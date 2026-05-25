from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str
    PRIVACY_MODE: bool = False
    FEED_SALT: str
    # Deprecated: JSONL replica file. Remove after all consumers migrate to the SQLite API.
    EVENTS_FILE: str = "storage/events.jsonl"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8088"
    LOGIN_RATE_LIMIT: str = "5/minute"
    DB_PATH: str = "storage/legiontrap.db"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
