# UAC - demand class follows the agent when the agent arrives late

Plan: `PLAN-demand-class-agent-arrival.md`. Track: small fix.

## Ingest (`/api/v1/external/ingest/sales_orders`)

- **AC-1** A sales order first pushed with no agent, for a customer whose segment is `retail`,
  lands `retail`. A second push of the same `source_ref` carrying an agent whose demand class
  is `project` leaves the order `project`.
- **AC-2** Mirror of AC-1: customer segment `project`, arriving agent `retail`, ends `retail`.
- **AC-3** Stored class, stored agent already set, a later push names a DIFFERENT agent with a
  different class: the class does not change.
- **AC-4** Stored class, no stored agent, the arriving agent carries NO demand class: the class
  does not change and is never blanked.
- **AC-5** Stored class, no stored agent, stored `order_type` says project, arriving agent is
  `retail`: the order is `project` (order type outranks the agent).
- **AC-6** A class set by hand on an order that already has an agent survives every later push.
- **AC-7** First push with no agent and a customer with no segment still warns
  `unclassified_demand` and lands NULL; the push that brings a classed agent fills it (existing
  behaviour, asserted so it cannot regress).

## Agent master backfill

- **AC-8** Setting an agent's demand class to `project` fills every NULL-class order of that
  agent with `project`, including one whose customer segment is `retail`.
- **AC-9** Orders of that agent that already carry a class are untouched, and other agents'
  NULL-class orders are untouched.
- **AC-10** Clearing an agent's demand class changes no order.
