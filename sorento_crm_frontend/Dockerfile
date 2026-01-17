# Multi-stage build for Next.js frontend
# Stage 1: Build the Next.js application
FROM node:20-alpine AS builder

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies (using npm ci for reproducible builds)
RUN npm ci

# Copy application source
COPY . .

# Generate Prisma client (required before build)
RUN npx prisma generate

# Set build-time environment variable for API URL
# Empty string means use relative paths (nginx will proxy)
ARG NEXT_PUBLIC_API_URL=
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# Build the Next.js application
# The output: 'standalone' in next.config.mjs creates a minimal production build
RUN npm run build

# Stage 2: Production image with Node.js and Nginx
FROM node:20-alpine

# Install nginx and curl for health checks
RUN apk add --no-cache nginx curl supervisor

# Copy custom Nginx configuration
# Alpine nginx expects server blocks in http.d, not conf.d
RUN mkdir -p /etc/nginx/http.d
COPY nginx.conf /etc/nginx/http.d/default.conf

# Copy the built Next.js standalone application from builder
# Next.js standalone creates a minimal server in .next/standalone
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

# Copy Prisma schema and migrations for database setup
COPY --from=builder /app/prisma ./prisma
COPY --from=builder /app/node_modules/.prisma ./node_modules/.prisma
COPY --from=builder /app/node_modules/@prisma ./node_modules/@prisma

# The standalone output structure has server.js in the root of .next/standalone
# We need to ensure the static files are in the right place
RUN if [ -d ".next/standalone/.next" ]; then \
        cp -r .next/standalone/.next/static .next/static 2>/dev/null || true; \
    fi

# Set environment variable for Next.js to run on port 3000
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Create supervisor config directory and file to run both nginx and Next.js
RUN mkdir -p /etc/supervisor/conf.d && \
    echo '[supervisord]' > /etc/supervisor/conf.d/supervisord.conf && \
    echo 'nodaemon=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '[program:nginx]' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'command=nginx -g "daemon off;"' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo '[program:nextjs]' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'command=node server.js' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'directory=/app' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autostart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'autorestart=true' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile=/dev/stdout' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stdout_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile=/dev/stderr' >> /etc/supervisor/conf.d/supervisord.conf && \
    echo 'stderr_logfile_maxbytes=0' >> /etc/supervisor/conf.d/supervisord.conf

# Create nginx user and set permissions
RUN chown -R node:node /app && \
    chmod -R 755 /app

# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost/health || exit 1

# Install Prisma CLI in production stage for migrations
RUN npm install -g prisma@6.10.1

# Create startup script that runs migrations then starts supervisor
RUN echo '#!/bin/sh' > /start.sh && \
    echo 'echo "Running Prisma migrations..."' >> /start.sh && \
    echo 'prisma migrate deploy || echo "Migration failed or already applied"' >> /start.sh && \
    echo 'echo "Starting services..."' >> /start.sh && \
    echo 'exec /usr/bin/supervisord -c /etc/supervisor/conf.d/supervisord.conf' >> /start.sh && \
    chmod +x /start.sh

# Start supervisor to run both nginx and Next.js (after migrations)
CMD ["/start.sh"]
