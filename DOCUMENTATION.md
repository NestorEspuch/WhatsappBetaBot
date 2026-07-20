# WhatsApp Beta TestFlight Monitor Bot

Bot que monitoriza automáticamente la disponibilidad de la beta de **WhatsApp Messenger para iOS** en TestFlight y envía una notificación instantánea por Telegram cuando se abre un hueco.

## Cómo funciona

### Arquitectura de doble frecuencia

```
┌─────────────────────────────────────────────────────────┐
│  bucle PRINCIPAL (cada 2-30 segundos)                    │
│                                                          │
│  1. GET httpx → https://testflight.apple.com/join/XXXXXX │
│  2. Analiza el HTML de Apple                             │
│  3. Si reconoce "full" o "isn"+"accepting"+"tester" → lleno │
│  4. Si NO aparece → ¡HAY HUECO! → Telegram YA            │
│  5. Sleep random(2, 30) segundos                         │
└─────────────────────────────────────────────────────────┘
                        │
┌─────────────────────────────────────────────────────────┐
│  bucle SECUNDARIO (cada 30 minutos)                      │
│                                                          │
│  1. GET httpx → https://wabetainfo.com/wa-testflight/    │
│  2. Busca testflight.apple.com/join/XXXXXXXX en el HTML  │
│  3. Si la URL cambió → actualiza la variable principal   │
│  4. Notifica por Telegram del cambio de URL              │
└─────────────────────────────────────────────────────────┘
```

### Detección de estado

El bot analiza el HTML que devuelve Apple en la URL de TestFlight:

| Estado | Detección |
|--------|-----------|
| **Abierto** | El HTML *no* contiene "This beta is full" ni los substrings "isn" + "accepting" + "tester" (cualquier contenido desconocido se asume abierto — preferimos falso positivo a perder un slot) |
| **Lleno** | El HTML contiene "This beta is full" O los substrings "isn" + "accepting" + "tester" (funciona aunque Apple escape el apóstrofe como `&#39;`) |
| **Cerrado** | La URL responde 404 (el enlace ya no existe) |
| **Desconocido** | Error de red o timeout |

### Anti-bloqueo

Apple no bloquea estas peticiones porque son las mismas que hace cualquier usuario al abrir el link en el navegador. Aun así, el bot implementa:

- **Intervalo aleatorio** 2-30 segundos (sin patrón fijo)
- **Rotación de User-Agent** (7 perfiles distintos: iPhone, Mac, Windows, Android)
- **Timeout** de 15 segundos por petición
- **Conexiones reutilizadas** (HTTP connection pooling)
- La frecuencia media es de ~2 peticiones/minuto — tráfico insignificante

## Requisitos

