/**
 * Security round S3 (#1280): `isSafeCallbackUrl` must reject every open-
 * redirect shape a `callbackUrl` query param could carry, and accept a
 * genuine same-origin path.
 */
import { describe, expect, it } from 'vitest';
import { isSafeCallbackUrl, pickLandingUrl } from './page';

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

describe('pickLandingUrl (AC-28)', () => {
  it('a deep link the user followed wins over the home path', () => {
    expect(pickLandingUrl('/orders/42', '/portal/c/ABC')).toBe('/orders/42');
  });

  it('the bare "/" the protected layout adds is not a deep link, so the home path wins', () => {
    expect(pickLandingUrl('/', '/portal/c/ABC')).toBe('/portal/c/ABC');
  });

  it('no callback and no home path lands on the CRM home', () => {
    expect(pickLandingUrl(null, null)).toBe('/');
  });

  it('an unsafe callback falls back to the home path', () => {
    expect(pickLandingUrl('//evil.com', '/portal/c/ABC')).toBe('/portal/c/ABC');
  });
});
