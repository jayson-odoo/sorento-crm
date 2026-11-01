# PLAN: retire n8n, reuse its box as the HA standby (N8N-DECOM-HA)

Status: planning (lane N8N-DECOM-HA, 1 Nov 2026). Plan only: nothing in production changes from
this lane. Track: L (cross-repo, prod infra), LEAD pattern; each build step below is its own lane.

Owner, 1 Nov 2026: retire n8n now and make the n8n box serve as the HA standby.

Builds on `documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md` (HA plan v2, PR #1915), which
kept n8n on node B "unchanged, for Tier 1" (section 6 there). This plan replaces that section.

Rules: no addresses, hostnames, keys or staff names here; prod details live outside the repo.
UNVERIFIED marks every fact this lane could not check from the repo.

## 1. Inventory: n8n workflows

(in progress)

## 2. Inventory: CRM and MCP paths that touch n8n

(in progress)

## 3. Inventory: what else runs on the n8n box

(in progress)

## 4. Decommission order (zero chat downtime, rollback per step)

(in progress)

## 5. HA Tier 1 on the freed box: changes to plan v2

(in progress)

## 6. Owner questions

(in progress)
