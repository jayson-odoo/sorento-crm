import { check } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

// Per-endpoint error counters and latency trends so Grafana can split by `name` tag.
const errors = new Counter('loadtest_errors');
const errorRate = new Rate('loadtest_error_rate');
const statusCodes = new Counter('loadtest_status_codes');

export function isOk(res, name = 'response') {
  const ok = res.status >= 200 && res.status < 300;
  errorRate.add(!ok, { endpoint: name });
  statusCodes.add(1, { endpoint: name, status: String(res.status) });
  if (!ok) {
    errors.add(1, { endpoint: name, status: String(res.status) });
    // Inline log so the timestamp + reason are visible in run output.
    const body = (res.body || '').toString().slice(0, 200);
    console.error(`[${name}] FAIL status=${res.status} url=${res.url} body=${body}`);
  }
  return check(res, {
    [`${name} 2xx`]: (r) => r.status >= 200 && r.status < 300,
  });
}

export function isJson(res, name = 'response') {
  return check(res, {
    [`${name} json`]: (r) => {
      try { r.json(); return true; } catch (_) { return false; }
    },
  });
}

export function hasStatus(res, status, name = 'response') {
  return check(res, {
    [`${name} ${status}`]: (r) => r.status === status,
  });
}
