# Host prep for the controller's watchdog (both CRM nodes)

Plan: documentation/plans/infra/PLAN-ha-cf-failover-04nov.md section 3 ("Why there can never be
two writable databases"). The failover controller (root, on the host) pets `/dev/watchdog` every
tick; if it hangs, the box reboots and Postgres comes back as a standby (rule D1).

1. Load softdog now and at boot (60 s default timeout, longer than the 15 s tick):
   `echo softdog | sudo tee /etc/modules-load.d/softdog.conf && sudo modprobe softdog`
2. Nothing else opens the device (no udev rule: the controller runs as root).
3. Check after `systemctl start cf-failover`: `dmesg | grep -i watchdog` shows it armed;
   `systemctl stop cf-failover` disarms it (log line "watchdog disarmed").
