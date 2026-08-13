from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg://billing:billing@db:5432/billing"
    WEBHOOK_SECRET: str = "development-secret-change-me"
    APP_ENV: str = "development"
    ENABLE_MOCK_GATEWAY: bool = True
    # Schema creation and demo-data seeding are convenient locally, but must not
    # run during every serverless instance startup.
    AUTO_INITIALIZE_DATABASE: bool = False
    # A comma-separated list of browser origins allowed to call the API.
    CORS_ORIGINS: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
