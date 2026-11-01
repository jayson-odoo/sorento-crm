# Postgres 17 + pgvector + Patroni + WAL-G, for both CRM nodes.
# Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2.
# Pin the base image by digest at build time in the private infra repo.
FROM pgvector/pgvector:pg17

# Patroni and WAL-G versions as rehearsed in H4a (infra/rehearsal); bump only after a re-run.
ARG PATRONI_VERSION=4.0.5
ARG WALG_VERSION=v3.0.5
# sha256 of wal-g-pg-ubuntu-22.04-amd64.tar.gz in the v3.0.5 release (its .sha256 asset, re-checked).
ARG WALG_SHA256=367ee2863f5f46fde8ab89ce289ca3a43fab3117f8d580029c502b0462580846
# Full `pip --require-hashes` with a lock file belongs in the private infra repo build.

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-venv curl ca-certificates \
 && python3 -m venv /opt/patroni \
 && /opt/patroni/bin/pip install --no-cache-dir "patroni[etcd3]==${PATRONI_VERSION}" psycopg2-binary==2.9.13 \
 && curl -fsSL -o /tmp/wal-g.tar.gz \
      "https://github.com/wal-g/wal-g/releases/download/${WALG_VERSION}/wal-g-pg-ubuntu-22.04-amd64.tar.gz" \
 && echo "${WALG_SHA256}  /tmp/wal-g.tar.gz" | sha256sum -c - \
 && tar -xzf /tmp/wal-g.tar.gz -C /usr/local/bin \
 && mv /usr/local/bin/wal-g-pg-ubuntu-22.04-amd64 /usr/local/bin/wal-g \
 && rm -rf /tmp/wal-g.tar.gz /var/lib/apt/lists/*

USER postgres
# patroni.yml is mounted read-only; values come from the env file on the node. Refuse to start
# with an empty REST or etcd password: unsafe REST endpoints must never run unauthenticated.
ENTRYPOINT ["/bin/sh", "-c", ": \"${PATRONI_RESTAPI_PASSWORD:?PATRONI_RESTAPI_PASSWORD unset}\" \"${PATRONI_ETCD3_PASSWORD:?PATRONI_ETCD3_PASSWORD unset}\" \"${PATRONI_SUPERUSER_PASSWORD:?PATRONI_SUPERUSER_PASSWORD unset}\" \"${PATRONI_REPLICATION_PASSWORD:?PATRONI_REPLICATION_PASSWORD unset}\" \"${PATRONI_REWIND_PASSWORD:?PATRONI_REWIND_PASSWORD unset}\"; exec /opt/patroni/bin/patroni /etc/patroni/patroni.yml"]
