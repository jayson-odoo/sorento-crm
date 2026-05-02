import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { standard } from '../../lib/thresholds.js';
import { login } from '../../lib/auth.js';

export const options = resolveOptions({
  exec: 'authFlow',
  thresholds: standard,
  scenarioOverrides: { peakRps: 20, preAllocatedVUs: 20, maxVUs: 100 },
});

const EMAIL = __ENV.LOADTEST_USER_EMAIL || 'loadtest@sorento.local';
const PASSWORD = __ENV.LOADTEST_USER_PASSWORD || 'changeme';

export function authFlow() {
  login(EMAIL, PASSWORD);
  sleep(1);
}

export default authFlow;
