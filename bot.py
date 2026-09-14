#!/usr/bin/env python3
"""
WhatsApp Beta TestFlight Monitor Bot
Dual-frequency monitoring: discovers the TestFlight URL from WABetaInfo
every 30 min, and checks for available slots every 2-30 seconds.
Sends Telegram notification the instant a slot opens.

Commands (register via @BotFather):
  /status - Show monitor status and stats
"""

from __future__ import annotations

import asyncio
import http.server
import json
import logging
import os
import random
import re
import signal
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

SPAIN_TZ = timezone(timedelta(hours=2))

def local_now() -> datetime:
    return datetime.now(SPAIN_TZ)

import httpx
from dotenv import load_dotenv

# ─── Configuration ───────────────────────────────────────────────────────────

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DEFAULT_TESTFLIGHT_URL = os.getenv("TESTFLIGHT_URL", "")
WABETAINFO_URL = os.getenv(
    "WABETAINFO_URL",
    "https://wabetainfo.com/wa-testflight/",
)
MIN_INTERVAL = int(os.getenv("MIN_INTERVAL", "2"))
MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", "30"))
URL_REFRESH_INTERVAL = int(os.getenv("URL_REFRESH_INTERVAL", "1800"))
PORT = int(os.getenv("PORT", "8080"))
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "5"))
ERROR_THRESHOLD = int(os.getenv("ERROR_THRESHOLD", "3"))

USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPad; CPU OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Mobile Safari/537.36",
]

TESTFLIGHT_PATTERN = re.compile(r"https://testflight\.apple\.com/join/[A-Za-z0-9]+")

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("wa-bot")

# ─── State ───────────────────────────────────────────────────────────────────

current_testflight_url = DEFAULT_TESTFLIGHT_URL
last_status: Optional[str] = None
last_status_change: Optional[float] = None
url_last_refreshed: float = 0.0
start_time: float = time.time()

total_checks: int = 0
consecutive_errors: int = 0
max_consecutive_errors: int = 0
errors_last_hour: int = 0
_last_error_reset: float = time.time()
last_error_msg: Optional[str] = None
last_error_time: Optional[float] = None
last_known_error_reported: bool = False

# offset for getUpdates polling (avoid re-processing old messages)
_updates_offset: int = 0

# ─── WABetaInfo URL Discovery ────────────────────────────────────────────────

async def discover_testflight_url(client: httpx.AsyncClient) -> Optional[str]:
    """Scrape WABetaInfo page and extract the current WhatsApp TestFlight URL."""
    try:
        response = await client.get(
            WABETAINFO_URL,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=15.0,
            follow_redirects=True,
        )
        response.raise_for_status()

        matches = TESTFLIGHT_PATTERN.findall(response.text)
        if matches:
            return matches[0]

        logger.warning("No TestFlight URL found on %s", WABETAINFO_URL)
        return None
    except Exception as exc:
        logger.error("Failed to discover URL from WABetaInfo: %s", exc)
        return None

# ─── TestFlight Status Check ─────────────────────────────────────────────────

async def check_testflight_status(client: httpx.AsyncClient, url: str) -> str:
    """Check whether the TestFlight beta has open slots.

    Returns one of: "open", "full", "closed", "unknown".
    """
    try:
        response = await client.get(
            url,
            headers={"User-Agent": random.choice(USER_AGENTS)},
            timeout=15.0,
            follow_redirects=True,
        )

        if response.status_code == 404:
            return "closed"

        text = response.text

        if "This beta is full" in text:
            return "full"
        if "isn" in text and "accepting" in text and "tester" in text:
            return "full"

        return "open"
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            return "closed"
        logger.error("HTTP error checking %s: %s", url, exc)
        return "unknown"
    except Exception as exc:
        logger.error("Error checking %s: %s", url, exc)
        return "unknown"

# ─── Telegram API helpers ────────────────────────────────────────────────────

