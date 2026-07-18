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
│  3. Si aparece "This beta is full" → está lleno          │
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
| **Abierto** | El HTML *no* contiene "This beta is full" |
| **Lleno** | El HTML contiene "This beta is full" o "This beta isn't accepting any new testers right now" |
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

### 2. Configurar variables de entorno

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

### 3. Probar localmente

```bash
pip install -r requirements.txt
python bot.py
```

Deberías ver logs como:

```
2026-07-18 12:00:00 [INFO] WhatsApp Beta Monitor started
2026-07-18 12:00:00 [INFO] Initial URL: https://testflight.apple.com/join/YcmGWyxV
2026-07-18 12:00:01 [INFO] Initial status: full
2026-07-18 12:00:31 [DEBUG] Status: full
```

### 4. Desplegar en Render (gratis)

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

### 5. Mantener despierto con UptimeRobot

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
