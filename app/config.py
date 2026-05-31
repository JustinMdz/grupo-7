from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    port: int = 8002
    allowed_origins: str = "*"
    max_group_messages: int = 100
    max_dm_messages: int = 50
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_exp_seconds: int = 3600
    cloudinary_cloud_name: str = ""
    cloudinary_api_key: str = ""
    cloudinary_api_secret: str = ""
    max_upload_size_mb: int = 10
    group_encryption_key: str = ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
