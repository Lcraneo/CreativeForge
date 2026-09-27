"""Image-generation provider API (multi-model extension).

    GET    /api/v1/providers            list built-in + custom providers
    POST   /api/v1/providers            create a custom provider
    PUT    /api/v1/providers/settings   select provider/model + save credentials
    POST   /api/v1/providers/test       connectivity test (generates one image)
    PUT    /api/v1/providers/{id}       update a custom provider
    DELETE /api/v1/providers/{id}       delete a custom provider

Secrets are never returned — only ``has_key`` + a masked hint.
"""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.engines.imagegen import get_store, test_provider
from app.engines.imagegen.providers import BUILTIN_PROVIDER

router = APIRouter()


class CustomProviderRequest(BaseModel):
    id: Optional[str] = None
    label: str = Field(..., min_length=1)
    vendor: Optional[str] = None
    endpoint: str = Field(..., min_length=1)
    method: str = "POST"
    models: list[str] | str = Field(default_factory=list)
    default_model: Optional[str] = None
    default_size: str = "1024x1024"
    size_format: str = "x"
    auth: dict[str, Any] = Field(default_factory=dict)
    credential_fields: list[str] = Field(default_factory=lambda: ["api_key"])
    body: dict[str, Any] = Field(default_factory=dict)
    image_paths: list[str] = Field(default_factory=list)
    notes: Optional[str] = None


class SettingsRequest(BaseModel):
    provider: str = BUILTIN_PROVIDER
    model: Optional[str] = None
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    secret_id: Optional[str] = None
    app_key: Optional[str] = None


class TestRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    size: Optional[str] = None


@router.get("")
def list_providers():
    return get_store().public_listing()


@router.post("")
def create_provider(request: CustomProviderRequest):
    spec = get_store().add_custom(request.model_dump())
    return {"provider": spec["id"], "listing": get_store().public_listing()}


@router.put("/settings")
def save_settings(request: SettingsRequest):
    store = get_store()
    if store.get_spec(request.provider) is None:
        raise HTTPException(status_code=404, detail="unknown provider")
    credentials = {
        "api_key": request.api_key,
        "secret_key": request.secret_key,
        "secret_id": request.secret_id,
        "app_key": request.app_key,
    }
    credentials = {k: v for k, v in credentials.items() if v is not None}
    if credentials:
        store.save_credentials(request.provider, credentials)
    store.set_selected(request.provider, request.model)
    return store.public_listing()


@router.post("/test")
async def test(request: TestRequest):
    if get_store().get_spec(request.provider) is None:
        raise HTTPException(status_code=404, detail="unknown provider")
    return await test_provider(request.provider, request.model, request.size)


@router.put("/{provider_id}")
def update_provider(provider_id: str, request: CustomProviderRequest):
    updated = get_store().update_custom(provider_id, request.model_dump())
    if updated is None:
        raise HTTPException(status_code=404, detail="custom provider not found")
    return {"provider": updated["id"], "listing": get_store().public_listing()}


@router.delete("/{provider_id}")
def delete_provider(provider_id: str):
    if not get_store().delete_custom(provider_id):
        raise HTTPException(status_code=404, detail="custom provider not found")
    return get_store().public_listing()
