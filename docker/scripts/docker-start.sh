#!/bin/bash

# Script to start the application with docker-compose
# This script is in docker/scripts/, automatically adjusts paths

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Go to the docker directory (where this script is located)
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOCKER_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$DOCKER_DIR")"

cd "$DOCKER_DIR"

echo -e "${BLUE}🚀 NIP-05 Nostr Identifier - Docker Startup${NC}"
echo -e "${BLUE}📍 Directory: $(pwd)${NC}"
echo ""

# Verify that docker-compose exists
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Error: Docker is not installed${NC}"
    exit 1
fi

# Verify .env file in project root
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found in: $PROJECT_ROOT${NC}"
    echo "Copying .env.example to .env..."
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo -e "${YELLOW}⚠️  Please, edit the .env file with your credentials${NC}"
        echo "Open the file: $PROJECT_ROOT/.env"
        read -p "Continue anyway? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    else
        echo -e "${RED}❌ Error: .env.example does not exist either${NC}"
        exit 1
    fi
fi

# Create data directory if it does not exist
mkdir -p "$PROJECT_ROOT/data/.well-known"

echo -e "${YELLOW}📦 Checking/downloading base image...${NC}"
docker pull python:3.11-slim

echo -e "${YELLOW}🔨 Building application...${NC}"
docker-compose build

echo -e "${YELLOW}🚀 Starting containers...${NC}"
docker-compose up -d

# Wait for the container to be ready
echo -e "${YELLOW}⏳ Waiting for the application to be ready...${NC}"
sleep 3

# Verify that the container is running
if docker-compose ps | grep -q "nip05-app.*Up"; then
    echo -e "${GREEN}✅ Application started successfully${NC}"
    echo ""
    echo -e "${BLUE}📋 Service information:${NC}"
    echo "  URL: http://localhost:8000"
    echo "  Container: nip05-app"
    echo "  Directory: $(pwd)"
    echo ""
    echo -e "${BLUE}🔧 Useful commands (run from docker/):${NC}"
    echo "  View logs:    docker-compose logs -f"
    echo "  Stop:         docker-compose down"
    echo "  Restart:      docker-compose restart"
    echo "  Status:       docker-compose ps"
    echo ""
    echo -e "${BLUE}🔧 Or use scripts:${NC}"
    echo "  ./scripts/docker-stop.sh"
    echo ""
else
    echo -e "${RED}❌ Error starting the application${NC}"
    echo ""
    echo -e "${BLUE}🔍 Showing logs:${NC}"
    docker-compose logs
    exit 1
fi
