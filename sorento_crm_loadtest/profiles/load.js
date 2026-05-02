// Ramp 0 -> peak RPS, hold 10 minutes. Expected-peak-hour profile.
export function load({ exec = 'default', peakRps = 50, preAllocatedVUs = 50, maxVUs = 200 } = {}) {
  return {
    load: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs,
      maxVUs,
      stages: [
        { target: Math.floor(peakRps / 2), duration: '1m' },
        { target: peakRps, duration: '2m' },
        { target: peakRps, duration: '10m' },
        { target: 0, duration: '30s' },
      ],
      exec,
      tags: { profile: 'load' },
    },
  };
}
