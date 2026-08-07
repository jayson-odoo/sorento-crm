import { beforeEach, describe, expect, it } from 'vitest';

import {
  clearPortalSlug,
  portalBase,
  portalDetailPath,
  portalHomePath,
  portalLodgePath,
  portalNewPath,
  portalVerifyPath,
  readPortalSlug,
  waMeUrl,
  writePortalSlug,
} from './portal-paths';

beforeEach(() => {
  window.localStorage.clear();
});

describe('slug storage', () => {
  it('round-trips and clears', () => {
    expect(readPortalSlug()).toBeNull();
    writePortalSlug('ABC123XYZ0');
    expect(readPortalSlug()).toBe('ABC123XYZ0');
    clearPortalSlug();
    expect(readPortalSlug()).toBeNull();
  });
});

describe('portalBase', () => {
  it('uses explicit slug over stored', () => {
    writePortalSlug('STORED1234');
    expect(portalBase('EXPLICIT99')).toBe('/portal/c/EXPLICIT99');
  });

  it('falls back to stored slug, then legacy', () => {
    expect(portalBase()).toBe('/portal');
    writePortalSlug('STORED1234');
    expect(portalBase()).toBe('/portal/c/STORED1234');
  });

  it('explicit null FORCES legacy even with a stored slug', () => {
    // Regression: a foreign ?token= recovery redirect must not be hijacked
    // onto this device's stored slug (wrong contact identity on verify).
    writePortalSlug('STORED1234');
    expect(portalBase(null)).toBe('/portal');
  });
});

describe('path builders', () => {
  it('builds home with type', () => {
    expect(portalHomePath({ slug: 'S1', type: 'complaint' })).toBe(
      '/portal/c/S1?type=complaint',
    );
    expect(portalHomePath()).toBe('/portal');
  });

  it('builds verify path; token only forwarded on legacy tree', () => {
    expect(portalVerifyPath({ slug: 'S1', reason: 'expired', token: 'T' })).toBe(
      '/portal/c/S1/verify?reason=expired',
    );
    expect(portalVerifyPath({ slug: null, reason: 'expired', token: 'T' })).toBe(
      '/portal/verify?reason=expired&token=T',
    );
    // Foreign-token recovery: slug null + stored slug present → STILL legacy,
    // so the dead token's own contact is recovered via /token-info.
    writePortalSlug('STORED1234');
    expect(portalVerifyPath({ slug: null, reason: 'expired', token: 'T' })).toBe(
      '/portal/verify?reason=expired&token=T',
    );
  });

  it('builds new/detail paths', () => {
    expect(portalNewPath('complaint', 'S1')).toBe('/portal/c/S1/complaint/new');
    expect(portalDetailPath('complaint', 'id-1', 'S1')).toBe(
      '/portal/c/S1/complaint/id-1',
    );
  });
});

describe('waMeUrl', () => {
  it('strips non-digits and encodes text', () => {
    expect(waMeUrl('+60 12-345 6789', 'Hi, link please')).toBe(
      'https://wa.me/60123456789?text=Hi%2C%20link%20please',
    );
  });

  it('gives the consumer intake journey its own path, separate from the typed form', () => {
    // Two doors on purpose: the form asks a dealer to type order numbers they know, the
    // lodge asks a consumer to photograph a fault they can see. One screen cannot be both.
    expect(portalLodgePath('S1')).toBe('/portal/c/S1/lodge');
    expect(portalLodgePath('S1')).not.toBe(portalNewPath('complaint', 'S1'));
  });
});
