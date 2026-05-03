// Ramp 0 -> peak RPS, hold N minutes. Expected-peak-hour profile.
// Env overrides:
//   K6_PEAK_RPS=200          peak RPS
//   K6_HOLD_MIN=10           minutes at peak
//   K6_MAX_VUS=600           ceiling on VU pool
export function load({ exec = 'default', peakRps = 50, preAllocatedVUs = 50, maxVUs = 200 } = {}) {
  const peak = Number(__ENV.K6_PEAK_RPS || peakRps);
  const hold = Number(__ENV.K6_HOLD_MIN || 10);
  const maxV = Number(__ENV.K6_MAX_VUS || maxVUs);
  const preV = Math.max(preAllocatedVUs, Math.min(peak, maxV));
  return {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: preV,
      maxVUs: maxV,
      stages: [
        { target: Math.floor(peak / 2), duration: '1m' },
        { target: peak, duration: '2m' },
        { target: peak, duration: `${hold}m` },
        { target: 0, duration: '30s' },
      ],
      exec,
      tags: { profile: 'load' },
    },
  };
}
