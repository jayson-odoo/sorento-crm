// Ramp past peak until thresholds break. Find the breaking point.
export function stress({ exec = 'default', peakRps = 50, preAllocatedVUs = 100, maxVUs = 600 } = {}) {
  return {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs,
      maxVUs,
      stages: [
        { target: peakRps, duration: '2m' },
        { target: peakRps * 2, duration: '5m' },
        { target: peakRps * 3, duration: '5m' },
        { target: peakRps * 4, duration: '5m' },
        { target: 0, duration: '1m' },
      ],
      exec,
      tags: { profile: 'stress' },
    },
  };
}
