"""Send notification emails via SMTP (DB system settings or env fallback)."""
import os
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, Any

logger = logging.getLogger(__name__)


def _smtp_config_from_env() -> dict:
    return {
        "host": os.environ.get("SMTP_HOST"),
        "port": os.environ.get("SMTP_PORT", "587"),
        "secure": os.environ.get("SMTP_USE_TLS", "true").lower() in ("1", "true", "yes") and os.environ.get("SMTP_PORT", "587") == "465",
        "username": os.environ.get("SMTP_USER"),
        "password": os.environ.get("SMTP_PASS"),
        "from_addr": os.environ.get("SMTP_FROM") or os.environ.get("SMTP_USER") or "noreply@localhost",
    }


def _smtp_config_from_settings(settings: Any) -> Optional[dict]:
    """Build smtp config dict from SystemSetting row. Password must be present for send."""
    if not settings or not getattr(settings, "smtp_host", None):
        return None
    return {
        "host": settings.smtp_host,
        "port": (settings.smtp_port or "587").strip(),
        "secure": getattr(settings, "smtp_secure", True),
        "username": getattr(settings, "smtp_username", None),
        "password": getattr(settings, "smtp_password", None),
        "from_addr": (getattr(settings, "smtp_from", None) or getattr(settings, "smtp_username", None) or "noreply@localhost"),
    }


def send_notification_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    smtp_config: Optional[dict] = None,
) -> Optional[str]:
    """
    Send an email. Uses smtp_config if provided, else env (SMTP_HOST, SMTP_PORT, etc.).
    Returns None on success, or error message string on failure.
    """
    if smtp_config:
        host = smtp_config.get("host")
        port = int(smtp_config.get("port", "587"))
        use_tls = smtp_config.get("secure", True) and port == 465
        user = smtp_config.get("username")
        password = smtp_config.get("password")
        from_addr = smtp_config.get("from_addr") or user or "noreply@localhost"
    else:
        cfg = _smtp_config_from_env()
        host = cfg["host"]
        if not host:
            return "SMTP not configured (SMTP_HOST missing)"
        port = int(cfg["port"])
        use_tls = cfg["secure"]
        user = cfg["username"]
        password = cfg["password"]
        from_addr = cfg["from_addr"]

    if not host:
        return "SMTP not configured (SMTP_HOST missing)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to
    msg.attach(MIMEText(body_text or body_html or "", "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    try:
        if use_tls and port == 465:
            with smtplib.SMTP_SSL(host, port) as server:
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                if use_tls:
                    server.starttls()
                if user and password:
                    server.login(user, password)
                server.sendmail(from_addr, [to], msg.as_string())
        return None
    except Exception as e:
        logger.warning("Notification email send failed: %s", e)
        return str(e)


def test_smtp_connection(settings: Any) -> tuple[bool, str]:
    """
    Test SMTP connection. Uses DB settings if provided and smtp_host set, else env.
    Returns (success, message).
    """
    if settings and getattr(settings, "smtp_host", None):
        port = int((getattr(settings, "smtp_port", None) or "587").strip())
        secure = getattr(settings, "smtp_secure", True)
        host = settings.smtp_host
        user = getattr(settings, "smtp_username", None)
        password = getattr(settings, "smtp_password", None)
    else:
        host = os.environ.get("SMTP_HOST")
        if not host:
            return False, "SMTP not configured (set SMTP host in settings or SMTP_HOST env)"
        port = int(os.environ.get("SMTP_PORT", "587"))
        secure = os.environ.get("SMTP_PORT", "587") == "465"
        user = os.environ.get("SMTP_USER")
        password = os.environ.get("SMTP_PASS")
    try:
        if secure and port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                if user and password:
                    server.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                if secure:
                    server.starttls()
                if user and password:
                    server.login(user, password)
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)
