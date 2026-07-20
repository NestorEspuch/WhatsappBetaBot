# WhatsApp Beta Monitor

Bot que monitoriza automáticamente la disponibilidad de la **beta de WhatsApp Messenger para iOS** en TestFlight y te avisa por Telegram al instante cuando se abre un hueco.

## Cómo funciona

- **Cada 2-30s** consulta el estado de la beta en TestFlight
- **Cada 30 min** obtiene la URL actualizada desde WABetaInfo (si WhatsApp cambia el link, el bot lo detecta solo)
- Envía un Telegram en cuanto detecta un hueco libre
- Comando `/status` para consultar el estado del monitor
- Alertas automáticas si el bot detecta errores consecutivos

## Inicio rápido

```bash
cp .env.example .env
# Edita .env con tu TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID
pip install -r requirements.txt
python bot.py
```

## Despliegue

Render (gratis) + UptimeRobot (gratis) → 24/7 sin coste.

Ver [DOCUMENTATION.md](DOCUMENTATION.md) para la guía completa de configuración y despliegue.
