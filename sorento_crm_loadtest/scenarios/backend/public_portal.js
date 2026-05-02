import http from 'k6/http';
import { sleep, group } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { standard } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { isOk } from '../../lib/checks.js';

export const options = resolveOptions({
  exec: 'portal',
  thresholds: standard,
  scenarioOverrides: { peakRps: 20, preAllocatedVUs: 20, maxVUs: 100 },
});

const CONTACT_ID = __ENV.PORTAL_CONTACT_ID || '';
const SPACE_ID = __ENV.PORTAL_SPACE_ID || '';

export function portal() {
  if (!CONTACT_ID || !SPACE_ID) {
    throw new Error('set PORTAL_CONTACT_ID + PORTAL_SPACE_ID env for the portal scenario');
  }
  const be = requireBeUrl();
  group('request-otp', () => {
    const res = http.post(
      `${be}/api/v1/public/portal/request-otp`,
      JSON.stringify({ contact_id: CONTACT_ID, space_id: SPACE_ID }),
      { headers: { 'Content-Type': 'application/json' }, tags: { name: 'portal_request_otp' } },
    );
    isOk(res, 'portal_request_otp');
  });
  sleep(1);
}

export default portal;
