# NIP-05 Registration Service

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](docker/)

Servicio de registro de identificadores [NIP-05](https://github.com/nostr-protocol/nips/blob/master/05.md) para Nostr con pagos Lightning integrados a través de LNbits.

> 📖 [English version → README.md](README.md)

---

## ¿Qué es NIP-05?

NIP-05 permite asociar una clave pública de Nostr (`npub...`) con un identificador legible tipo email (`usuario@dominio.com`). Los clientes Nostr verifican esta asociación consultando `https://dominio.com/.well-known/nostr.json`.

## Características

- ✅ Registro de identificadores NIP-05 vía pagos Lightning
- ✅ Interfaz web bilingüe (español / inglés)
- ✅ Verificación automática de pagos (polling cada 2s)
- ✅ Conversión automática npub → hex
- ✅ Detección de claves públicas duplicadas
- ✅ Diseño responsive (móvil, tablet, desktop)
- ✅ Containerizado con Docker

---

## Arquitectura

```
/
├── main.py                      # App factory, middlewares, startup/shutdown
├── config.py                    # Variables de entorno y constantes de rutas
├── schemas.py                   # Modelos Pydantic de request/response
│
├── db/
│   ├── connection.py            # Pool de BD (get_db, init_db)
│   ├── records.py               # CRUD sobre la tabla records
│   └── users.py                 # CRUD sobre users + tokens de reset
│
├── core/
│   ├── security.py              # Hash de contraseñas, auth de tokens, Depends
│   ├── nostr.py                 # Conversión npub, gestión de nostr.json
│   └── email.py                 # Envío de correos
│
├── services/
│   └── payments.py              # Integración con LNbits API
│
├── routers/
│   ├── public.py                # Rutas públicas (/, /health, /api/*)
│   ├── nip05.py                 # Rutas de registro y pago
│   ├── admin_auth.py            # Auth admin, reset de contraseña, perfil
│   └── admin_records.py         # CRUD admin para registros y usuarios
│
├── templates/
│   ├── index.html               # Frontend público de registro
│   └── manage.html              # Panel de administración
├── static/
│   └── images/                  # Recursos estáticos
├── .well-known/
│   └── nostr.json               # Registro de identidades NIP-05
├── docker/
│   ├── Dockerfile               # Imagen multi-stage Python 3.11
│   ├── docker-compose.yml       # Orquestación de servicios (desarrollo)
│   ├── docker-compose.prod.yml  # Configuración de producción con Nginx
│   ├── scripts/                 # Scripts de gestión
│   └── docs/                    # Documentación Docker
├── requirements.txt
├── Makefile                     # Atajos para Docker
├── .env.example                 # Plantilla de variables de entorno
└── .env                         # Variables de entorno (no versionado)
```

---

## Requisitos

- Python 3.11+
- Cuenta en [LNbits](https://lnbits.com/) (u otra instancia compatible) con API key

---

## Configuración

### 1. Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/nip05.git
cd nip05
```

### 2. Crear archivo `.env`

```bash
cp .env.example .env
nano .env
```

```env
LNBITS_URL=https://tu-instancia-lnbits.com
LNBITS_API_KEY=tu_api_key_aqui
INVOICE_AMOUNT_SATS=2000
DOMAIN=tudominio.com
```

| Variable | Descripción | Default |
|---|---|---|
| `LNBITS_URL` | URL de la instancia LNbits | — |
| `LNBITS_API_KEY` | API key de LNbits (invoice/read) | — |
| `INVOICE_AMOUNT_SATS` | Costo del registro en satoshis | `100` |
| `DOMAIN` | Dominio para los identificadores NIP-05 | `example.com` |

---

## Ejecución

### Local

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker (recomendado)

```bash
# Iniciar
make docker-start

# Detener
make docker-stop

# Ver logs
make docker-logs

# Reconstruir imagen
make docker-rebuild
```

El contenedor expone el puerto `8000`. Los volúmenes montan `data/.well-known`, `static/` y `templates/` para persistencia entre reinicios.

> 📖 Ver [docker/README.es.md](docker/README.es.md) para la guía completa de Docker.

---

## API Endpoints

### Públicos

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Página de registro (frontend) |
| `GET` | `/.well-known/nostr.json` | Archivo NIP-05 (consultado por clientes Nostr) |
| `GET` | `/api/check-availability/{username}` | Verificar disponibilidad de nombre de usuario |

### Registro

| Método | Ruta | Descripción |
|---|---|---|
| `POST` | `/api/check-pubkey` | Convertir npub a hex y verificar si ya está registrada |
| `POST` | `/api/convert-pubkey` | Convertir npub a formato hexadecimal |
| `POST` | `/api/create-invoice` | Crear factura Lightning para el registro |
| `POST` | `/api/check-payment` | Verificar estado del pago y registrar si fue exitoso |
| `POST` | `/api/register` | Registro directo (sin pago) |

### Ejemplos cURL

**Verificar disponibilidad:**
```bash
curl https://tudominio.com/api/check-availability/alice
# {"available": true}
```

**Verificar clave pública:**
```bash
curl -X POST https://tudominio.com/api/check-pubkey \
  -H "Content-Type: application/json" \
  -d '{"pubkey": "npub1..."}'
# {"hex": "abc123...", "registered": false}
```

**Crear factura Lightning:**
```bash
curl -X POST https://tudominio.com/api/create-invoice \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "pubkey": "npub1..."}'
# {"payment_request": "lnbc...", "payment_hash": "...", "amount_sats": 2000}
```

---

## Flujo de Registro

```
1. Usuario ingresa nombre de usuario
   └─> GET /api/check-availability/{username}
       └─> Respuesta: disponible o no

2. Usuario ingresa clave pública (npub)
   └─> POST /api/check-pubkey
       └─> Respuesta: hex + si ya está registrada

3. Usuario envía formulario
   └─> POST /api/create-invoice
       └─> Respuesta: factura Lightning (bolt11)

4. Se muestra QR de la factura
   └─> Polling cada 2s: POST /api/check-payment
       └─> Si pagado: escribe en .well-known/nostr.json

5. Registro completado: usuario@dominio.com
```

---

## Frontend

- **Bilingüe**: inglés / español (switch en la interfaz)
- **Responsive**: adaptado a móvil, tablet y desktop
- **Validaciones en tiempo real**:
  - Disponibilidad de username (debounce 300ms)
  - Conversión automática npub → hex
  - Detección de clave pública duplicada
- **Campo hex**: oculto por defecto, visible al hacer clic en "Hex"
- **QR de pago**: generado con QRious, verificación automática cada 2 segundos
- **Stack**: Tailwind CSS (CDN), Font Awesome, QRious

---

## Archivo nostr.json

El archivo `.well-known/nostr.json` sigue el estándar NIP-05:

```json
{
  "names": {
    "alice": "abc123def456...clave_hex_64_caracteres"
  }
}
```

Los clientes Nostr consultan `https://dominio.com/.well-known/nostr.json?name=alice` para verificar la identidad.

---

## Stack Tecnológico

| Componente | Tecnología |
|---|---|
| Backend | FastAPI + Uvicorn |
| Frontend | HTML + Tailwind CSS + Vanilla JS |
| Pagos | LNbits API (Lightning Network) |
| Encoding | bech32 (npub → hex) |
| Contenedor | Docker + docker-compose |
| Validación | Pydantic v2 |

---

## Licencia

MIT
