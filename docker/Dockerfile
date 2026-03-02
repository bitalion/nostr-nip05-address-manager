# Stage 1: Build
FROM python:3.11-slim as builder

WORKDIR /app

# Install required system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt --prefix=/install

# Download Tailwind CSS v4 standalone CLI and verify SHA256 checksum
# Hash pinned to v4.2.0 tailwindcss-linux-x64 — update alongside the version tag
RUN curl -fsSL https://github.com/tailwindlabs/tailwindcss/releases/download/v4.2.0/tailwindcss-linux-x64 \
    -o /usr/local/bin/tailwindcss && \
    echo "8f65e2d21c675f1e8d265219979d17d10634c1f553a2f583265b7edb28726432  /usr/local/bin/tailwindcss" \
    | sha256sum -c - && \
    chmod +x /usr/local/bin/tailwindcss

# Copy source files needed for Tailwind class scanning
COPY static/ static/
COPY templates/ templates/

# Compile Tailwind CSS
RUN tailwindcss -i static/css/input.css -o static/css/tailwind.css --minify

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install only the required runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy Python dependencies from the builder stage
COPY --from=builder /install /usr/local

# Copy application modules
COPY main.py .
COPY config.py .
COPY schemas.py .
COPY db/ db/
COPY core/ core/
COPY services/ services/
COPY routers/ routers/
COPY templates/ templates/
COPY static/ static/

# Create data directory — per-domain nostr.json files are injected via volume mount
RUN mkdir -p data

# Copy compiled Tailwind CSS from builder
COPY --from=builder /app/static/css/tailwind.css static/css/tailwind.css

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Default command
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
