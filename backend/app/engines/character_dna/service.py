"""Character DNA service (Phase 14.14 / 14.11).

Ties together encoder -> vector store -> similarity retrieval -> DNA memory
-> version manager, and exposes the flows the agent uses:

    create(asset)          new character gets a DNA record
    new_version(base, ..)  modification keeps identity, bumps version
    search(image)          same-character check by identity vector
    search_by_text(text)   find a character from a natural language edit
"""

import re
from typing import Any

from app.engines.character_dna.encoder.clip_encoder import CharacterEncoder
from app.engines.character_dna.memory.dna_memory import DNAMemory
from app.engines.character_dna.retrieval.similarity import DNAResolver
from app.engines.character_dna.vector.store import VectorStore
from app.engines.character_dna.version.version_manager import VersionManager
from app.engines.foundation.dna_profiles import build_dna_profile
from app.engines.foundation.quality_model import assess_identity
from app.utils import stable_hash

VERSION_SUFFIX = re.compile(r"_v\d+$")

SPECIES_FEATURES = [
    ("cat", ("猫",)),
    ("dog", ("狗",)),
    ("dragon", ("龙",)),
    ("robot", ("机械", "机甲", "robot", "mech")),
]
ROLE_KEYWORDS = [
    ("warrior", ("战士", "武士", "warrior")),
    ("mage", ("法师", "魔法师", "mage")),
    ("archer", ("弓箭", "射手", "archer")),
    ("boss", ("boss", "首领")),
]


def semantic_keys(text: str) -> dict[str, str]:
    """Extract (species, role, style) keywords shared by create/edit goals."""
    lowered = (text or "").lower()
    features = [name for name, keys in SPECIES_FEATURES if any(k.lower() in lowered for k in keys)]
    role = next(
        (name for name, keys in ROLE_KEYWORDS if any(k.lower() in lowered for k in keys)),
        "character",
    )
    style = "cyberpunk" if any(k in lowered for k in ("赛博", "机械", "cyber")) else "anime"
    return {"species": "_".join(features) or "character", "role": role, "style": style}


def base_stem(image: str) -> str:
    stem = re.sub(r"\.[a-zA-Z0-9]+$", "", image or "")
    return VERSION_SUFFIX.sub("", stem)


def next_image_for(stem: str, version: str) -> str:
    """`cat.png` + `v2` -> `cat_v2.png` — keeps the encoder's identity stem."""
    root = base_stem(stem)
    ext_match = re.search(r"\.[a-zA-Z0-9]+$", stem)
    ext = ext_match.group(0) if ext_match else ".png"
    return f"{root}_{version}{ext}"


