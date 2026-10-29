# Postgres 17 + pgvector + Patroni + WAL-G, for both CRM nodes.
# Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2.
# Pin every version at build time in the private infra repo; the tags below are placeholders.
FROM pgvector/pgvector:pg17

ARG PATRONI_VERSION=<PIN>
ARG WALG_VERSION=<PIN>

RUN apt-get update \
 && apt-get install -y --no-install-recommends python3-venv curl ca-certificates \
 && python3 -m venv /opt/patroni \
 && /opt/patroni/bin/pip install --no-cache-dir "patroni[etcd3]==${PATRONI_VERSION}" psycopg2-binary \
 && curl -fsSL -o /tmp/wal-g.tar.gz \
      "https://github.com/wal-g/wal-g/releases/download/${WALG_VERSION}/wal-g-pg-ubuntu-22.04-amd64.tar.gz" \
 && tar -xzf /tmp/wal-g.tar.gz -C /usr/local/bin \
 && mv /usr/local/bin/wal-g-pg-ubuntu-22.04-amd64 /usr/local/bin/wal-g \
 && rm -rf /tmp/wal-g.tar.gz /var/lib/apt/lists/*

USER postgres
# patroni.yml is mounted read-only; values come from the env file on the node. Refuse to start
# with an empty REST or etcd password: unsafe REST endpoints must never run unauthenticated.
ENTRYPOINT ["/bin/sh", "-c", ": \"${PATRONI_RESTAPI_PASSWORD:?PATRONI_RESTAPI_PASSWORD unset}\" \"${PATRONI_ETCD3_PASSWORD:?PATRONI_ETCD3_PASSWORD unset}\" \"${PATRONI_SUPERUSER_PASSWORD:?PATRONI_SUPERUSER_PASSWORD unset}\" \"${PATRONI_REPLICATION_PASSWORD:?PATRONI_REPLICATION_PASSWORD unset}\" \"${PATRONI_REWIND_PASSWORD:?PATRONI_REWIND_PASSWORD unset}\"; exec /opt/patroni/bin/patroni /etc/patroni/patroni.yml"]
