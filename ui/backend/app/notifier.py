import os
from typing import Any

# httpx only used if TELEGRAM is configured
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT = os.getenv("TELEGRAM_CHAT_ID")


def _fmt(event: dict[str, Any]) -> str:
    d = event.get("data", {})
    ip = d.get("ip", "-")
    user = d.get("username", "-")
    etype = event.get("type", "event")
    src = event.get("source", "sensor")
    return f"🔔 {src}:{etype} from {ip} (user={user})"


def notify(event: dict[str, Any]) -> None:
    """Best-effort alert. If TELEGRAM_* not set, just no-op."""
    if not (TELEGRAM_TOKEN and TELEGRAM_CHAT):
        # no config — skip quietly
        return

    try:
        import httpx

        msg = _fmt(event)
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHAT, "text": msg, "disable_web_page_preview": True}
        with httpx.Client(timeout=8.0) as client:
            client.post(url, json=payload)
    except Exception:
        # never crash the API because alerting failed
        pass
