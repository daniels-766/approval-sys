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
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "https://approve.vjr.co.id")

    # Email (SMTP)
    EMAIL_ENABLED: bool = os.getenv("EMAIL_ENABLED", "0") == "1"
    EMAIL_FROM: str = os.getenv("EMAIL_FROM", "tech@allenhf.in")
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "tech@allenhf.in")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "jwymoogghdjbucfu")
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "1") == "1"

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
