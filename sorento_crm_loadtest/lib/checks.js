import { check } from 'k6';

export function isOk(res, name = 'response') {
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
