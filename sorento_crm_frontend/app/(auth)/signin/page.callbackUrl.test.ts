/**
 * Security round S3 (#1280): `isSafeCallbackUrl` must reject every open-
 * redirect shape a `callbackUrl` query param could carry, and accept a
 * genuine same-origin path.
 */
import { describe, expect, it } from 'vitest';
import { isSafeCallbackUrl } from './page';

describe('isSafeCallbackUrl', () => {
  it('rejects a backslash-smuggled absolute URL', () => {
    expect(isSafeCallbackUrl('/\\evil.com')).toBe(false);
  });

  it('rejects a protocol-relative URL', () => {
    expect(isSafeCallbackUrl('//evil.com')).toBe(false);
  });

  it('rejects a fully-qualified cross-origin URL', () => {
    expect(isSafeCallbackUrl('https://evil.com')).toBe(false);
  });

  it('accepts a same-origin path with a query string', () => {
    expect(isSafeCallbackUrl('/orders?x=1')).toBe(true);
  });

  it('rejects null/empty', () => {
    expect(isSafeCallbackUrl(null)).toBe(false);
    expect(isSafeCallbackUrl('')).toBe(false);
  });
});
