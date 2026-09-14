# WhatsApp Beta Monitor

Bot que monitoriza automaticamente la disponibilidad de la **beta de WhatsApp Messenger para iOS** en TestFlight y te avisa por Telegram cuando se abre un hueco.

## Caracteristicas

- Monitoreo cada 2-30 segundos con intervalo aleatorio
- Auto-descubrimiento de URL desde WABetaInfo (cada 30 min)
- Notificaciones instantaneas por Telegram
- Comando `/status` para consultar el estado
- Alertas automaticas si el bot falla
- Health check HTTP para UptimeRobot/Render

## Requisitos

- Python 3.10+
- Bot de Telegram (crear con @BotFather)
- Tu chat ID de Telegram (obtener con @userinfobot)

## Inicio rapido

```bash
cp .env.example .env
# Edita .env con tus credenciales:
#   TELEGRAM_BOT_TOKEN=tu_token
#   TELEGRAM_CHAT_ID=tu_chat_id
#   TESTFLIGHT_URL= (opcional, se auto-descubre)
pip install -r requirements.txt
python bot.py
```

## Variables de entorno

| Variable | Obligatoria | Descripcion |
|----------|-------------|-------------|
| `TELEGRAM_BOT_TOKEN` | Si | Token de tu bot de Telegram |
| `TELEGRAM_CHAT_ID` | Si | Tu chat ID numerico |
| `TESTFLIGHT_URL` | No | URL de TestFlight (se auto-descubre si esta vacia) |
| `WABETAINFO_URL` | No | URL de WABetaInfo para descubrir enlaces |
| `MIN_INTERVAL` | No | Intervalo minimo entre chequeos (default: 2s) |
| `MAX_INTERVAL` | No | Intervalo maximo entre chequeos (default: 30s) |
| `URL_REFRESH_INTERVAL` | No | Segundos entre refresh de URL (default: 1800s) |
| `ERROR_THRESHOLD` | No | Errores antes de alertar (default: 3) |
| `POLL_INTERVAL` | No | Segundos entre polling de Telegram (default: 5) |
| `PORT` | No | Puerto del health check (default: 8080) |

## Como funciona

1. **Arranque**: Si no hay URL configurada, el bot la descubre automaticamente desde WABetaInfo
2. **Monitoreo principal**: Cada 2-30 segundos consulta el estado de la beta en TestFlight
3. **Actualizacion de URL**: Cada 30 minutos obtiene la URL actualizada desde WABetaInfo
4. **Notificaciones**: Envia un Telegram en cuanto detecta un hueco libre
5. **Comandos**: `/status` para consultar el estado del monitor
6. **Alertas**: Notificaciones automaticas si el bot detecta errores consecutivos

## Despliegue

### Render (gratis)

1. Sube el repo a GitHub
2. Crea un servicio web en Render
3. Configura las variables de entorno en el dashboard
4. El bot se despliega automaticamente

### UptimeRobot (gratis)

1. Crea una cuenta en UptimeRobot
2. Anade un monitor HTTP apuntando a tu URL de Render
3. Configura un ping cada 5 minutos

## Licencia

Este proyecto utiliza la [PolyForm Noncommercial License 1.0.0](LICENSE).
