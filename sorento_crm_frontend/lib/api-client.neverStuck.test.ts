/**
 * L3 (NEVER-STUCK-UI S2, S3): the refusal classifiers every five-state consumer and the
 * shared retry rule branch on.
 *
 * Errors built by `extractApiError` carry no HTTP status, so a refusal is recognised by
 * the backend's own `detail` text. These pin the exact strings `dependencies.py` and
 * `modules/runtime/guards.py` produce, including the strict-mode variant the old toast
 * check missed (`One of these permissions required (module may be disabled):`).
 */
import { describe, it, expect } from 'vitest';

import {
  REQUEST_TIMED_OUT_MESSAGE,
  isAccessDenied,
  isNotFound,
  isRefused,
  isSignedOut,
  isTimedOut,
} from './api-client';

const err = (m: string) => new Error(m);

describe('isAccessDenied', () => {
  it.each([
    'Permission required: scm.dashboard.view',
    'One of these permissions required: a.b, c.d',
    'One of these permissions required (module may be disabled): a.b',
    'Module not enabled: scm',
    'Module not enabled for purchase_order',
  ])('recognises the backend 403 "%s"', (m) => {
    expect(isAccessDenied(err(m))).toBe(true);
  });

  it.each(['Server error. Try again or contact support.', 'Product not found', ''])(
    'does not treat "%s" as a refusal',
    (m) => {
      expect(isAccessDenied(err(m))).toBe(false);
    },
  );

  it('is false for a non-Error value', () => {
    expect(isAccessDenied('Permission required: x')).toBe(false);
    expect(isAccessDenied(null)).toBe(false);
    expect(isAccessDenied(undefined)).toBe(false);
  });
});

describe('isSignedOut', () => {
  it.each([
    'Not signed in or session expired. Please sign in again.',
    'Authentication required',
    'Session expired',
    'Session was revoked',
    'Session not found',
    'Account is not active',
    'Invalid token: signature mismatch',
  ])('recognises the 401 "%s"', (m) => {
    expect(isSignedOut(err(m))).toBe(true);
  });

  it('does not match a 403', () => {
    expect(isSignedOut(err('Permission required: a.b'))).toBe(false);
  });
});

describe('isNotFound', () => {
  it.each(['Product not found', 'Price tag request not found', 'Not Found'])(
    'recognises "%s"',
    (m) => {
      expect(isNotFound(err(m))).toBe(true);
    },
  );

  it('does not match a 5xx', () => {
    expect(isNotFound(err('Server error. Try again or contact support.'))).toBe(false);
  });
});

describe('isTimedOut', () => {
  it('recognises the apiFetch timeout', () => {
    expect(isTimedOut(err(REQUEST_TIMED_OUT_MESSAGE))).toBe(true);
    expect(isTimedOut(err('Something else'))).toBe(false);
  });
});

describe('isRefused (never retried)', () => {
  it('covers 401, 403, 404 and a timeout, not a 5xx', () => {
    expect(isRefused(err('Permission required: a.b'))).toBe(true);
    expect(isRefused(err('Module not enabled: scm'))).toBe(true);
    expect(isRefused(err('Session expired'))).toBe(true);
    expect(isRefused(err('Order not found'))).toBe(true);
    expect(isRefused(err(REQUEST_TIMED_OUT_MESSAGE))).toBe(true);
    expect(isRefused(err('Server error. Try again or contact support.'))).toBe(false);
  });
});
