# METRONICS DOCKER DEPLOYMENT GUIDE

## 📦 Overview

This guide covers:
- Creating a Docker image for Metronics (Next.js frontend)
- Running it locally with Docker
- Deploying to a production server
- Managing with Docker Compose
- CI/CD pipeline integration

---

## 🏗️ PROJECT STRUCTURE SETUP

Before dockerizing, ensure your Metronics project has this structure:

```
metronics/
├── .dockerignore          ← Files to exclude from Docker
├── Dockerfile             ← Docker image definition
├── docker-compose.yml     ← Local development setup
├── docker-compose.prod.yml ← Production setup
├── .env.local             ← Local environment variables
├── .env.production        ← Production environment variables
├── next.config.js         ← Next.js configuration
├── package.json
├── package-lock.json
├── public/
├── src/
│   ├── app/
│   ├── components/
│   ├── hooks/
│   └── ...
├── tsconfig.json
└── README.md
```

---

## 📝 STEP 1: CREATE .dockerignore

**File: `.dockerignore`**

Prevents unnecessary files from being added to Docker image:

```
node_modules
npm-debug.log
.git
.gitignore
.next
.env.local
.env.*.local
out
build
dist
.DS_Store
.idea
.vscode
*.md
!README.md
coverage
.nyc_output
yarn-error.log
.yarn/cache
```

---

## 🐳 STEP 2: CREATE DOCKERFILE

**File: `Dockerfile`** (Multi-stage build for optimal size)

```dockerfile
# ============================================================================
# Stage 1: Build Stage
# ============================================================================
FROM node:18-alpine AS builder

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm ci --only=production && \
    npm cache clean --force

# Copy source code
COPY . .

# Build Next.js application
RUN npm run build

# ============================================================================
# Stage 2: Runtime Stage
# ============================================================================
FROM node:18-alpine AS runner

WORKDIR /app

# Set environment to production
ENV NODE_ENV=production

# Create non-root user for security
RUN addgroup --gid 1001 nodejs && \
    adduser --uid 1001 --ingroup nodejs nextjs

# Copy built application from builder stage
COPY --from=builder --chown=nextjs:nodejs /app/.next ./.next
COPY --from=builder --chown=nextjs:nodejs /app/node_modules ./node_modules
COPY --from=builder --chown=nextjs:nodejs /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/package.json ./package.json

# Copy .next/static directory
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# Use non-root user
USER nextjs

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD node -e "require('http').get('http://localhost:3000/', (r) => {if (r.statusCode !== 200) throw new Error(r.statusCode)})"

# Start Next.js application
CMD ["npm", "start"]
```

### Alternative: Development Dockerfile

**File: `Dockerfile.dev`** (for local development with hot reload)

```dockerfile
FROM node:18-alpine

WORKDIR /app

# Install dependencies
COPY package*.json ./
RUN npm install

# Copy source code
COPY . .

# Expose port
EXPOSE 3000

# Environment
ENV NODE_ENV=development

# Start with hot reload
CMD ["npm", "run", "dev"]
```

---

## 🔧 STEP 3: CREATE docker-compose.yml (Development)

**File: `docker-compose.yml`** (Local development with hot reload)

```yaml
version: '3.8'

services:
  metronics:
    build:
      context: .
      dockerfile: Dockerfile.dev
    container_name: metronics-dev
    ports:
      - "3000:3000"
    volumes:
      - .:/app
      - /app/node_modules  # Prevent host node_modules from overwriting
      - /app/.next
    environment:
      - NODE_ENV=development
      - NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
      - NEXT_PUBLIC_AUTH_URL=http://localhost:3000
    networks:
      - metronics-network
    command: npm run dev

  # Optional: Include backend API service
  # api:
  #   build:
  #     context: ../backend
  #     dockerfile: Dockerfile
  #   container_name: sorento-api
  #   ports:
  #     - "8000:8000"
  #   environment:
  #     - DATABASE_URL=postgresql://user:password@postgres:5432/sorento
  #     - REDIS_URL=redis://redis:6379
  #   depends_on:
  #     - postgres
  #     - redis
  #   networks:
  #     - metronics-network

  # Optional: Database service
  # postgres:
  #   image: postgres:15-alpine
  #   container_name: metronics-postgres
  #   environment:
  #     - POSTGRES_USER=sorento
  #     - POSTGRES_PASSWORD=your_secure_password
  #     - POSTGRES_DB=sorento
  #   volumes:
  #     - postgres_data:/var/lib/postgresql/data
  #   ports:
  #     - "5432:5432"
  #   networks:
  #     - metronics-network

  # Optional: Redis cache
  # redis:
  #   image: redis:7-alpine
  #   container_name: metronics-redis
  #   ports:
  #     - "6379:6379"
  #   networks:
  #     - metronics-network

networks:
  metronics-network:
    driver: bridge

volumes:
  postgres_data:
```

