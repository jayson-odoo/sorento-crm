# Failover drill (HA-CF-FAILOVER)

`python3 infra/rehearsal/cf_drill.py [--keep]`, needs only a local Docker daemon and the
`postgres:17` image. Synthetic data, throwaway containers named `drill-*`; never points at a
real host. Takes about 5 minutes.

It starts node A (primary) and node B (streaming standby), a fake Cloudflare Load Balancing API
(pool health computed the way the real monitor would: 200 only from a reachable primary, down
after 2 failed checks), and the REAL `infra/scripts/cf_failover.py` + `ha-pg.sh` once per node,
with every window scaled to seconds (tick 1 s, check 2 s, fence 8 s, promote 14 s, app-sick 20 s).

Scenarios: steady state with a synchronous standby; link cut only; Cloudflare API down; node A
dies and comes back; primary isolated (must fence before the standby promotes); app sick with
damaged data on the old primary (re-seed, old data kept); both nodes reboot; both reboot with the
link down. A monitor samples both nodes every 0.3 s and fails the drill on any sample with two
writable databases; a writer reports acknowledged rows lost.

Last result: plan section 10. The previous Patroni rehearsal (`run.sh`, H4a) was removed with the
Patroni design.
