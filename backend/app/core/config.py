from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global configuration (Phase 11.4).

    Every value can be overridden through environment variables or a `.env`
    file next to the backend working directory.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- database ------------------------------------------------------
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5432/creativeforge"
    )

    # --- external AI providers (Phase 12) -------------------------------
    # When WINDUP_BASE_URL is empty the adapter layer falls back to the
    # deterministic mock client so the whole pipeline stays runnable
    # without external credentials.
    WINDUP_BASE_URL: str = ""
    WINDUP_API_KEY: str = ""
    WINDUP_STYLE: str = "anime"

    # --- engine tuning (Phase 13-15) ------------------------------------
    DEFAULT_FPS: int = 12
    FRAME_COUNT: int = 8
    FRAME_SIZE: int = 128
    TARGET_ROOT_X: float = 256.0
    TARGET_ROOT_Y: float = 400.0
    TARGET_HEIGHT: float = 300.0

    # Same-character cosine similarity threshold (Phase 14).
    DNA_MATCH_THRESHOLD: float = 0.85

    # Hitbox dilation margin in pixels (Phase 15.5).
    HITBOX_EXPAND_RADIUS: int = 8

    # Default engine target for GImport (Phase 15.4).
    ENGINE_TARGET: str = "cocos"

    @property
    def target_root(self) -> tuple[float, float]:
        return (self.TARGET_ROOT_X, self.TARGET_ROOT_Y)

    @property
    def use_mock_generation(self) -> bool:
        return not self.WINDUP_BASE_URL


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
