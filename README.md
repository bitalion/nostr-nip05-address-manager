# NIP-05 Registration Service

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Docker](https://img.shields.io/badge/Docker-ready-blue.svg)](docker/)

A [NIP-05](https://github.com/nostr-protocol/nips/blob/master/05.md) identifier registration service for Nostr with integrated Lightning payments via LNbits.

> 📖 [Versión en español → README.es.md](README.es.md)

---

## What is NIP-05?

NIP-05 lets you associate a Nostr public key (`npub...`) with a human-readable, email-like identifier (`user@domain.com`). Nostr clients verify this association by querying `https://domain.com/.well-known/nostr.json`.

## Features

- ✅ NIP-05 identifier registration via Lightning payments
- ✅ Bilingual web interface (English / Spanish)
- ✅ Automatic payment verification (2s polling)
- ✅ Automatic npub → hex conversion
- ✅ Duplicate public key detection
- ✅ Fully responsive design (mobile, tablet, desktop)
- ✅ Docker-ready

---

## Architecture

```
/
├── main.py                      # App factory, middlewares, startup/shutdown
├── config.py                    # Environment variables and path constants
├── schemas.py                   # Pydantic request/response models
│
├── db/
│   ├── connection.py            # DB pool (get_db, init_db)
│   ├── records.py               # CRUD operations on the records table
│   └── users.py                 # CRUD on users + password reset tokens
│
├── core/
│   ├── security.py              # Password hashing, token auth, Depends
│   ├── nostr.py                 # npub conversion, nostr.json management
│   └── email.py                 # Email sending
│
├── services/
│   └── payments.py              # LNbits API integration
│
├── routers/
│   ├── public.py                # Public routes (/, /health, /api/*)
│   ├── nip05.py                 # Registration & payment routes
│   ├── admin_auth.py            # Admin auth, password reset, profile
│   └── admin_records.py         # Admin CRUD for records and users
│
├── templates/
│   ├── index.html               # Public registration frontend
│   └── manage.html              # Admin panel
├── static/
│   └── images/                  # Static assets
├── .well-known/
│   └── nostr.json               # NIP-05 identity registry
├── docker/
│   ├── Dockerfile               # Multi-stage Python 3.11 image
│   ├── docker-compose.yml       # Service orchestration (development)
│   ├── docker-compose.prod.yml  # Production configuration with Nginx
│   ├── scripts/                 # Management scripts
│   └── docs/                    # Docker documentation
├── requirements.txt
├── Makefile                     # Docker shortcuts
├── .env.example                 # Environment variable template
└── .env                         # Environment variables (not versioned)
```

---

## Requirements

- Python 3.11+
- A [LNbits](https://lnbits.com/) account (or compatible instance) with an API key

---

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-user/nip05.git
cd nip05
```

### 2. Create the `.env` file

```bash
cp .env.example .env
nano .env
```

```env
LNBITS_URL=https://your-lnbits-instance.com
LNBITS_API_KEY=your_api_key_here
INVOICE_AMOUNT_SATS=2000
DOMAIN=yourdomain.com
```

| Variable | Description | Default |
|---|---|---|
| `LNBITS_URL` | LNbits instance URL | — |
| `LNBITS_API_KEY` | LNbits API key (invoice/read) | — |
| `INVOICE_AMOUNT_SATS` | Registration cost in satoshis | `100` |
| `DOMAIN` | Domain for NIP-05 identifiers | `example.com` |

---

## Running

### Local

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker (recommended)

```bash
# Start
make docker-start

# Stop
make docker-stop

# View logs
make docker-logs

# Rebuild image
make docker-rebuild
```

The container exposes port `8000`. Volumes mount `data/.well-known`, `static/`, and `templates/` for persistence across restarts.

> 📖 See [docker/README.md](docker/README.md) for the full Docker guide.

---

## API Endpoints

### Public

| Method | Route | Description |
|---|---|---|
| `GET` | `/` | Registration page (frontend) |
| `GET` | `/.well-known/nostr.json` | NIP-05 file (queried by Nostr clients) |
| `GET` | `/api/check-availability/{username}` | Check username availability |

### Registration

| Method | Route | Description |
|---|---|---|
| `POST` | `/api/check-pubkey` | Convert npub to hex and check if already registered |
| `POST` | `/api/convert-pubkey` | Convert npub to hexadecimal format |
| `POST` | `/api/create-invoice` | Create Lightning invoice for registration |
| `POST` | `/api/check-payment` | Verify payment status and register if successful |
| `POST` | `/api/register` | Direct registration (no payment required) |

### cURL Examples

**Check availability:**
```bash
curl https://yourdomain.com/api/check-availability/alice
# {"available": true}
```

**Check public key:**
```bash
curl -X POST https://yourdomain.com/api/check-pubkey \
  -H "Content-Type: application/json" \
  -d '{"pubkey": "npub1..."}'
# {"hex": "abc123...", "registered": false}
```

**Create Lightning invoice:**
```bash
curl -X POST https://yourdomain.com/api/create-invoice \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "pubkey": "npub1..."}'
# {"payment_request": "lnbc...", "payment_hash": "...", "amount_sats": 2000}
```

---

## Registration Flow

```
1. User enters username
   └─> GET /api/check-availability/{username}
       └─> Response: available or not

2. User enters public key (npub)
   └─> POST /api/check-pubkey
       └─> Response: hex + whether already registered

3. User submits the form
   └─> POST /api/create-invoice
       └─> Response: Lightning invoice (bolt11)

4. QR code is displayed
   └─> Polling every 2s: POST /api/check-payment
       └─> If paid: writes to .well-known/nostr.json

5. Registration complete: user@domain.com
```

---

## Frontend

- **Bilingual**: English / Spanish (toggle in the UI)
- **Responsive**: mobile, tablet, and desktop ready
- **Real-time validations**:
  - Username availability (300ms debounce)
  - Automatic npub → hex conversion
  - Duplicate public key detection
- **Hex field**: hidden by default, shown on "Hex" link click
- **Payment QR**: generated with QRious, auto-verified every 2 seconds
- **Stack**: Tailwind CSS (CDN), Font Awesome, QRious

---

## nostr.json File

The `.well-known/nostr.json` file follows the NIP-05 standard:

```json
{
  "names": {
    "alice": "abc123def456...64_char_hex_key"
  }
}
```

Nostr clients query `https://domain.com/.well-known/nostr.json?name=alice` to verify the identity.

---

## Tech Stack

| Component | Technology |
|---|---|
| Backend | FastAPI + Uvicorn |
| Frontend | HTML + Tailwind CSS + Vanilla JS |
| Payments | LNbits API (Lightning Network) |
| Encoding | bech32 (npub → hex) |
| Container | Docker + docker-compose |
| Validation | Pydantic v2 |

---

## License

MIT
