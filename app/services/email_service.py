import smtplib
import threading
from email.message import EmailMessage

from app.config import settings


def _absolute_url(link: str | None) -> str | None:
    if not link:
        return None
    if link.startswith("http://") or link.startswith("https://"):
        return link
    base = (settings.APP_BASE_URL or "").rstrip("/")
    path = link if link.startswith("/") else f"/{link}"
    return f"{base}{path}"


def send_email(
    to_addrs: list[str],
    subject: str,
    body_text: str,
    *,
    body_html: str | None = None,
) -> bool:
    """
    Send an email via SMTP.
    Controlled by env:
      - EMAIL_ENABLED=1 to actually send
      - SMTP_* for server/auth
    """
    if not settings.EMAIL_ENABLED:
        return False
    if not to_addrs:
        return False
    if not settings.SMTP_PASSWORD:
        # Misconfigured; don't crash app flows.
        return False

    msg = EmailMessage()
    msg["From"] = settings.EMAIL_FROM
    msg["To"] = ", ".join([a for a in to_addrs if a])
    msg["Subject"] = subject
    msg.set_content(body_text)
    if body_html:
        msg.add_alternative(body_html, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as smtp:
        smtp.ehlo()
        if settings.SMTP_USE_TLS:
            smtp.starttls()
            smtp.ehlo()
        smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    return True


def send_email_async(
    to_addrs: list[str],
    subject: str,
    body_text: str,
    *,
    body_html: str | None = None,
) -> None:
    # Fire-and-forget so user actions remain fast.
    def _runner():
        try:
            send_email(to_addrs, subject, body_text, body_html=body_html)
        except Exception:
            # Avoid impacting main flow on SMTP problems.
            return

    threading.Thread(target=_runner, daemon=True).start()


def build_submission_email(
    *,
    title: str,
    message: str,
    link: str | None = None,
    submission_code: str | None = None,
) -> tuple[str, str, str | None]:
    """Create a proper subject, text body, and attractive HTML body for email events."""
    subject_parts = [title]
    if submission_code:
        subject_parts.append(f"({submission_code})")
    subject = " ".join(subject_parts)

    url = _absolute_url(link)
    
    # Text Version
    body_text = message
    if url:
        body_text = f"{body_text}\n\nView details: {url}"

    # HTML Version (Premium Design)
    html_message = message.replace('\n', '<br>')
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            .container {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f9f9f9;
                border-radius: 12px;
            }}
            .header {{
                background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
                color: white;
                padding: 30px;
                border-radius: 12px 12px 0 0;
                text-align: center;
            }}
            .content {{
                background-color: white;
                padding: 30px;
                border-radius: 0 0 12px 12px;
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            }}
            .footer {{
                text-align: center;
                margin-top: 20px;
                color: #6b7280;
                font-size: 12px;
            }}
            .button {{
                display: inline-block;
                padding: 12px 24px;
                background-color: #6366f1;
                color: white !important;
                text-decoration: none;
                border-radius: 6px;
                font-weight: 600;
                margin-top: 20px;
            }}
            .submission-code {{
                display: inline-block;
                padding: 4px 12px;
                background-color: #eef2ff;
                color: #4338ca;
                border-radius: 4px;
                font-family: monospace;
                font-weight: bold;
                margin-bottom: 10px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1 style="margin:0; font-size: 24px;">{title}</h1>
            </div>
            <div class="content">
                {f'<div class="submission-code">{submission_code}</div>' if submission_code else ''}
                <p style="color: #374151; font-size: 16px; line-height: 1.6;">
                    {html_message}
                </p>
                {f'<div style="text-align: center;"><a href="{url}" class="button">Click Here to View</a></div>' if url else ''}
            </div>
            <div class="footer">
                <p>Sent by Approval System &bull; &copy; 2026</p>
            </div>
        </div>
    </body>
    </html>
    """

    
    return subject, body_text, body_html

