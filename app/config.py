from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8002
    allowed_origins: str = "*"
    max_group_messages: int = 100
    max_dm_messages: int = 50
    firebase_enabled: bool = False
    firebase_credentials_path: str | None = Field(
        default="serviceAccountKey.json",
        validation_alias=AliasChoices(
            "FIREBASE_CREDENTIALS_PATH",
            "FIREBASE_SERVICE_ACCOUNT_PATH",
            "SERVICE_ACCOUNT_KEY_PATH",
            "GOOGLE_APPLICATION_CREDENTIALS",
        ),
    )
    firebase_project_id: str | None = None
    firebase_messages_collection: str = "chat_messages"
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_exp_seconds: int = 3600
    group_encryption_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
