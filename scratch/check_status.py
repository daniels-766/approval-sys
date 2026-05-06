
import os
from dotenv import load_dotenv
from app.config import settings
from app.services import email_service

# Reload environment
load_dotenv(override=True)

print(f"EMAIL_ENABLED: {settings.EMAIL_ENABLED}")

if settings.EMAIL_ENABLED:
    print("Email system is now ACTIVE.")
    # Optional: send a final verification email
    # success = email_service.send_email(...)
else:
    print("Email system is still INACTIVE. Please check if .env is loaded correctly.")
