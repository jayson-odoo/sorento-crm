# Host prep for the Patroni watchdog (both CRM nodes)

Plan: documentation/plans/infra/PLAN-ha-tier1-n8n-box-27oct.md section 2 (watchdog row).

1. Load softdog now and at boot:
   `echo softdog | sudo tee /etc/modules-load.d/softdog.conf && sudo modprobe softdog`
2. Give the container's postgres uid the device (the pgvector image's postgres is uid 999;
   check with `docker run --rm <image> id postgres`):
   `sudo cp 60-watchdog.rules /etc/udev/rules.d/ && sudo udevadm control --reload && sudo udevadm trigger`
3. Recreate the db container; the Patroni log must show "watchdog activated". Then set
   `watchdog.mode: required` in patroni.yml.
