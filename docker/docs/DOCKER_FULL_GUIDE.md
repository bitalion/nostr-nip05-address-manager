# 🐳 Docker - Full Guide

Complete guide to deploy the NIP-05 application using Docker and Docker Compose.

> 📖 [Versión en español → DOCKER_FULL_GUIDE.es.md](DOCKER_FULL_GUIDE.es.md)

---

## 📋 Prerequisites

- Docker >= 20.10
- Docker Compose >= 1.29
- Git

### Installing Docker

**Ubuntu / Debian:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

**macOS (with Homebrew):**
```bash
brew install --cask docker
```

**Windows:**
Download and install [Docker Desktop](https://www.docker.com/products/docker-desktop)

---

## 🚀 Quick Start

### 1. Clone the repository
```bash
git clone https://github.com/your-user/nip05.git
cd nip05
```

### 2. Configure environment variables
```bash
cp .env.example .env
nano .env
```

### 3. Start the application
```bash
# Option A: Automated script (recommended)
cd docker
./scripts/docker-start.sh

# Option B: Docker Compose directly
cd docker
docker-compose up -d
```

### 4. Check the status
```bash
docker-compose ps
docker-compose logs -f
```

### 5. Open the application
Open your browser at: **http://localhost:8000**

---

## 📝 Configuration

### Environment Variables (.env)

```env
# LNbits — Lightning payment provider
LNBITS_URL=https://your-lnbits-instance.com
LNBITS_API_KEY=your_api_key_here

# Application
INVOICE_AMOUNT_SATS=100
DOMAIN=yourdomain.com
```

### Changing the Port

Edit `docker-compose.yml`:
```yaml
ports:
  - "8080:8000"  # Access at http://localhost:8080
```

### Volume Structure

```
/
├── data/
│   └── .well-known/     # Persistent NIP-05 registry
├── static/
│   └── images/          # Static images
└── templates/           # HTML templates (hot-reload in development)
```

Volumes are mounted automatically from `docker-compose.yml`. Data in `data/` persists across restarts.

---

## 🔧 Management Commands

### Lifecycle

```bash
# Start in background
docker-compose up -d

# Stop (keeps volumes)
docker-compose down

# Restart without rebuilding
docker-compose restart

# View status
docker-compose ps

# Stream logs
docker-compose logs -f nip05-app

# View last 100 lines of logs
docker-compose logs --tail=100
```

### Building

```bash
# Build image
docker-compose build

# Rebuild without cache (useful when updating dependencies)
docker-compose build --no-cache

# Build and start in a single step
docker-compose up -d --build
```

### Maintenance

```bash
# Open a shell inside the container
docker exec -it nip05-app bash

# Remove containers and volumes (irreversible!)
docker-compose down -v

# Clean up unused images
docker image prune -f

# View resource usage
docker stats nip05-app
```

---

## 🧰 Utility Scripts

### `scripts/docker-start.sh`

Starts the application with full automated checks:
- Detects whether Docker is installed
- Copies `.env.example` → `.env` if missing
- Pulls base image
- Builds the application image
- Starts the containers
- Waits and confirms the service is responding

```bash
cd docker
./scripts/docker-start.sh
```

### `scripts/docker-stop.sh`

Stops containers with optional cleanup:

```bash
cd docker
./scripts/docker-stop.sh
```

### `scripts/docker-build.sh`

Builds the image manually with a custom name and tag:

```bash
cd docker
./scripts/docker-build.sh [name] [tag]
./scripts/docker-build.sh nip05-app v1.2.0
```

---

## 🔍 Troubleshooting

### Container exits immediately

```bash
# View full logs
docker-compose logs nip05-app

# Common causes:
# - Missing environment variables in .env
# - Port 8000 already in use
# - Application syntax error
```

### Port 8000 in use

```bash
# Find the process using the port
lsof -i :8000        # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Solution: change the external port in docker-compose.yml
ports:
  - "8001:8000"
```

### Docker permission issues

```bash
# Add user to the docker group (Linux)
sudo usermod -aG docker $USER
newgrp docker

# If it persists, restart the Docker daemon
sudo systemctl restart docker
```

### Stale image after code changes

```bash
# Rebuild ignoring cache
docker-compose build --no-cache
docker-compose up -d
```

### Verify LNbits connectivity

```bash
# Built-in diagnostic endpoint
curl http://localhost:8000/api/debug/lnbits-test
```

---

## 🔐 Security

### Best Practices

1. **Never commit your `.env` file**
   - `.env` is already in `.gitignore`
   - Use `docker secrets` for Docker Swarm environments

2. **Always use HTTPS in production**
   - Set up a reverse proxy (Nginx, Caddy, Traefik)
   - Get free certificates from [Let's Encrypt](https://letsencrypt.org/)

3. **Limit container resources**
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '1'
         memory: 512M
   ```

4. **The container already runs as a non-root user** (`appuser`, UID 1000)

5. **Keep the image up to date**
   ```bash
   docker-compose build --no-cache
   ```

### Nginx Configuration for Production

```nginx
server {
    listen 443 ssl http2;
    server_name yourdomain.com;

    ssl_certificate     /etc/nginx/ssl/cert.pem;
    ssl_certificate_key /etc/nginx/ssl/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    location / {
        proxy_pass         http://nip05-app:8000;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

# Redirect HTTP to HTTPS
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}
```

---

## 📊 Monitoring

### Health Check

The container checks its own health every 30 seconds:

```bash
# Status: healthy / unhealthy / starting
docker inspect nip05-app --format='{{.State.Health.Status}}'

# Health check history
docker inspect nip05-app --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### Resource Metrics

```bash
# Real-time CPU and memory usage
docker stats nip05-app

# Detailed container information
docker inspect nip05-app
```

---

## 🚀 Production Deployment

### VPS (DigitalOcean, Linode, Hetzner, AWS, etc.)

```bash
# 1. SSH into your server
ssh root@your-server.com

# 2. Install Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 3. Clone the repository
git clone https://github.com/your-user/nip05.git
cd nip05

# 4. Configure environment
cp .env.example .env
nano .env

# 5. Start with production profile
cd docker
docker-compose -f docker-compose.prod.yml up -d

# 6. Configure firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### With Docker Swarm (Multi-node)

```bash
# Initialize the swarm on the manager node
docker swarm init

# Deploy the stack
docker stack deploy -c docker-compose.yml nip05

# View services
docker service ls
```

---

## 🔄 Updates

```bash
# 1. Pull latest changes
git pull origin main

# 2. Rebuild the image
docker-compose build --no-cache

# 3. Restart with the new image
docker-compose up -d

# 4. Verify everything is OK
docker-compose ps
docker-compose logs --tail=50
```

---

## 📚 Additional Resources

- [Docker Official Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [FastAPI with Docker](https://fastapi.tiangolo.com/deployment/docker/)
- [Docker Best Practices](https://docs.docker.com/develop/dev-best-practices/)
- [Let's Encrypt (free SSL)](https://letsencrypt.org/)

---

## ❓ Support

1. Check the logs: `docker-compose logs -f`
2. Review the Troubleshooting section above
3. Open an issue in the GitHub repository

---

**Last updated:** 2026-02-18
