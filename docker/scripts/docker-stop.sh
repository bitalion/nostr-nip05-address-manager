#!/bin/bash

# Script to stop the application
# This script is in docker/scripts/, automatically adjusts paths

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Go to the docker directory
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOCKER_DIR="$(dirname "$SCRIPT_DIR")"

cd "$DOCKER_DIR"

echo -e "${BLUE}🛑 Stopping Docker application...${NC}"
echo -e "${BLUE}📍 Directory: $(pwd)${NC}"
echo ""

if docker-compose ps 2>/dev/null | grep -q "nip05-app"; then
    echo -e "${YELLOW}⏹️  Stopping containers...${NC}"
    docker-compose down
    echo -e "${GREEN}✅ Containers stopped${NC}"
else
    echo -e "${YELLOW}ℹ️  No containers running${NC}"
fi

echo ""
echo -e "${BLUE}🧹 Clean images and volumes?${NC}"
read -p "Do you want to delete unused images? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}🧹 Cleaning unused images...${NC}"
    docker image prune -f
    echo -e "${GREEN}✅ Images cleaned${NC}"
fi

echo ""
echo -e "${GREEN}✅ Process completed${NC}"
