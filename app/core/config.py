from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str
    PRIVACY_MODE: bool = False
    FEED_SALT: str
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8088"
    LOGIN_RATE_LIMIT: str = "5/minute"
    DB_PATH: str = "storage/legiontrap.db"

    # ---------------------------------------------------------------------------
    # Campaign clustering similarity weights (must sum to 1.0 ± 0.01)
    # ---------------------------------------------------------------------------
    WEIGHT_TIMING: float = 0.20
    WEIGHT_SEQUENCE: float = 0.35
    WEIGHT_PROTOCOL: float = 0.25
    WEIGHT_CREDENTIAL: float = 0.10
    WEIGHT_TARGET: float = 0.10

    # ---------------------------------------------------------------------------
    # Campaign clustering association thresholds
    # ---------------------------------------------------------------------------
    SIMILARITY_AUTO_THRESHOLD: float = 0.80
    SIMILARITY_UNCERTAIN_LOW: float = 0.60
    TEMPORAL_THRESHOLD_6M: float = 0.85
    TEMPORAL_THRESHOLD_12M: float = 0.90
    MIN_EVENTS_FOR_CLUSTERING: int = 10

    # ---------------------------------------------------------------------------
    # Campaign lifecycle thresholds (days)
    # ---------------------------------------------------------------------------
    CAMPAIGN_ACTIVE_DAYS: int = 7
    CAMPAIGN_DORMANT_DAYS: int = 90

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(
        "WEIGHT_TIMING",
        "WEIGHT_SEQUENCE",
        "WEIGHT_PROTOCOL",
        "WEIGHT_CREDENTIAL",
        "WEIGHT_TARGET",
    )
    @classmethod
    def weight_in_range(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError(f"Similarity weight must be in (0, 1]; got {v}")
        return v

    @field_validator(
        "SIMILARITY_AUTO_THRESHOLD",
        "SIMILARITY_UNCERTAIN_LOW",
        "TEMPORAL_THRESHOLD_6M",
        "TEMPORAL_THRESHOLD_12M",
    )
    @classmethod
    def threshold_in_range(cls, v: float) -> float:
        if not (0 < v <= 1):
            raise ValueError(f"Similarity threshold must be in (0, 1]; got {v}")
        return v

    @field_validator("MIN_EVENTS_FOR_CLUSTERING", "CAMPAIGN_ACTIVE_DAYS", "CAMPAIGN_DORMANT_DAYS")
    @classmethod
    def positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Value must be >= 1; got {v}")
        return v

    @model_validator(mode="after")
    def weights_sum_to_one(self) -> "Settings":
        total = (
            self.WEIGHT_TIMING
            + self.WEIGHT_SEQUENCE
            + self.WEIGHT_PROTOCOL
            + self.WEIGHT_CREDENTIAL
            + self.WEIGHT_TARGET
        )
        if abs(total - 1.0) > 0.01:
            raise ValueError(
                f"Similarity weights must sum to 1.0 (got {total:.4f}). "
                "Adjust WEIGHT_TIMING, WEIGHT_SEQUENCE, WEIGHT_PROTOCOL, "
                "WEIGHT_CREDENTIAL, and WEIGHT_TARGET."
            )
        return self


settings = Settings()