async def _telegram_request(
    client: httpx.AsyncClient,
    method: str,
    payload: dict,
) -> Optional[dict]:
    """Raw call to the Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN:
        return None
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}"
    try:
        response = await client.post(url, json=payload, timeout=10.0)
        response.raise_for_status()
        data = response.json()
        if not data.get("ok"):
            logger.warning("Telegram API error: %s", data.get("description"))
            return None
        return data
    except Exception as exc:
        logger.error("Telegram request failed (%s): %s", method, exc)
        return None


async def send_message(client: httpx.AsyncClient, chat_id: str, text: str) -> bool:
    """Send a text message to a Telegram chat."""
    result = await _telegram_request(client, "sendMessage", {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    })
    return result is not None


async def get_updates(client: httpx.AsyncClient) -> list[dict]:
    """Poll for incoming messages (commands)."""
    global _updates_offset
    result = await _telegram_request(client, "getUpdates", {
        "offset": _updates_offset,
        "timeout": POLL_INTERVAL,
        "allowed_updates": ["message"],
    })
    if result and "result" in result:
        for update in result["result"]:
            _updates_offset = update["update_id"] + 1
        return result["result"]
    return []

# ─── Notifications ───────────────────────────────────────────────────────────

async def notify_slot_available(client: httpx.AsyncClient, url: str):
    await send_message(
        client, TELEGRAM_CHAT_ID,
        "<b>Hueco libre en WhatsApp Beta iOS</b>\n\n"
        f"<b>App:</b> WhatsApp Messenger Beta\n"
        f"<b>Link:</b> <a href=\"{url}\">Abrir en TestFlight</a>\n\n"
        f"<b>Detectado:</b> {local_now().strftime('%H:%M:%S')} (España)\n\n"
        "Abre el link en tu iPhone y acepta antes de que se llene.",
    )


async def notify_slot_filled(client: httpx.AsyncClient, url: str):
    await send_message(
        client, TELEGRAM_CHAT_ID,
        "<b>WhatsApp Beta — Se lleno de nuevo</b>\n\n"
        f"<b>Link:</b> {url}\n\n"
        "Seguimos monitorizando.",
    )


async def notify_url_changed(client: httpx.AsyncClient, old_url: str, new_url: str):
    await send_message(
        client, TELEGRAM_CHAT_ID,
        "<b>URL de WhatsApp Beta actualizada</b>\n\n"
        f"<b>Anterior:</b> {old_url}\n"
        f"<b>Nuevo:</b> {new_url}\n\n"
        "El bot ya esta monitorizando la nueva URL.",
    )


async def notify_consecutive_errors(client: httpx.AsyncClient, count: int, error_msg: str):
    await send_message(
        client, TELEGRAM_CHAT_ID,
        f"<b>Alerta: {count} errores consecutivos</b>\n\n"
        f"<b>Ultimo error:</b> {error_msg}\n"
        f"<b>Hora:</b> {local_now().strftime('%H:%M:%S')} (España)",
    )


async def notify_recovered(client: httpx.AsyncClient, error_msg: str, since: str):
    await send_message(
        client, TELEGRAM_CHAT_ID,
        "<b>Monitor recuperado</b>\n\n"
        f"Estuvo fallando desde las {since}\n"
        f"<b>Ultimo error:</b> {error_msg}\n"
        f"<b>Recuperado:</b> {local_now().strftime('%H:%M:%S')} (Espana)",
    )


async def notify_status(client: httpx.AsyncClient, chat_id: str):
    """Respond to a /status command with current monitor state."""
    uptime_delta = timedelta(seconds=int(time.time() - start_time))
    uptime_str = str(uptime_delta).split(".")[0]

    status_emoji = {"open": "🟢", "full": "🔴", "closed": "⚫", "unknown": "⚪"}
    status_icon = status_emoji.get(last_status or "unknown", "⚪")

    last_change_str = "—"
    if last_status_change:
        ago = int(time.time() - last_status_change)
        if ago < 60:
            last_change_str = f"hace {ago} s"
        elif ago < 3600:
            last_change_str = f"hace {ago // 60} min"
        else:
            last_change_str = f"hace {ago // 3600}h {(ago % 3600) // 60}min"

    last_error_str = "—"
    if last_error_time:
        ago = int(time.time() - last_error_time)
        last_error_str = f"hace {ago}s" if ago < 60 else f"hace {ago // 60}min"
        if last_error_msg:
            last_error_str += f" ({last_error_msg})"

    await send_message(
        client, chat_id,
        "🤖 <b>WhatsApp Beta Monitor</b>\n\n"
        f"📡 <b>URL:</b> {current_testflight_url}\n"
        f"{status_icon} <b>Slot:</b> {last_status or 'desconocido'}\n"
        f"🕐 <b>Último cambio:</b> {last_change_str}\n"
        f"📊 <b>Peticiones totales:</b> {total_checks:,}\n"
        f"❌ <b>Errores consecutivos:</b> {consecutive_errors}\n"
        f"📈 <b>Max errores seguidos:</b> {max_consecutive_errors}\n"
        f"🕐 <b>Errores última hora:</b> {errors_last_hour}\n"
        f"🔄 <b>Último refresh URL:</b> {int((time.time() - url_last_refreshed) / 60) if url_last_refreshed > 0 else '—'} min\n"
        f"⏱ <b>Uptime:</b> {uptime_str}\n"
        f"🩺 <b>Health:</b> {'❌ CAÍDO' if consecutive_errors >= ERROR_THRESHOLD else '✅ OK'}",
    )

# ─── Health HTTP Server ──────────────────────────────────────────────────────

class HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP endpoint for Render / UptimeRobot health checks."""

    def _respond_health(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        info = {
            "status": "ok",
            "monitored_url": current_testflight_url,
            "last_status": last_status,
            "total_checks": total_checks,
            "consecutive_errors": consecutive_errors,
            "uptime_seconds": int(time.time() - start_time),
        }
        self.wfile.write(json.dumps(info).encode())

    def do_GET(self):
        if self.path == "/health":
            self._respond_health()
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"WhatsApp Beta Monitor - GET /health")

    def do_HEAD(self):
        if self.path == "/health":
            self._respond_health()

    def log_message(self, fmt, *args):
        logger.debug("Health check: %s", " ".join(str(a) for a in args))


