from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str
    PRIVACY_MODE: bool = False
    FEED_SALT: str
    EVENTS_FILE: str = "storage/events.jsonl"
    CORS_ORIGINS: str = "http://localhost:5173,http://localhost:8088"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
