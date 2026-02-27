# 🐳 Docker - NIP-05 Nostr Identifier

All Docker-related files are organized in this directory.

> 📖 [Versión en español → README.es.md](README.es.md)

---

## 📂 Structure

```
docker/
├── Dockerfile                      # Multi-stage container image
├── docker-compose.yml              # Local development
├── docker-compose.prod.yml         # Production with Nginx
├── .dockerignore                   # Build exclusions
├── Makefile                        # Make commands
├── scripts/
│   ├── docker-start.sh             # ⭐ Start (RECOMMENDED)
│   ├── docker-build.sh             # Build image manually
│   └── docker-stop.sh              # Stop application
├── nginx/
│   └── nginx.conf.example          # Nginx config for production
└── docs/
    ├── DOCKER_QUICK_START.en.md    # ⭐ Quick start guide
    └── DOCKER_FULL_GUIDE.en.md     # Full guide with troubleshooting
```

---

## 🚀 Quick Start

From the project root (`nip05/`):

```bash
# 1. Set up environment variables
cp .env.example .env
nano .env

# 2. Enter the docker directory
cd docker

# 3. Start the application (automated)
./scripts/docker-start.sh
```

**Done! The application will be available at http://localhost:8000**

---

## 📋 Available Commands

### Script (Recommended)
```bash
./scripts/docker-start.sh    # Start with automatic checks
./scripts/docker-stop.sh     # Stop and clean up
```

### Docker Compose
```bash
docker-compose up -d         # Start in background
docker-compose down          # Stop
docker-compose logs -f       # View logs in real time
docker-compose ps            # View container status
docker-compose restart       # Restart
```

### Makefile
```bash
make docker-start            # Start
make docker-stop             # Stop
make docker-logs             # View logs
make docker-rebuild          # Rebuild without cache
make docker-stats            # View resource usage
make help                    # List all available commands
```

---

## 📖 Documentation

| File | Description |
|---|---|
| [docs/DOCKER_QUICK_START.md](docs/DOCKER_QUICK_START.md) | Quick start in 3 steps |
| [docs/DOCKER_FULL_GUIDE.md](docs/DOCKER_FULL_GUIDE.md) | Full guide: configuration, security, production and troubleshooting |

---

## ✅ Verification

```bash
# Check the container is running
docker-compose ps

# Check health status
docker inspect nip05-app --format='{{.State.Health.Status}}'

# Test the endpoint
curl http://localhost:8000

# View logs
docker-compose logs -f
```

---

## 🔧 Configuration

### Environment Variables

Create the `.env` file at the **project root** (not inside `docker/`):

```env
LNBITS_URL=https://your-lnbits-instance.com
LNBITS_API_KEY=your_api_key_here
INVOICE_AMOUNT_SATS=100
DOMAIN=yourdomain.com
```

### Ports

| Environment | Port | URL |
|---|---|---|
| Development | 8000 | http://localhost:8000 |
| Production | 80 / 443 | http(s)://yourdomain.com |

---

## 🛑 Stopping the Application

```bash
# Using the script (recommended, offers optional cleanup)
./scripts/docker-stop.sh

# Or directly with docker-compose
docker-compose down
```

---

## 🐛 Common Issues

| Problem | Solution |
|---|---|
| Port 8000 in use | Change `"8000:8000"` to `"8001:8000"` in `docker-compose.yml` |
| `.env` not found | Run `cp .env.example .env` from the project root |
| Container keeps stopping | Check logs: `docker-compose logs nip05-app` |
| Changes not reflected | Rebuild: `docker-compose build --no-cache` |

---

## 📊 Container Specs

| Feature | Detail |
|---|---|
| Base image | `python:3.11-slim` |
| Build | Multi-stage (smaller final image) |
| User | `appuser` (non-root, UID 1000) |
| Health check | Every 30s via HTTP |
| CPU (development) | Max 1 core |
| RAM (development) | Max 512 MB |

---

## 🚀 Production

For a production deployment with Nginx and SSL:

```bash
# From the docker/ directory
docker-compose -f docker-compose.prod.yml up -d
```

Prerequisites:
1. SSL certificates in `ssl/`
2. Nginx configuration in `nginx/nginx.conf` (use `nginx.conf.example` as a base)
3. All environment variables set in `.env`

---

## 📚 Resources

- [Docker Official Documentation](https://docs.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [FastAPI with Docker](https://fastapi.tiangolo.com/deployment/docker/)

---

**Last updated:** 2026-02-26
