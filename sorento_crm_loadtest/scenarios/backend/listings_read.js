import http from 'k6/http';
import { group, sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { standard } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { authHeaders } from '../../lib/auth.js';
import { isOk } from '../../lib/checks.js';

export const options = resolveOptions({
  exec: 'listings',
  thresholds: standard,
  scenarioOverrides: { peakRps: 50, preAllocatedVUs: 50, maxVUs: 300 },
});

const RESOURCES = [
  { resource: 'order_management.orders', name: 'orders' },
  { resource: 'complaints.complaints', name: 'complaints' },
  { resource: 'user_management.contacts', name: 'contacts' },
  { resource: 'incoming_stock.shipments', name: 'shipments' },
];

export function listings() {
  const be = requireBeUrl();
  const headers = authHeaders();

  for (const r of RESOURCES) {
    group(`list-query ${r.name}`, () => {
      const res = http.post(
        `${be}/api/v1/list-query/search`,
        JSON.stringify({
          resource: r.resource,
          page: 1,
          limit: 25,
          sort: null,
          dir: null,
          query: '',
          filters: [],
        }),
        { headers, tags: { name: `list_${r.name}` } },
      );
      isOk(res, `list_${r.name}`);
    });
  }
  sleep(1);
}

export default listings;
