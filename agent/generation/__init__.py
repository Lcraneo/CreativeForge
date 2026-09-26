"""Prompt-driven character generation (spec parsing + asset building)."""

from agent.generation.builder import build_asset, asset_identity, spec_palette
from agent.generation.spec import parse_prompt

__all__ = ["build_asset", "asset_identity", "spec_palette", "parse_prompt"]
