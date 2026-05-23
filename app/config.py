from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8002
    allowed_origins: str = "*"
    max_group_messages: int = 100
    max_dm_messages: int = 50

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
