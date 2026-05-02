import http from 'k6/http';
import { sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { heavyWrite } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { externalHeaders } from '../../lib/auth.js';
import { unique } from '../../lib/data.js';
import { isOk } from '../../lib/checks.js';

export const options = resolveOptions({
  exec: 'externalCreate',
  thresholds: heavyWrite,
  scenarioOverrides: { peakRps: 20, preAllocatedVUs: 20, maxVUs: 100 },
});

export function externalCreate() {
  const be = requireBeUrl();
  const body = {
    customer_reference: unique('LOADTEST-SI'),
    notes: `LOADTEST VU=${__VU} ITER=${__ITER}`,
    items: [{ description: 'loadtest item', quantity: 1 }],
  };
  const res = http.post(
    `${be}/api/v1/external/stock-inquiries`,
    JSON.stringify(body),
    { headers: externalHeaders(), tags: { name: 'external_stock_inquiry_create' } },
  );
  isOk(res, 'external_stock_inquiry_create');
  sleep(1);
}

export default externalCreate;
