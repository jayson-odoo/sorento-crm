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


def send_notification_email_multi(
    to_list: list[str],
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    smtp_config: Optional[dict] = None,
) -> Optional[str]:
    """
    Send one email to multiple recipients (To: all). Uses smtp_config if provided, else env.
    Returns None on success, or error message string on failure.
    """
    if not to_list:
        return "No recipients"
    if smtp_config:
        host = smtp_config.get("host")
        port = int(smtp_config.get("port", "587"))
        secure = smtp_config.get("secure", True)
        user = smtp_config.get("username")
        password = smtp_config.get("password")
        from_addr = smtp_config.get("from_addr") or user or "noreply@localhost"
    else:
        cfg = _smtp_config_from_env()
        host = cfg["host"]
        if not host:
            return "SMTP not configured (SMTP_HOST missing)"
        port = int(cfg["port"])
        secure = cfg["secure"]
        user = cfg["username"]
        password = cfg["password"]
        from_addr = cfg["from_addr"]

    if not host:
        return "SMTP not configured (SMTP_HOST missing)"

    use_ssl = secure and port == 465
    use_starttls = secure and port != 465

    to_list = [t.strip() for t in to_list if t and str(t).strip()]
    if not to_list:
        return "No valid recipients"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    msg.attach(MIMEText(body_text or body_html or "", "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    def do_login(server: smtplib.SMTP) -> None:
        if user and password:
            try:
                server.login(user, password)
            except smtplib.SMTPNotSupportedError:
                pass
            except smtplib.SMTPException as e:
                if "not supported" in str(e).lower() and "auth" in str(e).lower():
                    pass
                else:
                    raise

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                do_login(server)
                server.sendmail(from_addr, to_list, msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                if use_starttls:
                    server.starttls()
                do_login(server)
                server.sendmail(from_addr, to_list, msg.as_string())
        return None
    except Exception as e:
        logger.warning("Notification email (multi) send failed: %s", e)
        return str(e)


def send_notification_email(
    to: str,
    subject: str,
    body_text: str,
    body_html: Optional[str] = None,
    smtp_config: Optional[dict] = None,
    from_name: Optional[str] = None,
) -> Optional[str]:
    """
    Send an email. Uses smtp_config if provided, else env (SMTP_HOST, SMTP_PORT, etc.).
    If from_name is set, the From header is formatted as "Name" <addr> for a professional sender.
    Returns None on success, or error message string on failure.
    """
    if smtp_config:
        host = smtp_config.get("host")
        port = int(smtp_config.get("port", "587"))
        secure = smtp_config.get("secure", True)
        user = smtp_config.get("username")
        password = smtp_config.get("password")
        from_addr = smtp_config.get("from_addr") or user or "noreply@localhost"
    else:
        cfg = _smtp_config_from_env()
        host = cfg["host"]
        if not host:
            return "SMTP not configured (SMTP_HOST missing)"
        port = int(cfg["port"])
        secure = cfg["secure"]
        user = cfg["username"]
        password = cfg["password"]
        from_addr = cfg["from_addr"]

    if not host:
        return "SMTP not configured (SMTP_HOST missing)"

    use_ssl = secure and port == 465
    use_starttls = secure and port != 465

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f'"{from_name}" <{from_addr}>' if from_name else from_addr
    msg["To"] = to
    msg.attach(MIMEText(body_text or body_html or "", "plain", "utf-8"))
    if body_html:
        msg.attach(MIMEText(body_html, "html", "utf-8"))

    def do_login(server: smtplib.SMTP) -> None:
        if user and password:
            try:
                server.login(user, password)
            except smtplib.SMTPNotSupportedError:
                pass
            except smtplib.SMTPException as e:
                if "not supported" in str(e).lower() and "auth" in str(e).lower():
                    pass
                else:
                    raise

    try:
        if use_ssl:
            with smtplib.SMTP_SSL(host, port) as server:
                do_login(server)
                server.sendmail(from_addr, [to], msg.as_string())
        else:
            with smtplib.SMTP(host, port) as server:
                if use_starttls:
                    server.starttls()
                do_login(server)
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
    def _do_login(server: smtplib.SMTP) -> None:
        if user and password:
            try:
                server.login(user, password)
            except smtplib.SMTPNotSupportedError:
                pass
            except smtplib.SMTPException as e:
                if "not supported" in str(e).lower() and "auth" in str(e).lower():
                    pass
                else:
                    raise

    try:
        if secure and port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=10) as server:
                _do_login(server)
        else:
            with smtplib.SMTP(host, port, timeout=10) as server:
                if secure:
                    server.starttls()
                _do_login(server)
        return True, "Connection successful"
    except Exception as e:
        return False, str(e)
