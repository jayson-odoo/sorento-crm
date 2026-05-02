// Peak/2, hold 1 hour. Memory leaks, connection-pool drift.
// For longer soaks, override via -e SOAK_DURATION=4h.
export function soak({ exec = 'default', peakRps = 50, preAllocatedVUs = 50, maxVUs = 200 } = {}) {
  const duration = __ENV.SOAK_DURATION || '1h';
  const sustainedRps = Math.max(1, Math.floor(peakRps / 2));
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
