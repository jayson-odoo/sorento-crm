import http from 'k6/http';
import { group, sleep } from 'k6';
import { resolveOptions } from '../../profiles/index.js';
import { standard } from '../../lib/thresholds.js';
import { requireBeUrl } from '../../lib/env.js';
import { authHeaders } from '../../lib/auth.js';
import { isOk } from '../../lib/checks.js';

// Per-endpoint SLA targets — locked stress SLA: p95 < 1s, p99 < 2s.
const perEndpointThresholds = {
  ...standard,
  'http_req_duration{name:list_orders}':      ['p(95)<1000', 'p(99)<2000'],
  'http_req_duration{name:list_products}':    ['p(95)<1000', 'p(99)<2000'],
  'http_req_duration{name:list_shipments}':   ['p(95)<1000', 'p(99)<2000'],
  'http_req_duration{name:list_attachments}': ['p(95)<1000', 'p(99)<2000'],
  'http_req_failed{name:list_orders}':      ['rate<0.01'],
  'http_req_failed{name:list_products}':    ['rate<0.01'],
  'http_req_failed{name:list_shipments}':   ['rate<0.01'],
  'http_req_failed{name:list_attachments}': ['rate<0.01'],
};

export const options = resolveOptions({
  exec: 'listings',
  thresholds: perEndpointThresholds,
  scenarioOverrides: { peakRps: 50, preAllocatedVUs: 50, maxVUs: 300 },
});

const SEARCH_TERMS = [
  '', '', '', '',                         // 40% no search (typical user)
  'sink', 'tap', 'basin', 'mixer',
  'BCSC', 'CG-2026', 'FJ24', 'image',
  'bathroom', 'kitchen', 'chrome', 'matte',
];

function pickPageLimit(maxLimit = 200) {
  // 70% page 1 (typical), 20% pages 2-10 (browse), 10% deep/big-page (cold)
  const r = Math.random();
  if (r < 0.7) return { page: 1, limit: 25 };
  if (r < 0.9) return { page: 2 + Math.floor(Math.random() * 9), limit: 25 };
  // 10%: deep page OR larger limit (clamped to endpoint's max)
  if (Math.random() < 0.5) return { page: 20 + Math.floor(Math.random() * 30), limit: 25 };
  return { page: 1, limit: Math.min(200, maxLimit) };
}

function pickSearch() {
  return SEARCH_TERMS[Math.floor(Math.random() * SEARCH_TERMS.length)];
}

let logged = false;

export function listings() {
  const be = requireBeUrl();
  const headers = authHeaders();

  if (!logged && __ITER === 0) {
    logged = true;
    console.log(`[listings_read] BE=${be}`);
  }

  // POST /api/v1/list-query/search — registered resources only.
  // Registry: orders, products, suppliers, promotions, workflow_form_definitions, workflow_form_submissions.
  for (const resource of ['orders', 'products']) {
    group(`list-query ${resource}`, () => {
      const { page, limit } = pickPageLimit();
      const quick_search = pickSearch();
      const body = { resource, page, limit };
      if (quick_search) body.quick_search = quick_search;
      const res = http.post(
        `${be}/api/v1/list-query/search`,
        JSON.stringify(body),
        { headers, tags: { name: `list_${resource}` } },
      );
      if (__ITER === 0) {
        console.log(`[list_${resource}] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
      }
      isOk(res, `list_${resource}`);
    });
  }

  // Plain REST list endpoints (not list-query). Caps differ per endpoint.
  group('shipments', () => {
    const { page, limit } = pickPageLimit(50);
    const res = http.get(
      `${be}/api/v1/incoming-stock/shipments?page=${page}&limit=${limit}`,
      { headers, tags: { name: 'list_shipments' } },
    );
    if (__ITER === 0) {
      console.log(`[list_shipments] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
    }
    isOk(res, 'list_shipments');
  });

  group('attachments', () => {
    const { page, limit } = pickPageLimit();
    const res = http.get(
      `${be}/api/v1/resource-management/attachments/?page=${page}&limit=${limit}`,
      { headers, tags: { name: 'list_attachments' } },
    );
    if (__ITER === 0) {
      console.log(`[list_attachments] status=${res.status} body=${(res.body || '').toString().slice(0, 200)}`);
    }
    isOk(res, 'list_attachments');
  });

  sleep(1);
}

export default listings;
