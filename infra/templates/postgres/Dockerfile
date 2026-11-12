# Postgres 17 + pgvector + WAL-G, for both CRM nodes (HA-CF-FAILOVER).
# Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 2 row 2.
# Pin the base image by digest at build time in the private infra repo.
FROM pgvector/pgvector:pg17

# WAL-G as rehearsed in H4a; bump only after a re-run of infra/rehearsal/cf_drill.py.
ARG WALG_VERSION=v3.0.5
# sha256 of wal-g-pg-ubuntu-22.04-amd64.tar.gz in the v3.0.5 release (its .sha256 asset, re-checked).
ARG WALG_SHA256=367ee2863f5f46fde8ab89ce289ca3a43fab3117f8d580029c502b0462580846

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL -o /tmp/wal-g.tar.gz \
      "https://github.com/wal-g/wal-g/releases/download/${WALG_VERSION}/wal-g-pg-ubuntu-22.04-amd64.tar.gz" \
 && echo "${WALG_SHA256}  /tmp/wal-g.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/wal-g.tar.gz -C /usr/local/bin \
 && mv /usr/local/bin/wal-g-pg-ubuntu-22.04-amd64 /usr/local/bin/wal-g \
 && rm -rf /tmp/wal-g.tar.gz /var/lib/apt/lists/*
# The stock entrypoint and STOPSIGNAL (SIGINT = fast shutdown, what a fence wants) are kept.
