# 🐳 Docker - Guía Completa

Guía completa para desplegar la aplicación NIP-05 usando Docker y Docker Compose.

> 📖 [English version → DOCKER_FULL_GUIDE.md](DOCKER_FULL_GUIDE.md)

---

## 📋 Requisitos Previos

- Docker >= 20.10
- Docker Compose >= 1.29
- Git

### Instalación de Docker

**Ubuntu / Debian:**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker
```

**macOS (con Homebrew):**
```bash
brew install --cask docker
```

**Windows:**
Descargar e instalar [Docker Desktop](https://www.docker.com/products/docker-desktop)

---

## 🚀 Inicio Rápido

### 1. Clonar el repositorio
```bash
git clone https://github.com/tu-usuario/nip05.git
cd nip05
```

### 2. Configurar variables de entorno
```bash
cp .env.example .env
nano .env
```

### 3. Iniciar la aplicación
```bash
# Opción A: Script automatizado (recomendado)
cd docker
./scripts/docker-start.sh

# Opción B: Docker Compose directamente
cd docker
docker-compose up -d
```

### 4. Verificar el estado
```bash
docker-compose ps
docker-compose logs -f
```

### 5. Acceder a la aplicación
Abre tu navegador en: **http://localhost:8000**

---

## 📝 Configuración

### Variables de Entorno (.env)

```env
# LNbits — Proveedor de pagos Lightning
LNBITS_URL=https://tu-instancia-lnbits.com
LNBITS_API_KEY=tu_api_key_aqui

# Aplicación
INVOICE_AMOUNT_SATS=100
DOMAIN=tudominio.com
```

### Cambiar el Puerto

Edita `docker-compose.yml`:
```yaml
ports:
  - "8080:8000"  # Acceder en http://localhost:8080
```

### Estructura de Módulos de la Aplicación

```
/
├── main.py              # App factory, middlewares, startup/shutdown
├── config.py            # Variables de entorno y constantes de rutas
├── schemas.py           # Modelos Pydantic de request/response
├── db/                  # Capa de datos (conexión, records, users)
├── core/                # Lógica de negocio (security, nostr, email)
├── services/            # Integraciones externas (pagos LNbits)
└── routers/             # Manejadores de rutas HTTP (public, nip05, admin)
```

### Estructura de Volúmenes

```
/
├── data/
│   └── .well-known/     # Registro NIP-05 persistente
├── static/
│   └── images/          # Imágenes estáticas
└── templates/           # Plantillas HTML (hot-reload en desarrollo)
```

Los volúmenes se montan automáticamente desde `docker-compose.yml`. Los datos en `data/` persisten entre reinicios.

---

## 🔧 Comandos de Gestión

### Ciclo de Vida

```bash
# Iniciar en segundo plano
docker-compose up -d

# Detener (conserva volúmenes)
docker-compose down

# Reiniciar sin reconstruir
docker-compose restart

# Ver estado
docker-compose ps

# Ver logs en tiempo real
docker-compose logs -f nip05-app

# Ver últimas 100 líneas de logs
docker-compose logs --tail=100
```

### Construcción

```bash
# Construir imagen
docker-compose build

# Reconstruir sin caché (útil al actualizar dependencias)
docker-compose build --no-cache

# Construir y levantar en un solo paso
docker-compose up -d --build
```

### Mantenimiento

```bash
# Abrir shell en el contenedor
docker exec -it nip05-app bash

# Eliminar contenedores y volúmenes (¡irreversible!)
docker-compose down -v

# Limpiar imágenes sin usar
docker image prune -f

# Ver uso de recursos
docker stats nip05-app
```

---

## 🧰 Scripts de Utilidad

### `scripts/docker-start.sh`

Inicia la aplicación con verificaciones completas:
- Detecta si Docker está instalado
- Copia `.env.example` → `.env` si no existe
- Descarga imagen base
- Construye la imagen de la aplicación
- Levanta los contenedores
- Espera y confirma que el servicio responde

```bash
cd docker
./scripts/docker-start.sh
```

### `scripts/docker-stop.sh`

Detiene los contenedores con limpieza opcional:

```bash
cd docker
./scripts/docker-stop.sh
```

### `scripts/docker-build.sh`

Construye la imagen manualmente con nombre y tag personalizados:

```bash
cd docker
./scripts/docker-build.sh [nombre] [tag]
./scripts/docker-build.sh nip05-app v1.2.0
```

---

## 🔍 Troubleshooting

### El contenedor se detiene inmediatamente

```bash
# Ver logs completos
docker-compose logs nip05-app

