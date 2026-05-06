
import os
from dotenv import load_dotenv
from app.config import settings
from app.services import email_service

load_dotenv()

print(f"EMAIL_ENABLED: {settings.EMAIL_ENABLED}")
print(f"SMTP_HOST: {settings.SMTP_HOST}")
print(f"SMTP_PORT: {settings.SMTP_PORT}")
print(f"SMTP_USER: {settings.SMTP_USER}")
print(f"SMTP_PASSWORD: {'SET' if settings.SMTP_PASSWORD else 'NOT SET'}")


# Try to send a test email BYPASSING the ENABLED check to verify credentials
print("\nAttempting to send test email (bypassing ENABLED check)...")
try:
    # Temporarily force enable for this test
    settings.EMAIL_ENABLED = True
    success = email_service.send_email(
        to_addrs=[settings.SMTP_USER],
        subject="Test Email Notification - Credential Check",
        body_text="This is a test email to verify the SMTP credentials are correct."
    )
    if success:
        print("Test email sent successfully! Your credentials are working.")
    else:
        print("Failed to send test email (returned False).")
except Exception as e:
    print(f"Error sending test email: {e}")

