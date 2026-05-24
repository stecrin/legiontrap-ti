from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    API_KEY: str
    PRIVACY_MODE: bool = False
    FEED_SALT: str
    EVENTS_FILE: str = "storage/events.jsonl"

    model_config = SettingsConfigDict(env_file=".env")


settings = Settings()
