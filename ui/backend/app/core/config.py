# ui/backend/app/core/config.py
from pydantic import Field
from pydantic_settings import BaseSettings  # ✅ moved here in Pydantic v2


class Settings(BaseSettings):
    API_KEY: str = Field(default="dev-123")
    PRIVACY_MODE: bool = Field(default=False)
    FEED_SALT: str = Field(default="change-me")

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
