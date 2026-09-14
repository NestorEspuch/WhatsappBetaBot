# WhatsApp Beta Monitor

Bot that automatically monitors the availability of the **WhatsApp Messenger Beta for iOS** on TestFlight and notifies you via Telegram when a slot opens up.

## Features

- Monitoring every 2-30 seconds with random interval
- Auto-discovery of TestFlight URL from WABetaInfo (every 30 min)
- Instant Telegram notifications
- `/status` command to check monitor status
- Automatic alerts when the bot encounters errors
- HTTP health check for UptimeRobot/Render

## Requirements

- Python 3.10+
- Telegram bot (create with @BotFather)
- Your Telegram chat ID (get it with @userinfobot)

## Quick Start

```bash
cp .env.example .env
# Edit .env with your credentials:
#   TELEGRAM_BOT_TOKEN=your_token
#   TELEGRAM_CHAT_ID=your_chat_id
#   TESTFLIGHT_URL= (optional, auto-discovered)
pip install -r requirements.txt
python bot.py
```

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `TELEGRAM_BOT_TOKEN` | Yes | Your Telegram bot token |
| `TELEGRAM_CHAT_ID` | Yes | Your numeric chat ID |
| `TESTFLIGHT_URL` | No | TestFlight URL (auto-discovered if empty) |
| `WABETAINFO_URL` | No | WABetaInfo URL for link discovery |
| `MIN_INTERVAL` | No | Minimum interval between checks (default: 2s) |
| `MAX_INTERVAL` | No | Maximum interval between checks (default: 30s) |
| `URL_REFRESH_INTERVAL` | No | Seconds between URL refresh (default: 1800s) |
| `ERROR_THRESHOLD` | No | Errors before alerting (default: 3) |
| `POLL_INTERVAL` | No | Seconds between Telegram polling (default: 5) |
| `PORT` | No | Health check port (default: 8080) |

## How It Works

1. **Startup**: If no URL is configured, the bot automatically discovers it from WABetaInfo
2. **Main monitoring**: Every 2-30 seconds it checks the beta status on TestFlight
3. **URL updates**: Every 30 minutes it fetches the updated URL from WABetaInfo
4. **Notifications**: Sends a Telegram message as soon as a free slot is detected
5. **Commands**: `/status` to check the monitor status
6. **Alerts**: Automatic notifications when the bot detects consecutive errors

## Deployment

### Render (free)

1. Push the repo to GitHub
2. Create a web service on Render
3. Configure the environment variables in the dashboard
4. The bot deploys automatically

### UptimeRobot (free)

1. Create an account on UptimeRobot
2. Add an HTTP monitor pointing to your Render URL
3. Set up a ping every 5 minutes

## License

This project uses the [PolyForm Noncommercial License 1.0.0](LICENSE).