---

## 🚀 STEP 4: CREATE docker-compose.prod.yml (Production)

**File: `docker-compose.prod.yml`** (Production-ready setup)

```yaml
version: '3.8'

services:
  metronics:
    image: metronics:latest  # Pre-built image
    container_name: metronics-prod
    restart: always
    ports:
      - "3000:3000"
    environment:
      - NODE_ENV=production
      - NEXT_PUBLIC_API_BASE_URL=https://api.sorento.com
      - NEXT_PUBLIC_AUTH_URL=https://sorento.com
      - NEXT_TELEMETRY_DISABLED=1  # Disable Next.js telemetry
    networks:
      - metronics-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"
    # Resource limits
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          cpus: '1'
          memory: 512M

  # Nginx reverse proxy (optional, recommended)
  nginx:
    image: nginx:alpine
    container_name: metronics-nginx
    restart: always
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro  # SSL certificates
      - ./cache:/var/cache/nginx
    depends_on:
      - metronics
    networks:
      - metronics-network
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

networks:
  metronics-network:
    driver: bridge
```

---

## 🌐 STEP 5: CREATE nginx.conf (Reverse Proxy)

**File: `nginx.conf`** (Nginx configuration for production)

```nginx
user nginx;
worker_processes auto;
error_log /var/log/nginx/error.log warn;
pid /var/run/nginx.pid;

events {
    worker_connections 1024;
}

http {
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    log_format main '$remote_addr - $remote_user [$time_local] "$request" '
                    '$status $body_bytes_sent "$http_referer" '
                    '"$http_user_agent" "$http_x_forwarded_for"';

    access_log /var/log/nginx/access.log main;

    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;
    client_max_body_size 20M;

    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css text/xml text/javascript 
               application/json application/javascript application/xml+rss 
               application/rss+xml application/atom+xml image/svg+xml;

    # Upstream Next.js service
    upstream metronics {
        server metronics:3000;
    }

    # HTTP to HTTPS redirect
    server {
        listen 80;
        server_name sorento.com www.sorento.com;
        
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }
        
        location / {
            return 301 https://$server_name$request_uri;
        }
    }

    # HTTPS server block
    server {
        listen 443 ssl http2;
        server_name sorento.com www.sorento.com;

        # SSL certificates (use Let's Encrypt)
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;

        # SSL configuration
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;
        ssl_prefer_server_ciphers on;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 10m;

        # Security headers
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        add_header X-Frame-Options "SAMEORIGIN" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header X-XSS-Protection "1; mode=block" always;
        add_header Referrer-Policy "no-referrer-when-downgrade" always;

        # Proxy settings
        location / {
            proxy_pass http://metronics;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_cache_bypass $http_upgrade;
            
            # Timeouts for long-lived connections
            proxy_connect_timeout 60s;
            proxy_send_timeout 60s;
            proxy_read_timeout 60s;
        }

        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            proxy_pass http://metronics;
            expires 1y;
            add_header Cache-Control "public, immutable";
        }

        # Disable caching for HTML
        location ~* \.html$ {
            proxy_pass http://metronics;
            expires -1;
            add_header Cache-Control "no-cache, no-store, must-revalidate";
        }
    }
}
```

