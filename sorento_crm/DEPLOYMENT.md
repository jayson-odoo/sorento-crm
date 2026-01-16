# Sorento CRM - Docker Deployment Guide

This guide explains how to deploy the Sorento CRM application (frontend + backend) to a remote server using Docker.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Deployment Options](#deployment-options)
3. [Option 1: Docker Compose on Remote Server (Recommended)](#option-1-docker-compose-on-remote-server-recommended)
4. [Option 2: Docker Registry + Pull on Server](#option-2-docker-registry--pull-on-server)
5. [Option 3: Build Images on Server](#option-3-build-images-on-server)
6. [Environment Configuration](#environment-configuration)
7. [Post-Deployment](#post-deployment)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### On Your Local Machine
- Docker Engine 20.10+
- Docker Compose 2.0+
- Git (to push code to repository)
- SSH access to remote server

### On Remote Server
- Docker Engine 20.10+
- Docker Compose 2.0+
- At least 4GB RAM
- At least 20GB disk space
- Open ports: 80 (frontend), 8000 (backend, optional), 5432 (database, internal only)

## Deployment Options

### Option 1: Docker Compose on Remote Server (Recommended)
**Best for**: Most deployments, easiest to manage
- Push code to Git repository
- Clone on server
- Run `docker compose up` on server

### Option 2: Docker Registry + Pull on Server
**Best for**: CI/CD pipelines, multiple environments
- Build images locally or in CI
- Push to Docker Hub/private registry
- Pull and run on server

### Option 3: Build Images on Server
**Best for**: When you have direct server access
- Copy code to server
- Build images on server
- Run with docker-compose

---

## Option 1: Docker Compose on Remote Server (Recommended)

### Step 1: Prepare Your Code

1. **Ensure all files are committed to Git**:
   ```bash
   git add .
   git commit -m "Docker deployment setup"
   git push origin main
   ```

### Step 2: Connect to Remote Server

```bash
ssh user@your-server-ip
```

### Step 3: Clone Repository on Server

```bash
# Navigate to your deployment directory
cd /opt  # or wherever you prefer

# Clone your repository
git clone https://github.com/your-username/sorento_crm.git
cd sorento_crm
```

### Step 4: Create Environment File

```bash
# Create .env file
nano .env
```

Add the following (adjust values for production):

```env
# Database
POSTGRES_USER=postgres
POSTGRES_PASSWORD=your-strong-password-here
POSTGRES_DB=sorento_crm
POSTGRES_PORT=5432

# Backend
JWT_SECRET=your-super-secret-jwt-key-minimum-32-characters-long
JWT_ALGORITHM=HS256
CORS_ORIGINS=http://your-domain.com,https://your-domain.com
ENVIRONMENT=production
DEBUG=false
WORKERS=4

# Frontend
NEXT_PUBLIC_API_URL=http://your-domain.com:8000
# Or if using reverse proxy:
# NEXT_PUBLIC_API_URL=https://your-domain.com

# Ports
FRONTEND_PORT=80
BACKEND_PORT=8000

# AWS S3 (if using file attachments)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1
AWS_S3_BUCKET=your-bucket-name
```

Save and exit (Ctrl+X, then Y, then Enter).

### Step 5: Build and Start Services

```bash
# Build all images
docker compose build

# Start all services in detached mode
docker compose up -d

# View logs to ensure everything started correctly
docker compose logs -f
```

### Step 6: Verify Deployment

```bash
# Check service status
docker compose ps

# Test backend health
curl http://localhost:8000/health

# Test frontend
curl http://localhost/health
```

### Step 7: Access Your Application

- **Frontend**: `http://your-server-ip` or `http://your-domain.com`
- **Backend API Docs**: `http://your-server-ip:8000/docs`
- **Backend ReDoc**: `http://your-server-ip:8000/redoc`

---

## Option 2: Docker Registry + Pull on Server

### Step 1: Build and Tag Images Locally

```bash
cd sorento_crm

# Build backend image
cd sorento_crm_backend
docker build -t your-dockerhub-username/sorento-crm-backend:latest .
docker build -t your-dockerhub-username/sorento-crm-backend:v1.0.0 .

# Build frontend image
cd ../sorento_crm_frontend
docker build -t your-dockerhub-username/sorento-crm-frontend:latest .
docker build -t your-dockerhub-username/sorento-crm-frontend:v1.0.0 .
```

### Step 2: Push to Docker Hub

```bash
# Login to Docker Hub
docker login

# Push backend
docker push your-dockerhub-username/sorento-crm-backend:latest
docker push your-dockerhub-username/sorento-crm-backend:v1.0.0

# Push frontend
docker push your-dockerhub-username/sorento-crm-frontend:latest
docker push your-dockerhub-username/sorento-crm-frontend:v1.0.0
```

### Step 3: Create docker-compose.prod.yml on Server

On your remote server, create `docker-compose.prod.yml`:

```yaml
version: '3.8'

services:
  db:
    image: postgres:15-alpine
    container_name: sorento_crm_db
    environment:
      POSTGRES_USER: ${POSTGRES_USER:-postgres}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-postgres}
      POSTGRES_DB: ${POSTGRES_DB:-sorento_crm}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER:-postgres}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - sorento_network

  backend:
    image: your-dockerhub-username/sorento-crm-backend:latest
    container_name: sorento_crm_backend
    environment:
      DATABASE_URL: postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@db:5432/${POSTGRES_DB:-sorento_crm}
      DIRECT_URL: postgresql://${POSTGRES_USER:-postgres}:${POSTGRES_PASSWORD:-postgres}@db:5432/${POSTGRES_DB:-sorento_crm}
      JWT_SECRET: ${JWT_SECRET}
      JWT_ALGORITHM: ${JWT_ALGORITHM:-HS256}
      API_HOST: 0.0.0.0
      API_PORT: 8000
      CORS_ORIGINS: ${CORS_ORIGINS}
      ENVIRONMENT: ${ENVIRONMENT:-production}
      DEBUG: ${DEBUG:-false}
      WORKERS: ${WORKERS:-4}
      AWS_ACCESS_KEY_ID: ${AWS_ACCESS_KEY_ID:-}
      AWS_SECRET_ACCESS_KEY: ${AWS_SECRET_ACCESS_KEY:-}
      AWS_REGION: ${AWS_REGION:-}
      AWS_S3_BUCKET: ${AWS_S3_BUCKET:-}
    ports:
      - "${BACKEND_PORT:-8000}:8000"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - sorento_network
    entrypoint: >
      sh -c "
        echo 'Waiting for database...' &&
        until pg_isready -h db -U $${POSTGRES_USER:-postgres}; do sleep 2; done &&
        echo 'Running migrations...' &&
        alembic upgrade head &&
        echo 'Starting server...' &&
        exec gunicorn app.main:app \
          --workers $${WORKERS:-4} \
          --worker-class uvicorn.workers.UvicornWorker \
          --bind 0.0.0.0:8000 \
          --timeout 120 \
          --keep-alive 5 \
          --access-logfile - \
          --error-logfile - \
          --log-level info
      "

  frontend:
    image: your-dockerhub-username/sorento-crm-frontend:latest
    container_name: sorento_crm_frontend
    ports:
      - "${FRONTEND_PORT:-80}:80"
    depends_on:
      - backend
    restart: unless-stopped
    networks:
      - sorento_network

networks:
  sorento_network:
    driver: bridge

volumes:
  postgres_data:
    driver: local
```

### Step 4: Deploy on Server

```bash
# On remote server
mkdir -p /opt/sorento_crm
cd /opt/sorento_crm

# Create .env file (same as Option 1, Step 4)

# Pull and start services
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

---

## Option 3: Build Images on Server

### Step 1: Transfer Code to Server

```bash
# From local machine, use rsync or scp
rsync -avz --exclude 'node_modules' --exclude '.next' --exclude '__pycache__' \
  sorento_crm/ user@your-server:/opt/sorento_crm/

# Or use Git
ssh user@your-server
cd /opt
git clone https://github.com/your-username/sorento_crm.git
cd sorento_crm
```

### Step 2: Build and Run

```bash
# Create .env file (same as Option 1, Step 4)

# Build and start
docker compose build
docker compose up -d
```

---

## Environment Configuration

### Required Environment Variables

Create a `.env` file in the root `sorento_crm/` directory:

```env
# Database (REQUIRED)
POSTGRES_USER=postgres
POSTGRES_PASSWORD=change-this-strong-password
POSTGRES_DB=sorento_crm

# Backend (REQUIRED)
JWT_SECRET=generate-with-openssl-rand-hex-32
CORS_ORIGINS=http://your-domain.com,https://your-domain.com

# Optional but Recommended
ENVIRONMENT=production
DEBUG=false
WORKERS=4
NEXT_PUBLIC_API_URL=http://your-domain.com:8000
```

### Generate Secure JWT Secret

```bash
openssl rand -hex 32
```

---

## Post-Deployment

### 1. Set Up Reverse Proxy (Recommended for Production)

Use Nginx or Traefik as a reverse proxy with SSL:

**Nginx Example** (`/etc/nginx/sites-available/sorento_crm`):

```nginx
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # Frontend
    location / {
        proxy_pass http://localhost:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Increase timeouts for file uploads
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }
}
```

### 2. Set Up Auto-Start on Boot

```bash
# Create systemd service
sudo nano /etc/systemd/system/sorento-crm.service
```

Add:

```ini
[Unit]
Description=Sorento CRM Docker Compose
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/sorento_crm
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable sorento-crm
sudo systemctl start sorento-crm
```

### 3. Set Up Log Rotation

```bash
sudo nano /etc/docker/daemon.json
```

Add:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Restart Docker:

```bash
sudo systemctl restart docker
```

### 4. Database Backups

Create a backup script (`/opt/sorento_crm/backup.sh`):

```bash
#!/bin/bash
BACKUP_DIR="/opt/backups/sorento_crm"
DATE=$(date +%Y%m%d_%H%M%S)
mkdir -p $BACKUP_DIR

docker compose exec -T db pg_dump -U postgres sorento_crm | gzip > $BACKUP_DIR/backup_$DATE.sql.gz

# Keep only last 7 days
find $BACKUP_DIR -name "backup_*.sql.gz" -mtime +7 -delete
```

Make executable and add to crontab:

```bash
chmod +x /opt/sorento_crm/backup.sh
crontab -e
# Add: 0 2 * * * /opt/sorento_crm/backup.sh
```

---

## Troubleshooting

### Services Won't Start

```bash
# Check logs
docker compose logs backend
docker compose logs frontend
docker compose logs db

# Check service status
docker compose ps

# Restart services
docker compose restart
```

### Database Connection Issues

```bash
# Test database connection
docker compose exec backend python -c "from app.database import engine; engine.connect()"

# Check database logs
docker compose logs db

# Verify environment variables
docker compose exec backend env | grep DATABASE
```

### Frontend Can't Connect to Backend

1. **Check NEXT_PUBLIC_API_URL**: Should match your backend URL
2. **Check CORS_ORIGINS**: Must include your frontend domain
3. **Test connectivity**:
   ```bash
   docker compose exec frontend wget -O- http://backend:8000/health
   ```

### Out of Disk Space

```bash
# Clean up unused Docker resources
docker system prune -a --volumes

# Check disk usage
docker system df
```

### Update Application

```bash
# Pull latest code
git pull

# Rebuild and restart
docker compose build --no-cache
docker compose up -d

# Or if using registry images
docker compose pull
docker compose up -d
```

---

## Quick Reference Commands

```bash
# Start all services
docker compose up -d

# Stop all services
docker compose down

# View logs
docker compose logs -f

# Restart a service
docker compose restart backend

# Execute command in container
docker compose exec backend alembic upgrade head
docker compose exec db psql -U postgres -d sorento_crm

# Update and restart
docker compose pull && docker compose up -d

# Clean rebuild
docker compose build --no-cache && docker compose up -d
```

---

## Security Checklist

- [ ] Changed default JWT_SECRET to strong random value
- [ ] Changed default database password
- [ ] Set DEBUG=false
- [ ] Configured CORS_ORIGINS to production domain only
- [ ] Set up SSL/TLS with reverse proxy
- [ ] Database port not exposed externally
- [ ] Regular backups configured
- [ ] Firewall rules configured
- [ ] Docker daemon secured
- [ ] Non-root user for containers (already configured)

---

## Support

For issues:
1. Check logs: `docker compose logs`
2. Verify environment variables
3. Check service health: `docker compose ps`
4. Review this documentation
