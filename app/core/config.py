from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str = "dev-123"
    PRIVACY_MODE: bool = False
    FEED_SALT: str = "change-me"
    EVENTS_FILE: str = "storage/events.jsonl"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
