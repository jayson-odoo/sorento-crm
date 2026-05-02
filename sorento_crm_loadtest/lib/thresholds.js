// Canonical threshold presets. Import the right one per scenario; never inline.

export const standard = {
  http_req_failed: ['rate<0.01'],
  http_req_duration: ['p(95)<800', 'p(99)<2000'],
  checks: ['rate>0.99'],
};

export const heavyWrite = {
  http_req_failed: ['rate<0.02'],
  http_req_duration: ['p(95)<1500', 'p(99)<4000'],
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