---

## 🔑 STEP 6: ENVIRONMENT CONFIGURATION

**File: `.env.production`**

```bash
# Next.js
NODE_ENV=production
NEXT_TELEMETRY_DISABLED=1

# API Configuration
NEXT_PUBLIC_API_BASE_URL=https://api.sorento.com
NEXT_PUBLIC_API_TIMEOUT=30000

# Authentication
NEXT_PUBLIC_AUTH_URL=https://sorento.com
NEXT_PUBLIC_AUTH_PROVIDER=jwt
NEXT_PUBLIC_JWT_SECRET=your_jwt_secret_key

# Feature Flags
NEXT_PUBLIC_ENABLE_ANALYTICS=true
NEXT_PUBLIC_ENABLE_SENTRY=true

# Sentry (Error tracking)
SENTRY_AUTH_TOKEN=your_sentry_token
NEXT_PUBLIC_SENTRY_DSN=your_sentry_dsn

# Analytics
NEXT_PUBLIC_GA_ID=your_google_analytics_id

# CDN
NEXT_PUBLIC_CDN_URL=https://cdn.sorento.com

# Logging
LOG_LEVEL=info

# Database
NEXT_PUBLIC_DB_HOST=postgres.internal
NEXT_PUBLIC_DB_PORT=5432
NEXT_PUBLIC_DB_NAME=sorento
```

**File: `.env.production.local`** (sensitive data - never commit)

```bash
# These should be loaded from CI/CD secrets, not committed to git
DATABASE_URL=postgresql://user:password@postgres:5432/sorento
NEXT_PUBLIC_API_SECRET_KEY=your_secret_key
NEXT_PUBLIC_JWT_SECRET=your_jwt_secret_key
```

---

## 🚀 STEP 7: BUILD AND RUN LOCALLY

### Build Docker Image

```bash
# Build development image
docker build -f Dockerfile.dev -t metronics:dev .

# Build production image
docker build -t metronics:latest .

# Tag for registry
docker tag metronics:latest your-registry.azurecr.io/metronics:latest
```

### Run with Docker Compose

```bash
# Development (with hot reload)
docker-compose up -d

# View logs
docker-compose logs -f metronics

# Stop containers
docker-compose down

# Clean up volumes
docker-compose down -v
```

### Run Single Container

```bash
# Build and run
docker run -p 3000:3000 \
  -e NODE_ENV=production \
  -e NEXT_PUBLIC_API_BASE_URL=http://localhost:8000 \
  metronics:latest

# With environment file
docker run -p 3000:3000 \
  --env-file .env.production \
  metronics:latest
```

---

## 📤 STEP 8: PUSH TO CONTAINER REGISTRY

### Azure Container Registry (Recommended)

```bash
# Login to ACR
az acr login --name your-registry

# Tag image
docker tag metronics:latest your-registry.azurecr.io/metronics:latest
docker tag metronics:latest your-registry.azurecr.io/metronics:$(date +%Y%m%d-%H%M%S)

# Push to registry
docker push your-registry.azurecr.io/metronics:latest
docker push your-registry.azurecr.io/metronics:$(date +%Y%m%d-%H%M%S)

# List images
az acr repository list --name your-registry
az acr repository show-tags --name your-registry --repository metronics
```

### Docker Hub

```bash
# Login to Docker Hub
docker login

# Tag image
docker tag metronics:latest your-username/metronics:latest

# Push
docker push your-username/metronics:latest
```

---

## 🖥️ STEP 9: DEPLOY TO SERVER

### Option A: Direct Server Deployment (VPS/Dedicated Server)

```bash
# SSH into server
ssh user@your-server.com

# Create app directory
mkdir -p /opt/metronics
cd /opt/metronics

# Clone or download docker-compose files
scp docker-compose.prod.yml user@your-server.com:/opt/metronics/
scp nginx.conf user@your-server.com:/opt/metronics/
scp .env.production user@your-server.com:/opt/metronics/

# Create SSL directory
mkdir -p /opt/metronics/ssl

# Pull image from registry
docker pull your-registry.azurecr.io/metronics:latest

# Start containers
docker-compose -f docker-compose.prod.yml up -d

# Verify services
docker-compose ps
docker-compose logs metronics
```

