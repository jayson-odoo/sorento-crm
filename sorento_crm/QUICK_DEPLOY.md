# Quick Deployment Guide

## Deploy to Remote Server in 5 Steps

### Step 1: Prepare Your Server

```bash
# SSH into your server
ssh user@your-server-ip

# Install Docker and Docker Compose (if not installed)
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Log out and back in for group changes to take effect
exit
ssh user@your-server-ip
```

### Step 2: Clone Repository

```bash
cd /opt
git clone https://github.com/your-username/sorento_crm.git
cd sorento_crm
```

### Step 3: Create Environment File

```bash
nano .env
```

Paste this (modify values for production):

```env
POSTGRES_USER=postgres
POSTGRES_PASSWORD=$(openssl rand -hex 16)
POSTGRES_DB=sorento_crm
JWT_SECRET=$(openssl rand -hex 32)
CORS_ORIGINS=http://your-domain.com,https://your-domain.com
ENVIRONMENT=production
DEBUG=false
NEXT_PUBLIC_API_URL=http://your-domain.com:8000
```

Save: `Ctrl+X`, then `Y`, then `Enter`

### Step 4: Deploy

```bash
# Build and start all services
docker compose build
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f
```

### Step 5: Verify

```bash
# Test backend
curl http://localhost:8000/health

# Test frontend
curl http://localhost/health
```

## Access Your Application

- **Frontend**: `http://your-server-ip` or `http://your-domain.com`
- **API Docs**: `http://your-server-ip:8000/docs`
- **ReDoc**: `http://your-server-ip:8000/redoc`

## Common Commands

```bash
# View logs
docker compose logs -f

# Restart services
docker compose restart

# Stop services
docker compose down

# Update application
git pull
docker compose build --no-cache
docker compose up -d
```

## Troubleshooting

If services won't start:
```bash
docker compose logs backend
docker compose logs frontend
docker compose logs db
```

For detailed deployment instructions, see `DEPLOYMENT.md`.
