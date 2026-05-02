// 0 -> 2x peak in 30s, hold 1 minute, drop. Recovery behavior.
export function spike({ exec = 'default', peakRps = 50, preAllocatedVUs = 100, maxVUs = 400 } = {}) {
  return {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs,
      maxVUs,
      stages: [
        { target: peakRps * 2, duration: '30s' },
        { target: peakRps * 2, duration: '1m' },
        { target: 0, duration: '30s' },
      ],
      exec,
      tags: { profile: 'spike' },
    },
  };
}