- Python 3.10 o superior
- Una cuenta de Telegram
- Una cuenta gratuita en [Render](https://render.com)
- (Opcional) Una cuenta gratuita en [UptimeRobot](https://uptimerobot.com)

## Configuración

### 1. Crear el bot de Telegram

1. Abre Telegram y busca [@BotFather](https://t.me/BotFather)
2. Envía `/newbot` y sigue las instrucciones
3. Guarda el **token** que te da (algo como `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`)
4. Busca [@userinfobot](https://t.me/userinfobot) y envíale `/start`
5. Te dará tu **Chat ID** numérico (algo como `123456789`)

### 2. Registrar los comandos del bot

Para que el bot responda a `/status`, registra los comandos con @BotFather:

1. Abre Telegram y busca [@BotFather](https://t.me/BotFather)
2. Envía: `/setcommands`
3. Selecciona tu bot
4. Envía la siguiente lista (una línea por comando):
   ```
   status - Ver estado del monitor
   ```
5. @BotFather confirmará con "Success!"

### 3. Sistema de alertas de errores

El bot monitoriza su propio estado y te avisa si algo va mal:

- **3+ errores consecutivos** → Telegram con el error completo
- **Recuperación** → Telegram cuando vuelve a funcionar
- **Errores esporádicos** (1 sí, 1 no) → **no** se notifica (sin spam)

### 4. Comando `/status`

Puedes consultar el estado del bot en cualquier momento enviando `/status` al bot de Telegram. Responde con:

```
WhatsApp Beta Monitor

URL: https://testflight.apple.com/join/YcmGWyxV
Slot: full
Ultimo cambio: hace 12h 30min
Peticiones totales: 4,231
Errores consecutivos: 0
Max errores seguidos: 0
Errores ultima hora: 0
Ultimo refresh URL: hace 3 min
Uptime: 2 dias 7h 31m
Health: OK
```

Los indicadores de estado:

| Indicador | Estado |
|-----------|--------|
| 🟢 | Hueco libre |
| 🔴 | Beta llena |
| ⚫ | Beta cerrada (404) |
| ⚪ | Estado desconocido |
| OK | Bot funcionando correctamente |
| CAIDO | Errores consecutivos detectados |

### 5. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto (nunca lo subas a Git):

```bash
cp .env.example .env
```

Edita `.env` con tus valores:

```
TELEGRAM_BOT_TOKEN=123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11
TELEGRAM_CHAT_ID=123456789
```

El resto de variables tienen valores por defecto que funcionan sin cambios.

### 6. Probar localmente

```bash
pip install -r requirements.txt
python bot.py
```

Deberías ver logs como:

```
2026-07-18 12:00:00 [INFO] WhatsApp Beta Monitor started
2026-07-18 12:00:00 [INFO] Initial URL: https://testflight.apple.com/join/YcmGWyxV
2026-07-18 12:00:01 [INFO] Initial status: full
2026-07-18 12:00:31 [INFO] Check #1: full
2026-07-18 12:00:31 [INFO] Next check in ~17s
2026-07-18 12:00:51 [INFO] Health check: GET /health 200 -
2030-01-15 18:00:00 [INFO] Refreshing TestFlight URL from WABetaInfo...
2030-01-15 18:00:02 [INFO] URL confirmed: https://testflight.apple.com/join/YcmGWyxV
```

### 7. Desplegar en Render (gratis)

#### Opción A: Manual

1. Sube el repositorio a **GitHub**
2. En [Render Dashboard](https://dashboard.render.com), crea un **New Web Service**
3. Conecta tu repositorio de GitHub
4. Configura:
   - **Runtime**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
   - **Plan**: `Free`
5. Añade las variables de entorno en el panel de Render:
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Crea el servicio

#### Opción B: Blueprint (render.yaml)

Si incluyes `render.yaml` en el repo, Render lo detecta automáticamente:

1. Sube el repositorio a GitHub
2. En Render Dashboard → **New Blueprint**
3. Conecta el repositorio
4. Render lee `render.yaml` y configura todo solo
5. Añade las variables de entorno que faltan en el panel

### 8. Mantener despierto con UptimeRobot

Render duerme los servicios gratuitos tras 15 minutos sin actividad. Para evitarlo:

1. Crea cuenta en [UptimeRobot](https://uptimerobot.com) (gratis)
2. **Add New Monitor**:
   - **Monitor Type**: HTTP(s)
   - **Friendly Name**: `WA Beta Bot`
   - **URL**: `https://tu-app.onrender.com/health`
   - **Interval**: `5 minutes`
3. Guardar

UptimeRobot hará ping al `/health` del bot cada 5 minutos, evitando que Render lo duerma.

## Variables de entorno

| Variable | Obligatoria | Por defecto | Descripción |
|----------|-------------|-------------|-------------|
| `TELEGRAM_BOT_TOKEN` | ✅ | — | Token del bot de Telegram (de @BotFather) |
| `TELEGRAM_CHAT_ID` | ✅ | — | Tu Chat ID numérico de Telegram |
| `TESTFLIGHT_URL` | ❌ | `https://testflight.apple.com/join/YcmGWyxV` | URL por defecto de la beta (se auto-descubre y actualiza) |
| `WABETAINFO_URL` | ❌ | `https://wabetainfo.com/wa-testflight/` | URL de WABetaInfo para descubrir el link actual |
| `MIN_INTERVAL` | ❌ | `2` | Segundos mínimos entre peticiones a Apple |
| `MAX_INTERVAL` | ❌ | `30` | Segundos máximos entre peticiones a Apple |
| `URL_REFRESH_INTERVAL` | ❌ | `1800` | Segundos entre refrescos de URL desde WABetaInfo (1800 = 30 min) |
| `ERROR_THRESHOLD` | ❌ | `3` | Errores consecutivos para disparar alerta por Telegram |
| `POLL_INTERVAL` | ❌ | `5` | Segundos entre polling de comandos de Telegram |
| `PORT` | ❌ | `8080` | Puerto del servidor HTTP para health checks |

## Preguntas frecuentes

### ¿Cada cuánto comprueba la beta?

Cada **2-30 segundos** con un intervalo aleatorio (sin patrón fijo) para evitar que Apple pueda detectar y bloquear el bot.

### ¿Cómo sabe la URL si WhatsApp la cambia?

Cada **30 minutos**, el bot visita `wabetainfo.com/wa-testflight/` y extrae la URL actual de TestFlight. Si WhatsApp cambia el enlace (crea un nuevo grupo beta), WABetaInfo lo refleja y el bot lo detecta automáticamente.

### ¿Puede Apple bloquearme la IP?

No. El bot hace ~2 peticiones por minuto, lo mismo que haría un usuario mirando el link manualmente. Apple no bloquea por esto.

### ¿Render no se duerme?

Render duerme los servicios gratuitos a los 15 minutos si no reciben tráfico. Por eso incluimos:
1. El endpoint `/health` en el bot
2. UptimeRobot haciendo ping cada 5 minutos

Así el bot está activo 24/7.

### ¿El bot avisa si algo falla?

Sí. Si hay **3 o más errores consecutivos** (p.ej. Apple devuelve 503, timeout de red), el bot envía un Telegram con el error. Cuando se recupera, envía otro aviso. Si los fallos son esporádicos (1 sí, 1 no), no molesta con notificaciones.

### ¿Para qué sirve el comando `/status`?

Envía `/status` al bot de Telegram y te responde con información completa: URL monitorizada, estado del slot, peticiones totales, errores consecutivos, uptime, etc. Así puedes saber si el bot funciona sin necesidad de mirar los logs de Render.

### ¿Y si WABetaInfo está caído?

El bot simplemente mantiene la última URL conocida y sigue monitorizando. Cuando WABetaInfo vuelva, se actualizará solo.

### ¿Se puede monitorizar más de una app?

El bot está enfocado en WhatsApp Messenger. Para monitorizar varias URLs, se puede modificar fácilmente. El diseño está pensado para ser simple.

## Notas importantes

- La beta de WhatsApp para iOS tiene un límite de **10.000 testers**
- Los huecos se abren cuando alguien abandona el programa o WhatsApp amplía el cupo
- Cuando recibas la notificación, **abre el link en tu iPhone inmediatamente** — los huecos se llenan en minutos
- Una vez dentro de la beta, recibirás automáticamente las builds futuras mientras no estés inactivo
- **Nadie debe cobrarte por acceso a la beta**. Cualquier oferta de pago es una estafa
