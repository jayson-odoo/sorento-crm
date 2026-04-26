#!/bin/bash
# Quick deployment script for Sorento CRM
# Usage: ./deploy.sh [production|staging]

set -e

ENVIRONMENT=${1:-production}
echo "Deploying to: $ENVIRONMENT"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if .env exists
if [ ! -f .env ]; then
    echo -e "${RED}Error: .env file not found!${NC}"
    echo "Please create a .env file with required environment variables."
    echo "See DEPLOYMENT.md for details."
    exit 1
fi

# Load .env so health checks honour BACKEND_PORT / FRONTEND_PORT overrides.
set -a
# shellcheck disable=SC1091
source .env
set +a

BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-80}"

echo -e "${GREEN}Step 1: Pulling latest code...${NC}"
git pull || echo "Warning: Could not pull from git (not a git repo?)"

echo -e "${GREEN}Step 2: Building Docker images...${NC}"
docker compose build

echo -e "${GREEN}Step 3: Starting services...${NC}"
docker compose up -d

echo -e "${GREEN}Step 4: Waiting for services to be healthy...${NC}"
sleep 10

echo -e "${GREEN}Step 5: Checking service status...${NC}"
docker compose ps

echo -e "${GREEN}Step 6: Testing backend health...${NC}"
if curl -f "http://localhost:${BACKEND_PORT}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Backend is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Backend health check failed (may still be starting)${NC}"
fi

echo -e "${GREEN}Step 7: Testing frontend...${NC}"
if curl -f "http://localhost:${FRONTEND_PORT}/health" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Frontend is healthy${NC}"
else
    echo -e "${YELLOW}⚠ Frontend health check failed (may still be starting)${NC}"
fi

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Access your application:"
echo "  Frontend:    http://localhost:${FRONTEND_PORT}"
echo "  Backend API: http://localhost:${BACKEND_PORT}/docs"
echo ""
echo "View logs:"
echo "  docker compose logs -f"
echo ""
echo "Stop services:"
echo "  docker compose down"
