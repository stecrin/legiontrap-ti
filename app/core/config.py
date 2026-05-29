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

    # ---------------------------------------------------------------------------
    # AI backend configuration (Phase 5)
    # ---------------------------------------------------------------------------
    AI_BACKEND: str = "none"  # none | ollama | claude
    ANTHROPIC_API_KEY: str | None = None
    OLLAMA_HOST: str = "http://localhost:11434"
    AI_MODEL: str | None = None
    AI_TIMEOUT_SECONDS: int = 30
    AI_MAX_REQUESTS_PER_MINUTE: int = 10

    # ---------------------------------------------------------------------------
    # Phase 7 — per-campaign weight profile adjustment (A1)
    # ---------------------------------------------------------------------------
    WEIGHT_REVIEW_NUDGE: float = 0.02
    WEIGHT_FLOOR: float = 0.05
    WEIGHT_CEILING: float = 0.60
    WEIGHT_PROFILE_MIN_REVIEWS: int = 3
    WEIGHT_HIGH_SCORE_GATE: float = 0.70

    # ---------------------------------------------------------------------------
    # Phase 7 — behavioral drift alert thresholds (A2)
    # ---------------------------------------------------------------------------
    DRIFT_ALERT_COMPOSITE_THRESHOLD: float = 0.65
    DRIFT_ALERT_TIMING_THRESHOLD: float = 0.60
    DRIFT_ALERT_SEQUENCE_THRESHOLD: float = 0.55
    DRIFT_ALERT_PROTOCOL_THRESHOLD: float = 0.60
    DRIFT_ALERT_CREDENTIAL_THRESHOLD: float = 0.55
    DRIFT_ALERT_TARGET_THRESHOLD: float = 0.60

    # ---------------------------------------------------------------------------
    # Phase 7 — sparse campaign surface and evidence quality (A3)
    # ---------------------------------------------------------------------------
    SPARSE_OBS_MATURE: int = 20  # observations for a mature density score
    SPARSE_OBS_ESTABLISHED: int = 8  # observations for an established density score
    SPARSE_IP_MATURE: int = 5  # unique source IPs for a mature density score
    SPARSE_AGE_HOURS_MATURE: float = 168.0  # age span (hours) for a mature score (1 week)
    SPARSE_AGE_HOURS_ESTABLISHED: float = 24.0  # age span (hours) for established (1 day)

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

    @field_validator("AI_BACKEND")
    @classmethod
    def ai_backend_valid(cls, v: str) -> str:
        allowed = {"none", "ollama", "claude"}
        normalized = v.lower()
        if normalized not in allowed:
            raise ValueError(f"AI_BACKEND must be one of {sorted(allowed)}; got {v!r}")
        return normalized

    @field_validator("AI_TIMEOUT_SECONDS", "AI_MAX_REQUESTS_PER_MINUTE")
    @classmethod
    def positive_ai_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Value must be >= 1; got {v}")
        return v

    @field_validator(
        "WEIGHT_REVIEW_NUDGE", "WEIGHT_FLOOR", "WEIGHT_CEILING", "WEIGHT_HIGH_SCORE_GATE"
    )
    @classmethod
    def weight_profile_float_in_range(cls, v: float) -> float:
        if not (0 < v < 1):
            raise ValueError(f"Value must be in (0, 1); got {v}")
        return v

    @field_validator("WEIGHT_PROFILE_MIN_REVIEWS")
    @classmethod
    def weight_profile_min_reviews_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Value must be >= 1; got {v}")
        return v

    @field_validator(
        "DRIFT_ALERT_COMPOSITE_THRESHOLD",
        "DRIFT_ALERT_TIMING_THRESHOLD",
        "DRIFT_ALERT_SEQUENCE_THRESHOLD",
        "DRIFT_ALERT_PROTOCOL_THRESHOLD",
        "DRIFT_ALERT_CREDENTIAL_THRESHOLD",
        "DRIFT_ALERT_TARGET_THRESHOLD",
    )
    @classmethod
    def drift_threshold_in_range(cls, v: float) -> float:
        if not (0 < v < 1):
            raise ValueError(f"Drift alert threshold must be in (0, 1); got {v}")
        return v

    @field_validator("SPARSE_OBS_MATURE", "SPARSE_OBS_ESTABLISHED", "SPARSE_IP_MATURE")
    @classmethod
    def sparse_positive_int(cls, v: int) -> int:
        if v < 1:
            raise ValueError(f"Value must be >= 1; got {v}")
        return v

    @field_validator("SPARSE_AGE_HOURS_MATURE", "SPARSE_AGE_HOURS_ESTABLISHED")
    @classmethod
    def sparse_positive_float(cls, v: float) -> float:
        if v <= 0:
            raise ValueError(f"Age span threshold must be > 0; got {v}")
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
