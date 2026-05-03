// Canonical threshold presets. Import the right one per scenario; never inline.
//
// Baselines from prod smoke (1 VU, unloaded) for the CRM listings:
//   list endpoints p95 ≈ 60-90ms, p99 ≈ 70-200ms.
// Rule: under-load SLA = baseline × 3-4. So p95 target ≈ 300ms.

export const standard = {
  http_req_failed: ['rate<0.01'],
  http_req_duration: ['p(95)<300', 'p(99)<800'],
  checks: ['rate>0.99'],
};

export const heavyWrite = {
  http_req_failed: ['rate<0.02'],
  http_req_duration: ['p(95)<800', 'p(99)<2500'],
  checks: ['rate>0.99'],
};

export const n8n = {
  http_req_failed: ['rate<0.01'],
  http_req_duration: ['p(95)<1500', 'p(99)<3000'],
  checks: ['rate>0.99'],
};

export const ai = {
  http_req_failed: ['rate<0.05'],
  http_req_duration: ['p(95)<6000', 'p(99)<15000'],
  checks: ['rate>0.95'],
};

export const ssr = {
  http_req_failed: ['rate<0.01'],
  http_req_duration: ['p(95)<2000', 'p(99)<4000'],
  checks: ['rate>0.99'],
};

export const browser = {
  // k6 browser metrics
  browser_web_vital_lcp: ['p(95)<3000'],
  browser_web_vital_fcp: ['p(95)<2000'],
  checks: ['rate>0.95'],
};
