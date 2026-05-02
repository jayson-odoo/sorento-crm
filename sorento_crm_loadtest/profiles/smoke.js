// 1 VU constant for 1 minute. CI gate.
export function smoke({ exec = 'default' }) {
  return {
    smoke: {
      executor: 'constant-vus',
      vus: 1,
      duration: '1m',
      exec,
      tags: { profile: 'smoke' },
    },
  };
}
