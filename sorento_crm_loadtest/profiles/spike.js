// 0 -> 2x peak in 30s, hold 1 minute, drop. Recovery behavior.
// Env: K6_PEAK_RPS, K6_MAX_VUS.
export function spike({ exec = 'default', peakRps = 50, preAllocatedVUs = 100, maxVUs = 400 } = {}) {
  const peak = Number(__ENV.K6_PEAK_RPS || peakRps);
  const maxV = Number(__ENV.K6_MAX_VUS || maxVUs);
  const preV = Math.max(preAllocatedVUs, Math.min(peak * 2, maxV));
  return {
    spike: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: preV,
      maxVUs: maxV,
      stages: [
        { target: peak * 2, duration: '30s' },
        { target: peak * 2, duration: '1m' },
        { target: 0, duration: '30s' },
      ],
      exec,
      tags: { profile: 'spike' },
    },
  };
}
