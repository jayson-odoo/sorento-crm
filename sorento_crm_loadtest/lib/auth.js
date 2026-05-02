import http from 'k6/http';
import { check, fail } from 'k6';
import { requireBeUrl } from './env.js';

const tokenByVu = {};

export function login(email, password) {
  const url = `${requireBeUrl()}/api/v1/login`;
  const res = http.post(
    url,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'auth_login' } },
  );
  const ok = check(res, {
    'login 200': (r) => r.status === 200,
    'login has token': (r) => r.json('access_token') || r.json('token'),
  });
  if (!ok) {
    fail(`login failed: status=${res.status} body=${res.body}`);
  }
  return res.json('access_token') || res.json('token');
}

export function getToken() {
  const vu = __VU;
  if (tokenByVu[vu]) return tokenByVu[vu];
  const email = __ENV.LOADTEST_USER_EMAIL || 'loadtest@sorento.local';
  const password = __ENV.LOADTEST_USER_PASSWORD || 'changeme';
  const token = login(email, password);
  tokenByVu[vu] = token;
  return token;
}

export function clearToken() {
  delete tokenByVu[__VU];
}

export function authHeaders(extra = {}) {
  return {
    Authorization: `Bearer ${getToken()}`,
    'Content-Type': 'application/json',
    ...extra,
  };
}

export function externalHeaders(extra = {}) {
  const key = __ENV.EXTERNAL_API_KEY || '';
  if (!key) fail('EXTERNAL_API_KEY missing in env');
  return {
    'X-API-Key': key,
    'Content-Type': 'application/json',
    ...extra,
  };
}
