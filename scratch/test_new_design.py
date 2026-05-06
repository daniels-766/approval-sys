
import os
from dotenv import load_dotenv
from app.config import settings
from app.services import email_service

load_dotenv(override=True)

print(f"EMAIL_ENABLED: {settings.EMAIL_ENABLED}")

# Sample data
title = "New Submission"
message = "jimbo123 has created a new submission: MASUK NOTIF"
link = "/approver/submission/17"
submission_code = "SUB-20260505-017"

subject, body_text, body_html = email_service.build_submission_email(
    title=title,
    message=message,
    link=link,
    submission_code=submission_code
)

print(f"\nSubject: {subject}")
print("-" * 20)
print("Sending email...")

try:
    success = email_service.send_email(
        to_addrs=[settings.SMTP_USER],
        subject=subject,
        body_text=body_text,
        body_html=body_html
    )
    if success:
        print("Email sent successfully! Check your inbox for the new design.")
    else:
        print("Failed to send email.")
except Exception as e:
    print(f"Error: {e}")
