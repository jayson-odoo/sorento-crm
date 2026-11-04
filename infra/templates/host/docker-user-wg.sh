#!/bin/sh
# DOCKER-USER rules for the private link, BOTH CRM nodes (HA-CF-FAILOVER active-active, security
# review S3). Ports Docker publishes on <THIS_WG_IP> are forwarded by Docker's own chains: UFW and
# INPUT never see them, and the DNAT matches the address, not the interface. These rules sit in
# DOCKER-USER, which Docker evaluates first. Idempotent; run at boot after Docker (a systemd unit
# or the provider's firewall hook). THIS CHANGES PROD.
set -eu
WG_IF=wg0
THIS_WG_IP="<THIS_WG_IP>"
PEER_WG_IP="<PEER_WG_IP>"
COMPOSE_SUBNET="<COMPOSE_SUBNET>"

iptables -N SORENTO-HA 2>/dev/null || iptables -F SORENTO-HA
# Postgres (5432) and Redis (6379) published on the private address: only the peer, only over wg0.
iptables -A SORENTO-HA -p tcp -m conntrack --ctorigdst "$THIS_WG_IP" -m multiport --dports 5432,6379 \
  -i "$WG_IF" -s "$PEER_WG_IP" -j RETURN
iptables -A SORENTO-HA -p tcp -m conntrack --ctorigdst "$THIS_WG_IP" -m multiport --dports 5432,6379 -j DROP
# Out over the link: only the CRM compose network (Postgres, pgbouncer, Redis, HAProxy, the app),
# not any other container on this box.
iptables -A SORENTO-HA -o "$WG_IF" ! -s "$COMPOSE_SUBNET" -j DROP
iptables -C DOCKER-USER -j SORENTO-HA 2>/dev/null || iptables -I DOCKER-USER -j SORENTO-HA
