#!/bin/bash

# Script to build the Docker image
# This script is in docker/scripts/, automatically adjusts paths

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Go to the docker directory (where this script is located)
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOCKER_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DOCKER_DIR"

echo "🐳 Building Docker image for NIP-05..."
echo "📍 Directory: $(pwd)"

# Verify that the Dockerfile exists
if [ ! -f "Dockerfile" ]; then
    echo -e "${RED}❌ Error: Dockerfile not found in $DOCKER_DIR${NC}"
    exit 1
fi

# Image name
IMAGE_NAME=${1:-nip05-app}
IMAGE_TAG=${2:-latest}

echo -e "${YELLOW}📦 Building image: ${IMAGE_NAME}:${IMAGE_TAG}${NC}"

# Build image (context is the parent directory of the project)
docker build \
    --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
    --tag "${IMAGE_NAME}:latest" \
    --file Dockerfile \
    ..

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Image built successfully${NC}"
    echo ""
    echo "Useful commands (run from docker/):"
    echo "  docker-compose up -d"
    echo "  docker-compose logs -f"
else
    echo -e "${RED}❌ Error building the image${NC}"
    exit 1
fi
