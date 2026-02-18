# 🚀 Docker - Inicio Rápido

> 📖 [English version → DOCKER_QUICK_START.md](DOCKER_QUICK_START.md)

---

## 📂 Estructura de Archivos Docker

```
/
└── docker/
    ├── Dockerfile                  ← Imagen multi-stage del contenedor
    ├── docker-compose.yml          ← Desarrollo local
    ├── docker-compose.prod.yml     ← Producción con Nginx
    ├── .dockerignore               ← Exclusiones de build
    ├── scripts/
    │   ├── docker-start.sh         ⭐ RECOMENDADO
    │   ├── docker-build.sh
    │   └── docker-stop.sh
    ├── nginx/
    │   └── nginx.conf.example
    └── docs/
        ├── DOCKER_QUICK_START.md   ← Este archivo
        └── DOCKER_FULL_GUIDE.md
```

---

## ⚡ Inicio Rápido (3 pasos)

### 1️⃣ Configura las variables de entorno

Desde la raíz del proyecto:

```bash
cp .env.example .env
nano .env
```

```env
LNBITS_URL=https://tu-lnbits.com
LNBITS_API_KEY=tu_api_key
INVOICE_AMOUNT_SATS=100
DOMAIN=tudominio.com
```

### 2️⃣ Entra al directorio docker

```bash
cd docker
```

### 3️⃣ Ejecuta el script de inicio

```bash
./scripts/docker-start.sh
```

✨ **¡La aplicación estará disponible en http://localhost:8000!**

El script realiza automáticamente:
- Verifica que Docker esté instalado
- Copia `.env.example` a `.env` si no existe
- Descarga la imagen base
- Construye la imagen de la aplicación
- Inicia los contenedores
- Confirma que el servicio esté corriendo

---

## 📋 Comandos Comunes

### Desde `docker/`:

```bash
# Iniciar (recomendado - script automático)
./scripts/docker-start.sh

# O con docker-compose directamente
docker-compose up -d

# Ver logs en tiempo real
docker-compose logs -f

# Ver estado de los contenedores
docker-compose ps

# Detener
docker-compose down

# Detener con script (ofrece limpieza opcional)
./scripts/docker-stop.sh
```

### Desde la raíz del proyecto:

```bash
make docker-start
make docker-stop
make docker-logs
make docker-rebuild
```

---

## ✅ Verificación

```bash
# Verificar que el contenedor está corriendo
docker-compose ps

# Verificar estado de salud
docker inspect nip05-app --format='{{.State.Health.Status}}'

# Probar la aplicación
curl http://localhost:8000

# Probar la API
curl http://localhost:8000/api/check-availability/test
```

---

## 🛑 Detener la Aplicación

```bash
# Desde docker/
./scripts/docker-stop.sh

# O manualmente
docker-compose down
```

---

## 🐛 Troubleshooting Rápido

| Problema | Solución |
|----------|----------|
| `docker: command not found` | Instalar Docker — ver [DOCKER_FULL_GUIDE.es.md](DOCKER_FULL_GUIDE.es.md) |
| `Port 8000 already in use` | Cambiar puerto en `docker-compose.yml`: `"8001:8000"` |
| `.env no encontrado` | Desde la raíz: `cp .env.example .env` |
| El contenedor se detiene | Ver logs: `docker-compose logs nip05-app` |
| Cambios sin efecto | Reconstruir: `make docker-rebuild` |

---

## 🚀 Producción

```bash
cd docker
docker-compose -f docker-compose.prod.yml up -d
```

Requisitos:
- Certificados SSL en `ssl/`
- Configuración Nginx en `nginx/nginx.conf`
- Variables de entorno completas

---

## 📖 Más Información

- [DOCKER_FULL_GUIDE.es.md](DOCKER_FULL_GUIDE.es.md) — Guía completa con seguridad, producción y troubleshooting detallado
- [../README.es.md](../README.es.md) — README del directorio docker

---

**Última actualización:** 2026-02-18