class CharacterDNAService:
    def __init__(
        self,
        encoder: CharacterEncoder | None = None,
        store: VectorStore | None = None,
        memory: DNAMemory | None = None,
        versions: VersionManager | None = None,
        threshold: float = 0.85,
    ):
        self.encoder = encoder or CharacterEncoder()
        self.store = store or VectorStore()
        self.memory = memory or DNAMemory()
        self.versions = versions or VersionManager()
        self.resolver = DNAResolver(self.store, threshold)

    # -- create ---------------------------------------------------------

    async def create(self, asset: dict[str, Any], action: str = "idle") -> dict[str, Any]:
        image = asset["content"]["image"]
        vector = await self.encoder.encode(image)
        stem = base_stem(image)
        character_id = f"{stem}_{stable_hash(stem) % 0xFFF:03x}"

        profile = build_dna_profile(asset, action)
        identity = {**self._semantic_identity(asset), "dna_profile": profile}
        version = self.versions.create_version(
            character_id, {"change_type": "created"}, asset_id=asset.get("id")
        )
        dna = {
            "character_id": character_id,
            "identity": identity,
            "profile": profile,
            "embedding": {"vector": vector, "model": self.encoder.model},
            "image_stem": image,
            "versions": [version["version"]],
            "version_records": [version],
        }
        self._remember(dna)
        return dna

    async def new_version(
        self,
        base_dna: dict[str, Any],
        asset: dict[str, Any],
        changes: dict[str, Any],
        action: str = "idle",
    ) -> dict[str, Any]:
        """Modification flow (Phase 14.11): same identity, new version."""
        character_id = base_dna["character_id"]
        image = asset["content"]["image"]
        vector = await self.encoder.encode(image)
        version = self.versions.create_version(
            character_id, changes, asset_id=asset.get("id")
        )
        profile = build_dna_profile(asset, action)
        similarity = assess_identity(
            {
                "profile": base_dna.get("profile")
                or (base_dna.get("identity") or {}).get("dna_profile")
            },
            {"profile": profile},
        )["similarity"]
        dna = {
            "character_id": character_id,
            "identity": base_dna.get("identity") or {},
            "profile": profile,
            "embedding": {"vector": vector, "model": self.encoder.model},
            "image_stem": image,
            "versions": [r["version"] for r in self.versions.lineage(character_id)],
            "version_records": self.versions.lineage(character_id),
            "changes": changes,
            "identity_similarity": similarity,
        }
        self._remember(dna)
        return dna

    def _remember(self, dna: dict[str, Any]) -> None:
        self.memory.save(dna)
        self.store.upsert(
            dna["character_id"],
            dna["embedding"]["vector"],
            {"style": (dna["identity"] or {}).get("style")},
        )

    # -- retrieval --------------------------------------------------------

    async def search(self, image: str) -> dict[str, Any]:
        result = await self.resolver.search(await self.encoder.encode(image))
        if result["match"]:
            result["character"] = self.memory.get(result["match"])
        return result

    def search_by_text(self, text: str) -> dict[str, Any] | None:
        """Find a character from a natural language edit request.

        Identity is matched on species parts ("机械猫战士" -> cat_robot parts
        {cat, robot}) so partial mentions still hit; role only adds weight.
        """
        keys = semantic_keys(text)
        best, best_score = None, 0
        for dna in self.memory.records.values():
            identity = dna.get("identity") or {}
            score = 0
            stored_parts = set(str(identity.get("species") or "").split("_"))
            wanted_parts = set(keys["species"].split("_"))
            if stored_parts & wanted_parts:
                score += 2
            if keys["role"] != "character" and identity.get("role") == keys["role"]:
                score += 1
            if score > best_score:
                best, best_score = dna, score
        return best if best_score >= 2 else None

    def get(self, character_id: str) -> dict[str, Any] | None:
        return self.memory.get(character_id)

    # -- identity ---------------------------------------------------------

    def _semantic_identity(self, asset: dict[str, Any]) -> dict[str, Any]:
        prompt = (asset.get("identity") or {}).get("prompt") or ""
        keys = semantic_keys(f"{(asset.get('identity') or {}).get('name', '')} {prompt}")
        body = self._body_geometry(asset)
        return {
            "name": (asset.get("identity") or {}).get("name"),
            "species": keys["species"],
            "role": keys["role"],
            "style": (asset.get("style") or {}).get("name") or keys["style"],
            "body": body,
            "color": [c for c in ((asset.get("pixel") or {}).get("palette") or {}).get("colors", [])],
        }

    @staticmethod
    def _body_geometry(asset: dict[str, Any]) -> dict[str, Any]:
        layers = (asset.get("content") or {}).get("layers") or []
        body = next((l for l in layers if l.get("name") == "body"), None)
        if not body:
            return {"height_ratio": 1.0}
        x1, y1, x2, y2 = body["bbox"]
        width = max(x2 - x1, 1.0)
        height = max(y2 - y1, 1.0)
        return {
            "height_ratio": round(height / width, 3),
            "head_ratio": 0.18,
            "armor_type": "metal" if any(
                k in str((asset.get("identity") or {}).get("prompt", ""))
                for k in ("机械", "机甲", "metal")
            ) else "none",
        }
