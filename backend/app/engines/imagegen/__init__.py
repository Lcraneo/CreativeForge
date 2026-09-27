"""Image generation engine (multi-provider API extension).

A single facade over:

    * the project's built-in deterministic 2D generator (default), and
    * seven pre-registered hosted image APIs + user-defined custom providers.

Public surface: ``generate`` / ``test_provider`` / ``get_store``.
"""

from app.engines.imagegen.providers import (  # noqa: F401
    BUILTIN_PROVIDER,
    PROVIDERS,
    ProviderError,
)
from app.engines.imagegen.service import (  # noqa: F401
    GenerateResult,
    generate,
    test_provider,
)
from app.engines.imagegen.store import get_store  # noqa: F401

__all__ = [
    "BUILTIN_PROVIDER",
    "PROVIDERS",
    "ProviderError",
    "GenerateResult",
    "generate",
    "test_provider",
    "get_store",
]
