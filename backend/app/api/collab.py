"""Collaboration API (Phase 22.6 / 22.8): projects, roles, asset lifecycle.

    Organization -> Project -> Asset Library

Roles:   owner > reviewer > developer > designer (owner does everything)
States:  created/ready/draft -> submit -> in_review -> approve
         -> approved -> promote -> production

Every transition is guarded: the actor must be a member with the role the
action requires, and the asset must be attached to the project. `tenant_id`
scopes projects for the SaaS multi-tenant split.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.models import Asset
from app.models.collab import Project, ProjectMember
from app.schemas.collab import (
    AssetAttachRequest,
    AssetStateOut,
    MemberAddRequest,
    MemberOut,
    ProjectCreateRequest,
    ProjectOut,
    ProjectSummary,
    TransitionRequest,
    TransitionResponse,
)

router = APIRouter()

ROLE_RANK = {"owner": 3, "reviewer": 2, "developer": 1, "designer": 0}

# action -> (allowed current states, minimum role)
TRANSITIONS = {
    "submit": ({"created", "ready", "draft"}, "designer", "in_review"),
    "approve": ({"in_review"}, "reviewer", "approved"),
    "promote": ({"approved"}, "owner", "production"),
}


async def _require_member(
    db: AsyncSession, project_id: str, user_id: str
) -> ProjectMember:
    row = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == user_id,
            )
        )
    ).scalars().first()
    if row is None:
        raise HTTPException(status_code=403, detail="not a project member")
    return row


@router.post("", response_model=ProjectSummary)
async def create_project(data: ProjectCreateRequest, db: AsyncSession = Depends(get_db)):
    project = Project(
        id=str(uuid.uuid4()),
        name=data.name,
        tenant_id=data.tenant_id or "default",
        owner_id=data.owner_id,
    )
    db.add(project)
    db.add(
        ProjectMember(
            id=str(uuid.uuid4()),
            project_id=project.id,
            user_id=data.owner_id,
            role="owner",
        )
    )
    await db.commit()
    return ProjectSummary(
        id=project.id,
        name=project.name,
        tenant_id=project.tenant_id,
        owner_id=project.owner_id,
    )


@router.get("", response_model=list[ProjectSummary])
async def list_projects(
    tenant_id: str | None = None, db: AsyncSession = Depends(get_db)
):
    query = select(Project).order_by(Project.created_at.desc())
    if tenant_id:
        query = query.where(Project.tenant_id == tenant_id)
    rows = (await db.execute(query)).scalars().all()
    return [
        ProjectSummary(id=r.id, name=r.name, tenant_id=r.tenant_id, owner_id=r.owner_id)
        for r in rows
    ]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: str, db: AsyncSession = Depends(get_db)):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    members = (
        await db.execute(
            select(ProjectMember).where(ProjectMember.project_id == project_id)
        )
    ).scalars().all()
    assets = (
        await db.execute(select(Asset).where(Asset.project_id == project_id))
    ).scalars().all()
    return ProjectOut(
        id=project.id,
        name=project.name,
        tenant_id=project.tenant_id,
        owner_id=project.owner_id,
        members=[MemberOut(user_id=m.user_id, role=m.role) for m in members],
        assets=[
            AssetStateOut(id=a.id, name=a.name, status=a.status or "created")
            for a in assets
        ],
    )


@router.post("/{project_id}/members", response_model=MemberOut)
async def add_member(
    project_id: str, data: MemberAddRequest, db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    existing = (
        await db.execute(
            select(ProjectMember).where(
                ProjectMember.project_id == project_id,
                ProjectMember.user_id == data.user_id,
            )
        )
    ).scalars().first()
    if existing is not None:
        existing.role = data.role
        await db.commit()
        return MemberOut(user_id=existing.user_id, role=existing.role)
    member = ProjectMember(
        id=str(uuid.uuid4()),
        project_id=project_id,
        user_id=data.user_id,
        role=data.role,
    )
    db.add(member)
    await db.commit()
    return MemberOut(user_id=member.user_id, role=member.role)


@router.post("/{project_id}/assets", response_model=AssetStateOut)
async def attach_asset(
    project_id: str, data: AssetAttachRequest, db: AsyncSession = Depends(get_db)
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    asset = await db.get(Asset, data.asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    asset.project_id = project_id
    await db.commit()
    return AssetStateOut(
        id=asset.id, name=asset.name, status=asset.status or "created"
    )


@router.post(
    "/{project_id}/assets/{asset_id}/transition",
    response_model=TransitionResponse,
)
async def transition_asset(
    project_id: str,
    asset_id: str,
    data: TransitionRequest,
    db: AsyncSession = Depends(get_db),
):
    project = await db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    asset = await db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="asset not found")
    if asset.project_id != project_id:
        raise HTTPException(status_code=400, detail="asset is not in this project")

    member = await _require_member(db, project_id, data.user_id)
    allowed_from, min_role, next_status = TRANSITIONS[data.action]
    if (asset.status or "created") not in allowed_from:
        raise HTTPException(
            status_code=409,
            detail=f"cannot {data.action} from status={asset.status}",
        )
    if ROLE_RANK.get(member.role, -1) < ROLE_RANK[min_role]:
        raise HTTPException(
            status_code=403,
            detail=f"role {member.role} cannot {data.action} (needs {min_role})",
        )
    asset.status = next_status
    await db.commit()
    return TransitionResponse(asset_id=asset.id, status=asset.status, action=data.action)