### Option B: Kubernetes Deployment

**File: `k8s-deployment.yaml`**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: metronics
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: metronics
  template:
    metadata:
      labels:
        app: metronics
    spec:
      containers:
      - name: metronics
        image: your-registry.azurecr.io/metronics:latest
        imagePullPolicy: Always
        ports:
        - containerPort: 3000
        env:
        - name: NODE_ENV
          value: production
        - name: NEXT_PUBLIC_API_BASE_URL
          value: https://api.sorento.com
        - name: NEXT_PUBLIC_AUTH_URL
          value: https://sorento.com
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "1Gi"
            cpu: "1000m"
        livenessProbe:
          httpGet:
            path: /
            port: 3000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /
            port: 3000
          initialDelaySeconds: 5
          periodSeconds: 5
      imagePullSecrets:
      - name: acr-secret

---
apiVersion: v1
kind: Service
metadata:
  name: metronics-service
spec:
  selector:
    app: metronics
  ports:
  - port: 80
    targetPort: 3000
  type: LoadBalancer
```

Deploy to Kubernetes:

```bash
# Create secret for ACR
kubectl create secret docker-registry acr-secret \
  --docker-server=your-registry.azurecr.io \
  --docker-username=your-username \
  --docker-password=your-password

# Deploy
kubectl apply -f k8s-deployment.yaml

# Check deployment
kubectl get pods
kubectl get svc metronics-service

# View logs
kubectl logs -f deployment/metronics
```

---

## 🔐 STEP 10: SSL CERTIFICATES (Let's Encrypt)

### Using Certbot with Docker

```bash
# Run Certbot
docker run -it --rm --name certbot \
  -v "/opt/metronics/ssl:/etc/letsencrypt" \
  certbot/certbot certonly \
  --standalone \
  --email your-email@sorento.com \
  -d sorento.com \
  -d www.sorento.com

# Verify certificates
ls -la /opt/metronics/ssl/live/sorento.com/

# Copy certificates to nginx location
cp /opt/metronics/ssl/live/sorento.com/fullchain.pem /opt/metronics/ssl/cert.pem
cp /opt/metronics/ssl/live/sorento.com/privkey.pem /opt/metronics/ssl/key.pem
```

### Auto-renewal with Docker

**File: `renewal-cron.sh`**

```bash
#!/bin/bash

# Renew certificates
docker run --rm --name certbot \
  -v "/opt/metronics/ssl:/etc/letsencrypt" \
  certbot/certbot renew \
  --webroot \
  --webroot-path /var/www/certbot

# Reload nginx
docker-compose -f /opt/metronics/docker-compose.prod.yml exec nginx nginx -s reload
```

Add to crontab:

```bash
# Crontab entry (runs daily at 2 AM)
0 2 * * * /opt/metronics/renewal-cron.sh >> /var/log/metronics-cert-renewal.log 2>&1
```

---

## 📊 STEP 11: MONITORING & LOGGING

### Docker Logs

```bash
# View logs
docker-compose logs metronics
docker-compose logs -f metronics  # Follow logs
docker-compose logs --tail=100 metronics

# View specific service logs
docker logs container-name
docker logs -f container-name --tail=50
```

### Container Stats

```bash
# Monitor resource usage
docker stats

# Check container health
docker inspect metronics | grep -A 10 '"Health"'
```

### Prometheus + Grafana (Optional)

**File: `docker-compose.monitoring.yml`**

```yaml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml:ro
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3001:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=your_password
    volumes:
      - grafana_data:/var/lib/grafana

volumes:
  prometheus_data:
  grafana_data:
```

---

## 🔄 STEP 12: CI/CD INTEGRATION

### GitHub Actions

**File: `.github/workflows/deploy.yml`**

```yaml
name: Build and Deploy Metronics

on:
  push:
    branches:
      - main
      - develop

