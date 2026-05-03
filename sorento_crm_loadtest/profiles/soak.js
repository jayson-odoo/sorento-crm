// Peak/2, hold 1 hour. Memory leaks, connection-pool drift.
// Env: SOAK_DURATION (default 1h), K6_PEAK_RPS, K6_MAX_VUS.
export function soak({ exec = 'default', peakRps = 50, preAllocatedVUs = 50, maxVUs = 200 } = {}) {
  const duration = __ENV.SOAK_DURATION || '1h';
  const peak = Number(__ENV.K6_PEAK_RPS || peakRps);
  const maxV = Number(__ENV.K6_MAX_VUS || maxVUs);
  const sustainedRps = Math.max(1, Math.floor(peak / 2));
  preAllocatedVUs = Math.max(preAllocatedVUs, Math.min(sustainedRps * 2, maxV));
  maxVUs = maxV;
  return {
    soak: {
      executor: 'constant-arrival-rate',
      rate: sustainedRps,
      timeUnit: '1s',
      duration,
      preAllocatedVUs,
      maxVUs,
      exec,
      tags: { profile: 'soak' },
    },
  };
}
