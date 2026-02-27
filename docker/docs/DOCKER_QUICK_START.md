# 🚀 Docker - Quick Start

> 📖 [Versión en español → DOCKER_QUICK_START.es.md](DOCKER_QUICK_START.es.md)

---

## 📂 Docker File Structure

```
nip05/
└── docker/
    ├── Dockerfile                  ← Multi-stage container image
    ├── docker-compose.yml          ← Local development
    ├── docker-compose.prod.yml     ← Production with Nginx
    ├── .dockerignore               ← Build exclusions
    ├── scripts/
    │   ├── docker-start.sh         ⭐ RECOMMENDED
    │   ├── docker-build.sh
    │   └── docker-stop.sh
    ├── nginx/
    │   └── nginx.conf.example
    └── docs/
        ├── DOCKER_QUICK_START.en.md  ← This file
        └── DOCKER_FULL_GUIDE.en.md
```

---

## ⚡ Quick Start (3 steps)

### 1️⃣ Set up environment variables

From the project root:

```bash
cp .env.example .env
nano .env
```

```env
LNBITS_URL=https://your-lnbits.com
LNBITS_API_KEY=your_api_key
INVOICE_AMOUNT_SATS=100
DOMAIN=yourdomain.com
```

### 2️⃣ Enter the docker directory

```bash
cd docker
```

### 3️⃣ Run the start script

```bash
./scripts/docker-start.sh
```

✨ **The application will be available at http://localhost:8000!**

The script automatically:
- Checks that Docker is installed
- Copies `.env.example` to `.env` if it does not exist
- Pulls the base image
- Builds the application image
- Starts the containers
- Confirms the service is running

---

## 📋 Common Commands

### From `docker/`:

```bash
# Start (recommended — automated script)
./scripts/docker-start.sh

# Or with docker-compose directly
docker-compose up -d

# View logs in real time
docker-compose logs -f

# View container status
docker-compose ps

# Stop
docker-compose down

# Stop with script (offers optional cleanup)
./scripts/docker-stop.sh
```

### From the project root:

```bash
make docker-start
make docker-stop
make docker-logs
make docker-rebuild
```

---

## ✅ Verification

```bash
# Check the container is running
docker-compose ps

# Check health status
docker inspect nip05-app --format='{{.State.Health.Status}}'

# Test the application
curl http://localhost:8000

# Test the API
curl http://localhost:8000/api/check-availability/test
```

---

## 🛑 Stopping the Application

```bash
# From docker/
./scripts/docker-stop.sh

# Or manually
docker-compose down
```

---

## 🐛 Quick Troubleshooting

| Problem | Solution |
|----------|----------|
| `docker: command not found` | Install Docker — see [DOCKER_FULL_GUIDE.md](DOCKER_FULL_GUIDE.md) |
| `Port 8000 already in use` | Change port in `docker-compose.yml`: `"8001:8000"` |
| `.env not found` | From project root: `cp .env.example .env` |
| Container keeps stopping | View logs: `docker-compose logs nip05-app` |
| Changes not reflected | Rebuild: `make docker-rebuild` |

---

## 🚀 Production

```bash
cd docker
docker-compose -f docker-compose.prod.yml up -d
```

Requirements:
- SSL certificates in `ssl/`
- Nginx configuration in `nginx/nginx.conf`
- All environment variables set

---

## 📖 More Information

- [DOCKER_FULL_GUIDE.md](DOCKER_FULL_GUIDE.md) — Full guide with security, production and detailed troubleshooting
- [../README.md](../README.md) — Docker directory README

---

**Last updated:** 2026-02-26
