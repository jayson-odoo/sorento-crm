// Ramp past peak until thresholds break. Find the breaking point.
// Env overrides:
//   K6_PEAK_RPS=200          target peak (drives all stages)
//   K6_STAGE_MIN=5           minutes per ramp stage (default 5)
//   K6_MAX_VUS=1500          ceiling on VU pool
export function stress({ exec = 'default', peakRps = 50, preAllocatedVUs = 100, maxVUs = 600 } = {}) {
  const peak = Number(__ENV.K6_PEAK_RPS || peakRps);
  const stageMin = Number(__ENV.K6_STAGE_MIN || 5);
  const maxV = Number(__ENV.K6_MAX_VUS || maxVUs);
  const preV = Math.max(preAllocatedVUs, Math.min(peak * 2, maxV));
  return {
    stress: {
      executor: 'ramping-arrival-rate',
      startRate: 0,
      timeUnit: '1s',
      preAllocatedVUs: preV,
      maxVUs: maxV,
      stages: [
        { target: peak, duration: '2m' },
        { target: peak * 2, duration: `${stageMin}m` },
        { target: peak * 3, duration: `${stageMin}m` },
        { target: peak * 4, duration: `${stageMin}m` },
        { target: 0, duration: '1m' },
      ],
      exec,
      tags: { profile: 'stress' },
    },
  };
}
