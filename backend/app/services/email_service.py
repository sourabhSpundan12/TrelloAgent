import asyncio
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from app.core.config import settings
from app.core.logging import logger


class EmailService:
    """Enterprise SMTP email delivery service with HTML/text templates and async execution."""

    def __init__(self):
        self.host = settings.SMTP_HOST
        self.port = settings.SMTP_PORT
        self.user = settings.SMTP_USER
        self.password = settings.SMTP_PASSWORD
        self.from_email = settings.SMTP_FROM_EMAIL or settings.SMTP_USER or "noreply@agentictaskmanager.com"
        self.from_name = settings.SMTP_FROM_NAME or "Agentic Task Manager"
        self.use_tls = settings.SMTP_TLS
        self.use_ssl = settings.SMTP_SSL

    def is_configured(self) -> bool:
        """Returns True if SMTP credentials are fully provided."""
        return bool(self.user and self.password)

    def _send_sync(self, to_email: str, subject: str, html_content: str, text_content: str) -> None:
        """Synchronously deliver email over SMTP with TLS/SSL."""
        if not self.is_configured():
            logger.warning(
                f"[SMTP NOT CONFIGURED] Email to '{to_email}' was not sent over SMTP because "
                f"SMTP_USER/SMTP_PASSWORD are not set in .env. Subject: '{subject}'."
            )
            return

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{self.from_name} <{self.from_email}>"
        msg["To"] = to_email

        part1 = MIMEText(text_content, "plain", "utf-8")
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        try:
            if self.use_ssl:
                with smtplib.SMTP_SSL(self.host, self.port, timeout=15) as server:
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, [to_email], msg.as_string())
            else:
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    server.ehlo()
                    if self.use_tls:
                        server.starttls()
                        server.ehlo()
                    server.login(self.user, self.password)
                    server.sendmail(self.from_email, [to_email], msg.as_string())

            logger.info(f"Successfully delivered email via SMTP to {to_email}")
        except Exception as exc:
            logger.error(f"Failed to send email to {to_email} via SMTP ({self.host}:{self.port}): {exc}")
            raise exc

    async def send_email(self, to_email: str, subject: str, html_content: str, text_content: str) -> None:
        """Asynchronously send an email without blocking the FastAPI event loop."""
        await asyncio.to_thread(self._send_sync, to_email, subject, html_content, text_content)

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        reset_code: str,
        expire_minutes: int = 15,
    ) -> None:
        """Dispatch formatted password reset email with verification code."""
        subject = f"Your Password Reset Code: {reset_code} - Agentic Task Manager"
        text_content = (
            f"Hello {user_name},\n\n"
            f"We received a request to reset your password for Agentic Task Manager.\n"
            f"Your 6-digit verification code is: {reset_code}\n\n"
            f"This code will expire in {expire_minutes} minutes.\n"
            f"If you did not request this password reset, please ignore this email.\n\n"
            f"Best regards,\n"
            f"Agentic Task Manager Team"
        )

        year = datetime.now().year
        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Password Reset</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; margin: 0; padding: 24px 12px; }}
    .card {{ max-width: 520px; margin: 0 auto; background: #111827; border-radius: 20px; border: 1px solid #1f2937; overflow: hidden; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); }}
    .header {{ background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%); padding: 32px 24px; text-align: center; border-bottom: 1px solid #1f2937; }}
    .brand {{ display: inline-block; font-size: 20px; font-weight: 800; color: #10b981; letter-spacing: -0.5px; text-decoration: none; }}
    .tagline {{ margin: 6px 0 0 0; font-size: 12px; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }}
    .body {{ padding: 32px 28px; color: #e2e8f0; line-height: 1.6; font-size: 14px; }}
    .greeting {{ font-size: 18px; font-weight: 700; color: #f8fafc; margin-top: 0; }}
    .code-box {{ background: #0f172a; border: 2px dashed #059669; border-radius: 14px; text-align: center; padding: 22px 16px; margin: 26px 0; }}
    .code {{ font-size: 38px; font-weight: 800; letter-spacing: 10px; color: #10b981; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; display: block; }}
    .code-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; color: #6ee7b7; margin-top: 6px; }}
    .expiry {{ font-size: 12px; color: #94a3b8; text-align: center; }}
    .footer {{ background: #0b0f19; padding: 20px 24px; text-align: center; font-size: 11px; color: #64748b; border-top: 1px solid #1f2937; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="brand">Agentic Task Manager</div>
      <div class="tagline">Autonomous AI & Trello MCP Orchestration</div>
    </div>
    <div class="body">
      <div class="greeting">Password Reset Request</div>
      <p>Hello <strong>{user_name}</strong>,</p>
      <p>We received a request to reset the password for your account associated with <strong>{to_email}</strong>. Use the 6-digit code below to set your new password:</p>
      <div class="code-box">
        <span class="code">{reset_code}</span>
        <div class="code-label">Verification Code</div>
      </div>
      <div class="expiry">This verification code expires in <strong>{expire_minutes} minutes</strong>.</div>
      <p style="margin-top: 24px; font-size: 12px; color: #94a3b8;">If you didn't request a password reset, you can safely ignore this email. Your current password remains secure.</p>
    </div>
    <div class="footer">
      &copy; {year} Agentic Task Manager Platform. Enterprise Security.
    </div>
  </div>
</body>
</html>"""
        await self.send_email(to_email, subject, html_content, text_content)
