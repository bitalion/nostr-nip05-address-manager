# 🐳 Docker - NIP-05 Nostr Identifier

Todos los archivos relacionados con Docker están organizados en este directorio.

> 📖 [English version → README.md](README.md)

---

## 📂 Estructura

```
docker/
├── Dockerfile                      # Imagen multi-stage del contenedor
├── docker-compose.yml              # Desarrollo local
├── docker-compose.prod.yml         # Producción con Nginx
├── .dockerignore                   # Exclusiones de build
├── Makefile                        # Comandos make
├── scripts/
│   ├── docker-start.sh             # ⭐ Iniciar (RECOMENDADO)
│   ├── docker-build.sh             # Construir imagen manualmente
│   └── docker-stop.sh              # Detener aplicación
├── nginx/
│   └── nginx.conf.example          # Configuración Nginx para producción
└── docs/
    ├── DOCKER_QUICK_START.md       # ⭐ Guía de inicio rápido
    └── DOCKER_FULL_GUIDE.md        # Guía completa con troubleshooting
```

---

## 🚀 Inicio Rápido

Desde la raíz del proyecto (`nip05/`):

```bash
# 1. Configura las variables de entorno
cp .env.example .env
nano .env

# 2. Entra al directorio docker
cd docker

# 3. Inicia la aplicación (automatizado)
./scripts/docker-start.sh
```

**¡Listo! La aplicación estará disponible en http://localhost:8000**

---

## 📋 Comandos Disponibles

### Script (Recomendado)
```bash
./scripts/docker-start.sh    # Iniciar con verificaciones automáticas
./scripts/docker-stop.sh     # Detener y limpiar
```

### Docker Compose
```bash
docker-compose up -d         # Iniciar en segundo plano
docker-compose down          # Detener
docker-compose logs -f       # Ver logs en tiempo real
docker-compose ps            # Ver estado de los contenedores
docker-compose restart       # Reiniciar
```

### Makefile
```bash
make docker-start            # Iniciar
make docker-stop             # Detener
make docker-logs             # Ver logs
make docker-rebuild          # Reconstruir sin caché
make docker-stats            # Ver uso de recursos
make help                    # Ver todos los comandos disponibles
```

---

## 📖 Documentación

| Archivo | Descripción |
|---|---|
| [docs/DOCKER_QUICK_START.es.md](docs/DOCKER_QUICK_START.es.md) | Inicio rápido en 3 pasos |
| [docs/DOCKER_FULL_GUIDE.es.md](docs/DOCKER_FULL_GUIDE.es.md) | Guía completa: configuración, seguridad, producción y troubleshooting |

---

## ✅ Verificación

```bash
# Ver que el contenedor esté corriendo
docker-compose ps

# Verificar estado de salud
docker inspect nip05-app --format='{{.State.Health.Status}}'

# Probar endpoint
curl http://localhost:8000

# Ver logs
docker-compose logs -f
```

---

## 🔧 Configuración

### Variables de Entorno

Crea el archivo `.env` en la **raíz del proyecto** (no dentro de `docker/`):

```env
LNBITS_URL=https://tu-instancia-lnbits.com
LNBITS_API_KEY=tu_api_key_aqui
INVOICE_AMOUNT_SATS=100
DOMAIN=tudominio.com
```

### Puertos

| Entorno | Puerto | URL |
|---|---|---|
| Desarrollo | 8000 | http://localhost:8000 |
| Producción | 80 / 443 | http(s)://tudominio.com |

---

## 🛑 Detener la Aplicación

```bash
# Usando el script (recomendado, ofrece limpieza opcional)
./scripts/docker-stop.sh

# O directamente con docker-compose
docker-compose down
```

---

## 🐛 Problemas Comunes

| Problema | Solución |
|---|---|
| Puerto 8000 ocupado | Cambiar `"8000:8000"` a `"8001:8000"` en `docker-compose.yml` |
| `.env` no encontrado | Ejecutar `cp .env.example .env` desde la raíz del proyecto |
| Contenedor se detiene | Revisar logs: `docker-compose logs nip05-app` |
| Cambios sin efecto | Reconstruir: `docker-compose build --no-cache` |

---

## 📊 Especificaciones del Contenedor

| Característica | Detalle |
|---|---|
| Imagen base | `python:3.11-slim` |
| Build | Multi-stage (menor tamaño final) |
| Usuario | `appuser` (no-root, UID 1000) |
| Health check | Cada 30s vía HTTP |
| CPU (desarrollo) | Máx. 1 core |
| RAM (desarrollo) | Máx. 512 MB |

---

## 🚀 Producción

Para un despliegue en producción con Nginx y SSL:

```bash
# Desde el directorio docker/
docker-compose -f docker-compose.prod.yml up -d
```

Requisitos previos:
1. Certificados SSL en `ssl/`
2. Configuración Nginx en `nginx/nginx.conf` (usar `nginx.conf.example` como base)
3. Variables de entorno completas en `.env`

---

## 📚 Recursos

- [Documentación oficial de Docker](https://docs.docker.com/)
- [Docker Compose](https://docs.docker.com/compose/)
- [FastAPI en Docker](https://fastapi.tiangolo.com/deployment/docker/)

---

**Última actualización:** 2026-02-26
