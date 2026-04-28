import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    DB_HOST: str = os.getenv("DB_HOST", "localhost")
    DB_PORT: int = int(os.getenv("DB_PORT", "3306"))
    DB_USER: str = os.getenv("DB_USER", "root")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "")
    DB_NAME: str = os.getenv("DB_NAME", "approval_system_db")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "gyKkEmXyD33MR3fwKTfMvFccsOvZ1zrora87w54V0pZ")
    UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "app/static/uploads")
    MAX_UPLOAD_SIZE: int = int(os.getenv("MAX_UPLOAD_SIZE", "5242880"))  # 5MB

    # @property
    # def DATABASE_URL(self) -> str:
    #     return (
    #         f"mysql+pymysql://{self.DB_USER}:{self.DB_PASSWORD}"
    #         f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
    #     )

    @property
    def DATABASE_URL(self) -> str:
        import urllib.parse
        encoded_password = urllib.parse.quote_plus(self.DB_PASSWORD)
        return (
            f"mysql+pymysql://{self.DB_USER}:{encoded_password}"
            f"@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}?charset=utf8mb4"
        )

settings = Settings()