env:
  REGISTRY: your-registry.azurecr.io
  IMAGE_NAME: metronics

jobs:
  build-and-push:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2

      - name: Login to ACR
        uses: docker/login-action@v2
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ secrets.ACR_USERNAME }}
          password: ${{ secrets.ACR_PASSWORD }}

      - name: Build and push
        uses: docker/build-push-action@v4
        with:
          context: .
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}
          cache-from: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache
          cache-to: type=registry,ref=${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:buildcache,mode=max

  deploy:
    needs: build-and-push
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3

      - name: Deploy to server
        uses: appleboy/ssh-action@master
        with:
          host: ${{ secrets.SERVER_HOST }}
          username: ${{ secrets.SERVER_USER }}
          key: ${{ secrets.SERVER_SSH_KEY }}
          script: |
            cd /opt/metronics
            docker-compose -f docker-compose.prod.yml pull
            docker-compose -f docker-compose.prod.yml up -d
            docker-compose -f docker-compose.prod.yml logs metronics
```

---

## 🐛 STEP 13: TROUBLESHOOTING

### Common Issues

```bash
# Port already in use
docker-compose down
docker system prune -a
docker-compose up -d

# Container keeps restarting
docker-compose logs metronics  # Check logs
docker inspect metronics  # Check health status

# High memory usage
docker stats
docker-compose restart metronics

# Network issues
docker network ls
docker network inspect metronics_metronics-network

# Clear everything and start fresh
docker-compose down -v
docker system prune -a --volumes
docker-compose up -d
```

### Health Checks

```bash
# Test service
curl http://localhost:3000

# Test with logs
docker-compose exec metronics curl http://localhost:3000

# Check container status
docker ps
docker-compose ps
```

---

## 📋 DEPLOYMENT CHECKLIST

- [ ] `.dockerignore` created
- [ ] `Dockerfile` created (multi-stage)
- [ ] `Dockerfile.dev` created (optional)
- [ ] `docker-compose.yml` created (development)
- [ ] `docker-compose.prod.yml` created
- [ ] `nginx.conf` created
- [ ] `.env.production` configured
- [ ] `.env.production.local` created (not committed)
- [ ] Docker image builds successfully
- [ ] Local development works with hot reload
- [ ] Image tagged and pushed to registry
- [ ] Server has Docker and Docker Compose installed
- [ ] SSL certificates obtained (Let's Encrypt)
- [ ] Nginx configuration tested
- [ ] Health checks passing
- [ ] Monitoring/logging configured
- [ ] CI/CD pipeline configured
- [ ] Backup strategy in place
- [ ] Auto-renewal for SSL certificates set up
- [ ] Production deployment tested

---

## 🚀 QUICK START COMMANDS

```bash
# Local development
docker-compose up -d
docker-compose logs -f

# Build production image
docker build -t metronics:latest .

# Push to registry
docker tag metronics:latest your-registry.azurecr.io/metronics:latest
docker push your-registry.azurecr.io/metronics:latest

# Deploy to server
ssh user@server "cd /opt/metronics && docker-compose -f docker-compose.prod.yml pull && docker-compose -f docker-compose.prod.yml up -d"

# Check deployment
docker-compose ps
docker-compose logs metronics

# Update running container
docker-compose pull
docker-compose up -d
```

---

## 📞 SUPPORT & REFERENCES

- **Docker Docs:** https://docs.docker.com/
- **Docker Compose:** https://docs.docker.com/compose/
- **Next.js Docker:** https://nextjs.org/docs/deployment/docker
- **Nginx:** https://nginx.org/
- **Let's Encrypt:** https://letsencrypt.org/
- **Azure Container Registry:** https://docs.microsoft.com/en-us/azure/container-registry/

---

**Status:** Docker deployment guide complete  
**Last Updated:** January 11, 2026  
**For:** Metronics/Sorento Admin Dashboard  

**Next Steps:**
1. Implement Dockerfile and docker-compose files
2. Test locally with Docker
3. Push to container registry
4. Deploy to production server
5. Monitor and maintain