# Causas comunes:
# - Variables de entorno faltantes en .env
# - Puerto 8000 ocupado por otro proceso
# - Error de sintaxis en la aplicación
```

### Puerto 8000 en uso

```bash
# Identificar el proceso que ocupa el puerto
lsof -i :8000       # macOS/Linux
netstat -ano | findstr :8000  # Windows

# Solución: cambiar el puerto externo en docker-compose.yml
ports:
  - "8001:8000"
```

### Problemas de permisos con Docker

```bash
# Añadir usuario al grupo docker (Linux)
sudo usermod -aG docker $USER
newgrp docker

# Si persiste, reiniciar el demonio Docker
sudo systemctl restart docker
```

### Imagen desactualizada tras cambios

```bash
# Reconstruir ignorando la caché
docker-compose build --no-cache
docker-compose up -d
```

### Verificar conectividad con LNbits

```bash
# Endpoint de diagnóstico incluido en la app
curl http://localhost:8000/api/debug/lnbits-test
```

---

## 🔐 Seguridad

### Buenas Prácticas

1. **No versiones el archivo `.env`**
   - `.env` ya está en `.gitignore`
   - Usa `docker secrets` para entornos Docker Swarm

2. **Usa siempre HTTPS en producción**
   - Configura un reverse proxy (Nginx, Caddy, Traefik)
   - Obtén certificados gratuitos con [Let's Encrypt](https://letsencrypt.org/)

3. **Limita los recursos del contenedor**
   ```yaml
   deploy:
     resources:
       limits:
         cpus: '1'
         memory: 512M
   ```

4. **El contenedor ya corre como usuario no-root** (`appuser`, UID 1000)

5. **Mantén la imagen actualizada**
   ```bash
   docker-compose build --no-cache
   ```

### Configuración Nginx para Producción

```nginx
server {
    listen 443 ssl http2;
    server_name tudominio.com;

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

# Redirigir HTTP a HTTPS
server {
    listen 80;
    server_name tudominio.com;
    return 301 https://$host$request_uri;
}
```

---

## 📊 Monitoreo

### Health Check

El contenedor verifica su propio estado cada 30 segundos:

```bash
# Estado: healthy / unhealthy / starting
docker inspect nip05-app --format='{{.State.Health.Status}}'

# Historial de health checks
docker inspect nip05-app --format='{{range .State.Health.Log}}{{.Output}}{{end}}'
```

### Métricas de Recursos

```bash
# Uso de CPU y memoria en tiempo real
docker stats nip05-app

# Información detallada del contenedor
docker inspect nip05-app
```

---

## 🚀 Despliegue en Producción

### VPS (DigitalOcean, Linode, Hetzner, AWS, etc.)

```bash
# 1. Conectarse al servidor
ssh root@tu-servidor.com

# 2. Instalar Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER

# 3. Clonar el repositorio
git clone https://github.com/tu-usuario/nip05.git
cd nip05

# 4. Configurar variables
cp .env.example .env
nano .env

# 5. Iniciar con perfil de producción
cd docker
docker-compose -f docker-compose.prod.yml up -d

# 6. Configurar firewall
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### Con Docker Swarm (Multi-nodo)

```bash
# Inicializar el swarm en el nodo manager
docker swarm init

# Desplegar el stack
docker stack deploy -c docker-compose.yml nip05

# Ver servicios
docker service ls
```

---

## 🔄 Actualizaciones

```bash
# 1. Obtener últimos cambios
git pull origin main

# 2. Reconstruir la imagen
docker-compose build --no-cache

# 3. Reiniciar con la nueva imagen (sin downtime)
docker-compose up -d

# 4. Verificar que todo esté OK
docker-compose ps
docker-compose logs --tail=50
```

---

## 📚 Recursos Adicionales

- [Documentación oficial de Docker](https://docs.docker.com/)
- [Referencia de Docker Compose](https://docs.docker.com/compose/compose-file/)
- [FastAPI en Docker](https://fastapi.tiangolo.com/deployment/docker/)
- [Buenas prácticas con Docker](https://docs.docker.com/develop/dev-best-practices/)
- [Let's Encrypt (SSL gratuito)](https://letsencrypt.org/)

---

## ❓ Soporte

1. Revisar los logs: `docker-compose logs -f`
2. Consultar la sección de Troubleshooting de esta guía
3. Abrir un issue en el repositorio de GitHub

---

**Última actualización:** 2026-02-26
