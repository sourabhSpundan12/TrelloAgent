import asyncio
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict

from app.core.config import settings
from app.core.logging import logger


class EmailService:
    """Enterprise SMTP email delivery service with direct code formatting and dynamic env reloading."""

    def _get_config(self) -> Dict[str, Any]:
        """Dynamically re-reads environment and .env files to capture freshly updated credentials."""
        from dotenv import dotenv_values

        env_file_paths = [
            Path(__file__).resolve().parents[3] / ".env",
            Path(__file__).resolve().parents[2] / ".env",
            Path("agentic-task-manager/.env"),
            Path(".env"),
        ]
        vals: Dict[str, Any] = {}
        for p in env_file_paths:
            if p.exists():
                try:
                    vals.update(dotenv_values(str(p)))
                except Exception:
                    pass

        host = os.getenv("SMTP_HOST") or vals.get("SMTP_HOST") or settings.SMTP_HOST or "smtp.gmail.com"
        port_raw = os.getenv("SMTP_PORT") or vals.get("SMTP_PORT") or settings.SMTP_PORT or 587
        try:
            port = int(port_raw)
        except Exception:
            port = 587

        user = (os.getenv("SMTP_USER") or vals.get("SMTP_USER") or settings.SMTP_USER or "").strip()
        password = (os.getenv("SMTP_PASSWORD") or vals.get("SMTP_PASSWORD") or settings.SMTP_PASSWORD or "").strip()
        from_email = (
            os.getenv("SMTP_FROM_EMAIL") or vals.get("SMTP_FROM_EMAIL") or settings.SMTP_FROM_EMAIL or user
        ).strip()
        from_name = (
            os.getenv("SMTP_FROM_NAME") or vals.get("SMTP_FROM_NAME") or settings.SMTP_FROM_NAME or "PM Hooks"
        )
        use_tls_str = str(os.getenv("SMTP_TLS", vals.get("SMTP_TLS", settings.SMTP_TLS))).lower()
        use_tls = use_tls_str in ("true", "1", "yes")
        use_ssl_str = str(os.getenv("SMTP_SSL", vals.get("SMTP_SSL", settings.SMTP_SSL))).lower()
        use_ssl = use_ssl_str in ("true", "1", "yes")

        return {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "from_email": from_email,
            "from_name": from_name,
            "use_tls": use_tls,
            "use_ssl": use_ssl,
        }

    def is_configured(self) -> bool:
        cfg = self._get_config()
        return bool(cfg["user"] and cfg["password"])

    def _send_sync(self, to_email: str, subject: str, html_content: str, text_content: str) -> None:
        cfg = self._get_config()
        if not cfg["user"] or not cfg["password"]:
            logger.warning(
                f"[SMTP NOT CONFIGURED] Email to '{to_email}' skipped because SMTP_USER/SMTP_PASSWORD are not set."
            )
            raise ValueError(
                "SMTP credentials are not configured. Please set SMTP_USER and SMTP_PASSWORD in agentic-task-manager/.env"
            )

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{cfg['from_name']} <{cfg['from_email']}>"
        msg["To"] = to_email

        part1 = MIMEText(text_content, "plain", "utf-8")
        part2 = MIMEText(html_content, "html", "utf-8")
        msg.attach(part1)
        msg.attach(part2)

        if cfg["use_ssl"] or cfg["port"] == 465:
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20) as server:
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], [to_email], msg.as_string())
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=20) as server:
                server.ehlo()
                if cfg["use_tls"]:
                    server.starttls()
                    server.ehlo()
                server.login(cfg["user"], cfg["password"])
                server.sendmail(cfg["from_email"], [to_email], msg.as_string())

        logger.info(f"Successfully delivered verification email via SMTP to {to_email}")

    async def send_email(self, to_email: str, subject: str, html_content: str, text_content: str) -> None:
        await asyncio.to_thread(self._send_sync, to_email, subject, html_content, text_content)

    async def send_password_reset_email(
        self,
        to_email: str,
        user_name: str,
        reset_code: str,
        expire_minutes: int = 15,
    ) -> None:
        """Dispatch email containing specifically the verification code."""
        subject = f"Your Verification Code: {reset_code}"
        text_content = f"Your Verification Code is: {reset_code}\n\nValid for {expire_minutes} minutes."

        html_content = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Verification Code</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background-color: #0b0f19; margin: 0; padding: 32px 16px; }}
    .card {{ max-width: 420px; margin: 0 auto; background: #111827; border: 1px solid #1f2937; border-radius: 18px; padding: 36px 28px; text-align: center; color: #f8fafc; box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.5); }}
    .title {{ font-size: 14px; font-weight: 600; text-transform: uppercase; letter-spacing: 1.5px; color: #94a3b8; margin-bottom: 24px; }}
    .code {{ font-size: 44px; font-weight: 800; letter-spacing: 12px; color: #10b981; font-family: ui-monospace, Menlo, Monaco, Consolas, monospace; background: #0f172a; border: 2px dashed #059669; border-radius: 14px; padding: 18px 24px; display: inline-block; margin: 12px 0 24px 0; }}
    .expiry {{ font-size: 13px; color: #cbd5e1; }}
    .footer {{ margin-top: 32px; font-size: 11px; color: #64748b; border-top: 1px solid #1f2937; padding-top: 18px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="title">PM Hooks</div>
    <div class="expiry">Your password reset verification code:</div>
    <div class="code">{reset_code}</div>
    <div class="expiry">This code is valid for <strong>{expire_minutes} minutes</strong>.</div>
    <div class="footer">If you did not request this, please ignore this email.</div>
  </div>
</body>
</html>"""
        await self.send_email(to_email, subject, html_content, text_content)
