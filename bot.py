#!/usr/bin/env python3
"""
WhatsApp Beta TestFlight Monitor Bot
Dual-frequency monitoring: discovers the TestFlight URL from WABetaInfo
every 30 min, and checks for available slots every 2-30 seconds.
Sends Telegram notification the instant a slot opens.
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
from datetime import datetime, timezone
from typing import Optional

import httpx
from dotenv import load_dotenv

# ─── Configuration ───────────────────────────────────────────────────────────

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DEFAULT_TESTFLIGHT_URL = os.getenv(
    "TESTFLIGHT_URL",
    "https://testflight.apple.com/join/YcmGWyxV",
)
WABETAINFO_URL = os.getenv(
    "WABETAINFO_URL",
    "https://wabetainfo.com/wa-testflight/",
)
MIN_INTERVAL = int(os.getenv("MIN_INTERVAL", "2"))
MAX_INTERVAL = int(os.getenv("MAX_INTERVAL", "30"))
URL_REFRESH_INTERVAL = int(os.getenv("URL_REFRESH_INTERVAL", "1800"))
PORT = int(os.getenv("PORT", "8080"))

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
url_last_refreshed: float = 0.0
start_time: float = time.time()

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
        if "This beta isn't accepting any new testers" in text:
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

# ─── Telegram Notifications ──────────────────────────────────────────────────

async def send_telegram(client: httpx.AsyncClient, message: str) -> bool:
    """Send a message via the Telegram Bot API."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured — skipping notification")
        return False

    api_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    try:
        response = await client.post(api_url, json=payload, timeout=10.0)
        response.raise_for_status()
        logger.info("Telegram notification sent")
        return True
    except Exception as exc:
        logger.error("Failed to send Telegram: %s", exc)
        return False


async def notify_slot_available(client: httpx.AsyncClient, url: str):
    await send_telegram(
        client,
        (
            "🎉 <b>¡Hueco libre en WhatsApp Beta iOS!</b>\n\n"
            f"📱 <b>WhatsApp Messenger Beta</b>\n"
            f"🔗 <a href=\"{url}\">Abrir en TestFlight</a>\n\n"
            f"⏰ Detectado: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}\n\n"
            "⚠️ Ábrelo en tu iPhone y acepta YA antes de que se llene."
        ),
    )


async def notify_slot_filled(client: httpx.AsyncClient, url: str):
    await send_telegram(
        client,
        (
            "🔴 <b>WhatsApp Beta iOS — Se llenó de nuevo</b>\n\n"
            f"🔗 {url}\n\n"
            "Seguimos monitorizando para el próximo hueco."
        ),
    )


async def notify_url_changed(client: httpx.AsyncClient, old_url: str, new_url: str):
    await send_telegram(
        client,
        (
            "🔄 <b>WhatsApp Beta URL actualizada automáticamente</b>\n\n"
            f"<b>Anterior:</b> {old_url}\n"
            f"<b>Nuevo:</b> {new_url}\n\n"
            "El bot ya está monitorizando la nueva URL."
        ),
    )

# ─── Health HTTP Server ──────────────────────────────────────────────────────

class HealthHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP endpoint for Render / UptimeRobot health checks."""

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            info = {
                "status": "ok",
                "monitored_url": current_testflight_url,
                "last_status": last_status,
                "uptime_seconds": int(time.time() - start_time),
            }
            self.wfile.write(json.dumps(info).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"WhatsApp Beta Monitor - GET /health")

    def log_message(self, fmt, *args):
        logger.debug("Health check: %s %s %s", args[0], args[1], args[2])


def run_health_server():
    server = http.server.HTTPServer(("0.0.0.0", PORT), HealthHandler)
    logger.info("Health server listening on port %d", PORT)
    server.serve_forever()

# ─── Main Monitoring Loop ────────────────────────────────────────────────────

async def monitor_loop():
    global current_testflight_url, last_status, url_last_refreshed

    logger.info("WhatsApp Beta Monitor started")
    logger.info("Initial URL: %s", current_testflight_url)
    logger.info("Check interval: %d-%d s", MIN_INTERVAL, MAX_INTERVAL)
    logger.info(
        "URL refresh interval: %d s (%d min)",
        URL_REFRESH_INTERVAL,
        URL_REFRESH_INTERVAL // 60,
    )
    logger.info("WABetaInfo source: %s", WABETAINFO_URL)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15.0),
        limits=httpx.Limits(max_keepalive_connections=5),
    ) as client:
        while True:
            try:
                # ── URL Discovery (every N seconds) ──
                if time.time() - url_last_refreshed > URL_REFRESH_INTERVAL:
                    discovered = await discover_testflight_url(client)
                    if discovered and discovered != current_testflight_url:
                        old = current_testflight_url
                        current_testflight_url = discovered
                        logger.info("URL updated: %s -> %s", old, discovered)
                        await notify_url_changed(client, old, discovered)
                        last_status = None
                    elif discovered:
                        logger.debug("URL confirmed: %s", discovered)
                    else:
                        logger.debug("URL discovery returned nothing, keeping current")
                    url_last_refreshed = time.time()

                # ── Slot Status Check ──
                status = await check_testflight_status(client, current_testflight_url)
                logger.debug("Status: %s", status)

                if status == "open" and last_status != "open":
                    logger.info("SLOTS AVAILABLE!")
                    await notify_slot_available(client, current_testflight_url)
                    last_status = "open"

                elif status == "full" and last_status == "open":
                    logger.info("Slots filled up again")
                    await notify_slot_filled(client, current_testflight_url)
                    last_status = "full"

                elif status == "closed" and last_status != "closed":
                    logger.warning("Beta link returned 404 — may be closed / expired")
                    last_status = "closed"

                elif status == "full" and last_status is None:
                    logger.info("Initial status: full")
                    last_status = "full"

                elif status == "open" and last_status is None:
                    logger.info("Initial status: open (already available)")
                    await notify_slot_available(client, current_testflight_url)
                    last_status = "open"

                elif status == "unknown" and last_status != "unknown":
                    logger.warning("Status unknown — possible network issue")

            except Exception as exc:
                logger.error("Unexpected error in main loop: %s", exc)

            delay = random.randint(MIN_INTERVAL, MAX_INTERVAL)
            await asyncio.sleep(delay)

# ─── Entry Point ─────────────────────────────────────────────────────────────

def shutdown(signum, frame):
    logger.info("Received signal %s, shutting down", signum)
    sys.exit(0)

def main():
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning(
            "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set"
        )

    thread = threading.Thread(target=run_health_server, daemon=True)
    thread.start()

    try:
        asyncio.run(monitor_loop())
    except KeyboardInterrupt:
        logger.info("Shutdown by user")

if __name__ == "__main__":
    main()
