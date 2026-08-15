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

# Headless Chromium for the Dealer Kit catalogue PDF export (RQ task
# `generate_catalogue_pdf`). The worker shares this image, so it is installed
# here rather than in a separate one.
#
# Two steps on purpose: the shared libraries Chromium links against need root,
# and the browser itself is installed AS appuser so it lands in that user's
# ~/.cache/ms-playwright - which is the only place the worker process will look
# for it. Installing the browser as root puts it in /root/.cache, where appuser
# cannot read it, and the task then fails at launch with "Executable doesn't
# exist" long after the image looked fine.
#
# PYTHONPATH is not decoration. Every dependency was pip-installed with --user
# in the builder stage and copied to /home/appuser/.local, so it sits on
# APPUSER's user-site path. The line below runs as root, and root's interpreter
# does not read another user's site directory - the `playwright` shim on PATH
# resolves fine and then dies on `ModuleNotFoundError: No module named
# 'playwright'`. Pointing PYTHONPATH at that directory is what lets the root
# step import the package it is standing on.
ENV APPUSER_SITE=/home/appuser/.local/lib/python3.11/site-packages
RUN PYTHONPATH=$APPUSER_SITE playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*
USER appuser
RUN playwright install chromium
USER root

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
