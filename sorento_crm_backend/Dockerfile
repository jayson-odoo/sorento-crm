# Multi-stage build for FastAPI backend
FROM python:3.11-slim AS builder

WORKDIR /app

# Install system dependencies for building
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies only.
# WeasyPrint (complaint PDF export RQ task) needs the GTK/Cairo/Pango native
# stack at runtime — libglib2.0-0 provides libgobject-2.0-0, the rest provide
# pango/cairo/gdk-pixbuf + a base font. Without these the PDF task fails with
# "cannot load library 'libgobject-2.0-0'". The worker shares this image.
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    curl \
    libglib2.0-0 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libcairo2 \
    libffi8 \
    shared-mime-info \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security (before copying packages)
RUN useradd -m -u 1000 appuser

# Copy Python packages from builder to user's home directory
COPY --from=builder /root/.local /home/appuser/.local

# Set ownership and permissions
RUN chown -R appuser:appuser /home/appuser/.local && \
    chmod -R +x /home/appuser/.local/bin

# Make sure scripts in .local are usable
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY . .
RUN chown -R appuser:appuser /app

# Make start.sh executable
RUN chmod +x start.sh

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use the startup script as entrypoint
ENTRYPOINT ["/bin/sh", "/app/start.sh"]
