import http from 'k6/http';
import crypto from 'k6/crypto';
import encoding from 'k6/encoding';
import { check, fail } from 'k6';
import { requireBeUrl } from './env.js';

const tokenByVu = {};
const profileByVu = {};

function b64url(s) {
  return encoding.b64encode(s, 'rawurl');
}

function signHs256(payload, secret) {
  const header = { alg: 'HS256', typ: 'JWT' };
  const h = b64url(JSON.stringify(header));
  const p = b64url(JSON.stringify(payload));
  const data = `${h}.${p}`;
  const sig = crypto.hmac('sha256', secret, data, 'base64rawurl');
  return `${data}.${sig}`;
}

function loginForProfile(email, password) {
  const url = `${requireBeUrl()}/api/v1/auth/login`;
  const res = http.post(
    url,
    JSON.stringify({ email, password }),
    { headers: { 'Content-Type': 'application/json' }, tags: { name: 'auth_login' } },
  );
  const ok = check(res, {
    'login 200': (r) => r.status === 200,
    'login has id': (r) => !!r.json('id'),
  });
  if (!ok) {
    fail(`login failed: status=${res.status} body=${res.body}`);
  }
  return res.json();
}

export function login(email, password) {
  // Back-compat: returns minted JWT.
  const profile = loginForProfile(email, password);
  return mintJwt(profile);
}

function mintJwt(profile) {
  const secret = __ENV.NEXTAUTH_SECRET || __ENV.JWT_SECRET || '';
  if (!secret) {
    fail('NEXTAUTH_SECRET (or JWT_SECRET) missing in .env — required to mint a k6 JWT');
  }
  const ttlSec = Number(__ENV.JWT_TTL_SECONDS || 3600);
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    sub: String(profile.id),
    id: String(profile.id),
    email: profile.email,
    name: profile.name || null,
    avatar: profile.avatar || null,
    status: profile.status || 'ACTIVE',
    roleId: profile.role_id || profile.roleId || '',
    roleName: profile.role_name || profile.roleName || null,
    iat: now,
    exp: now + ttlSec,
  };
  return signHs256(payload, secret);
}

export function getToken() {
  const vu = __VU;
  if (tokenByVu[vu]) return tokenByVu[vu];

  const email = __ENV.LOADTEST_USER_EMAIL || 'loadtest@sorento.local';
  const password = __ENV.LOADTEST_USER_PASSWORD || 'changeme';

  let profile = profileByVu[vu];
  if (!profile) {
    profile = loginForProfile(email, password);
    profileByVu[vu] = profile;
  }
  const token = mintJwt(profile);
  tokenByVu[vu] = token;
  return token;
}

export function clearToken() {
  delete tokenByVu[__VU];
  delete profileByVu[__VU];
}

const RUN_ID = __ENV.K6_RUN_ID || `loadtest-${Date.now()}`;

export function correlationHeaders() {
  return {
    'X-Loadtest-Run-Id': RUN_ID,
    'X-Loadtest-VU': String(__VU),
    'X-Loadtest-Iter': String(__ITER),
  };
}

export function authHeaders(extra = {}) {
  return {
    Authorization: `Bearer ${getToken()}`,
    'Content-Type': 'application/json',
    ...correlationHeaders(),
    ...extra,
  };
}

export function externalHeaders(extra = {}) {
  const key = __ENV.EXTERNAL_API_KEY || '';
  if (!key) fail('EXTERNAL_API_KEY missing in env');
  return {
    'X-API-Key': key,
    'Content-Type': 'application/json',
    ...correlationHeaders(),
    ...extra,
  };
}