def run_health_server():
    server = http.server.HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health server listening on port %d", PORT)
    server.serve_forever()

# ─── Command Polling Loop ────────────────────────────────────────────────────

async def command_loop():
    """Poll Telegram for incoming commands every POLL_INTERVAL seconds."""
    logger.info("Command poller started (every %d s)", POLL_INTERVAL)
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(10.0),
        limits=httpx.Limits(max_keepalive_connections=3),
    ) as client:
        while True:
            try:
                updates = await get_updates(client)
                for update in updates:
                    message = update.get("message", {})
                    text = message.get("text", "")
                    chat_id = str(message.get("chat", {}).get("id", ""))

                    if not chat_id or not text:
                        continue

                    if text == "/status":
                        logger.info("Status requested via /status from chat %s", chat_id)
                        await notify_status(client, chat_id)
                        logger.info("Status response sent")

                    elif text.startswith("/"):
                        logger.debug("Unknown command: %s", text)

            except Exception as exc:
                logger.error("Command poll error: %s", exc)

            await asyncio.sleep(POLL_INTERVAL)

# ─── Main Monitoring Loop ────────────────────────────────────────────────────

async def monitor_loop():
    global current_testflight_url
    global last_status
    global last_status_change
    global url_last_refreshed
    global total_checks
    global consecutive_errors
    global max_consecutive_errors
    global errors_last_hour
    global _last_error_reset
    global last_error_msg
    global last_error_time
    global last_known_error_reported

    logger.info("WhatsApp Beta Monitor started")
    logger.info("Initial URL: %s", current_testflight_url)
    logger.info("Check interval: %d-%d s", MIN_INTERVAL, MAX_INTERVAL)
    logger.info("URL refresh interval: %d s (%d min)", URL_REFRESH_INTERVAL, URL_REFRESH_INTERVAL // 60)
    logger.info("WABetaInfo source: %s", WABETAINFO_URL)
    logger.info("Error threshold: %d", ERROR_THRESHOLD)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        limits=httpx.Limits(max_keepalive_connections=5),
    ) as client:
        # ── Auto-discovery on startup if no URL configured ──
        if not current_testflight_url:
            logger.info("No TestFlight URL configured, discovering from WABetaInfo...")
            while True:
                discovered = await discover_testflight_url(client)
                if discovered:
                    current_testflight_url = discovered
                    logger.info("URL discovered: %s", discovered)
                    await notify_url_changed(client, "(none)", discovered)
                    break
                logger.warning("No URL found, retrying in 60s...")
                await asyncio.sleep(60)

        while True:
            try:
                # ── URL Discovery (every N seconds) ──
                if time.time() - url_last_refreshed > URL_REFRESH_INTERVAL:
                    logger.info("Refreshing TestFlight URL from WABetaInfo...")
                    discovered = await discover_testflight_url(client)
                    if discovered and discovered != current_testflight_url:
                        old = current_testflight_url
                        current_testflight_url = discovered
                        logger.info("URL updated: %s -> %s", old, discovered)
                        await notify_url_changed(client, old, discovered)
                        last_status = None
                    elif discovered:
                        logger.info("URL confirmed: %s", discovered)
                    else:
                        logger.info("URL discovery returned nothing, keeping current")
                    url_last_refreshed = time.time()

                # ── Slot Status Check ──
                status = await check_testflight_status(client, current_testflight_url)

                # --- Error tracking ---
                # Reset errors_last_hour every 3600 s
                if time.time() - _last_error_reset > 3600:
                    errors_last_hour = 0
                    _last_error_reset = time.time()

                total_checks += 1

                if status == "unknown":
                    consecutive_errors += 1
                    if consecutive_errors > max_consecutive_errors:
                        max_consecutive_errors = consecutive_errors
                    errors_last_hour += 1

                    if consecutive_errors >= ERROR_THRESHOLD and not last_known_error_reported:
                        err_msg = last_error_msg or f"Status unknown after {consecutive_errors} checks"
                        await notify_consecutive_errors(client, consecutive_errors, err_msg)
                        last_known_error_reported = True
                else:
                    if consecutive_errors >= ERROR_THRESHOLD and last_known_error_reported:
                        await notify_recovered(
                            client,
                            last_error_msg or "unknown errors",
                            datetime.fromtimestamp(last_error_time or time.time(), tz=timezone.utc)
                            .strftime("%H:%M:%S UTC"),
                        )
                    consecutive_errors = 0
                    last_known_error_reported = False

                # --- Status transitions ---
                logger.info("Check #%d: %s", total_checks, status)

                if status == "open" and last_status != "open":
                    logger.info("SLOTS AVAILABLE!")
                    await notify_slot_available(client, current_testflight_url)
                    last_status = "open"
                    last_status_change = time.time()

                elif status == "full" and last_status == "open":
                    logger.info("Slots filled up again")
                    await notify_slot_filled(client, current_testflight_url)
                    last_status = "full"
                    last_status_change = time.time()

                elif status == "closed" and last_status != "closed":
                    logger.warning("Beta link returned 404 — may be closed / expired")
                    last_status = "closed"
                    last_status_change = time.time()

                elif status == "full" and last_status is None:
                    logger.info("Initial status: full")
                    last_status = "full"
                    last_status_change = time.time()

                elif status == "open" and last_status is None:
                    logger.info("Initial status: open (already available)")
                    await notify_slot_available(client, current_testflight_url)
                    last_status = "open"
                    last_status_change = time.time()

            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors > max_consecutive_errors:
                    max_consecutive_errors = consecutive_errors
                last_error_msg = str(exc)
                last_error_time = time.time()
                logger.error("Unexpected error in main loop: %s", exc)

            delay = random.randint(MIN_INTERVAL, MAX_INTERVAL)
            logger.info("Next check in ~%ds", delay)
            await asyncio.sleep(delay)

# ─── Entry Point ─────────────────────────────────────────────────────────────

def shutdown(signum, frame):
    logger.info("Received signal %s, shutting down", signum)
    raise SystemExit(0)

async def async_main():
    await asyncio.gather(
        monitor_loop(),
        command_loop(),
    )

def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set")

    thread = threading.Thread(target=run_health_server, daemon=True)
    thread.start()

    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown")

if __name__ == "__main__":
    main()
