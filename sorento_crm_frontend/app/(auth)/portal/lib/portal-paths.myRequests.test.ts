/**
 * PORTAL-P3-ROLE-MENU P3-15, P3-18: inside `/my-requests` every builder keeps the visitor under
 * `/my-requests`; anywhere else each builder returns exactly what it always did.
 */
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import {
  portalBase,
  portalDetailPath,
  portalDuplicatePath,
  portalHomePath,
  portalNewPath,
  portalRevisePath,
  portalVerifyPath,
  writePortalSlug,
} from './portal-paths';

function at(path: string) {
  window.history.pushState({}, '', path);
}

beforeEach(() => window.localStorage.clear());
afterEach(() => at('/'));

describe('portal paths under /my-requests', () => {
  it.each([
    ['/my-requests'],
    ['/my-requests/stock_inquiry/new'],
    ['/my-requests/complaint/abc'],
  ])('on %s the base is /my-requests for any slug argument', (here) => {
    at(here);
    writePortalSlug('STORED1234');
    expect(portalBase('SLUG123456')).toBe('/my-requests');
    expect(portalBase(undefined)).toBe('/my-requests');
    expect(portalBase(null)).toBe('/my-requests');
  });

  it('every builder stays under /my-requests', () => {
    at('/my-requests');
    expect(portalHomePath({ slug: 'SLUG123456', type: 'complaint' })).toBe('/my-requests?type=complaint');
    expect(portalNewPath('stock_inquiry', 'SLUG123456')).toBe('/my-requests/stock_inquiry/new');
    expect(portalDetailPath('complaint', 'id 1', 'SLUG123456')).toBe('/my-requests/complaint/id%201');
    expect(portalVerifyPath({ slug: 'SLUG123456' })).toMatch(/^\/my-requests\/verify/);
    expect(portalDuplicatePath('complaint', 'id1', 'SLUG123456')).toBe(
      '/my-requests/complaint/new?from=id1',
    );
    expect(portalRevisePath('complaint', 'id1', 'SLUG123456')).toBe('/my-requests/complaint/id1?revise=1');
  });
});

describe('portal paths outside /my-requests are unchanged', () => {
  it.each([['/'], ['/portal/c/SLUG123456'], ['/portal/verify']])('on %s', (here) => {
    at(here);
    expect(portalBase('SLUG123456')).toBe('/portal/c/SLUG123456');
    expect(portalBase(null)).toBe('/portal');
    expect(portalBase(undefined)).toBe('/portal');
    writePortalSlug('STORED1234');
    expect(portalBase(undefined)).toBe('/portal/c/STORED1234');
    expect(portalHomePath({ slug: 'SLUG123456', type: 'complaint' })).toBe(
      '/portal/c/SLUG123456?type=complaint',
    );
    expect(portalNewPath('stock_inquiry', 'SLUG123456')).toBe('/portal/c/SLUG123456/stock_inquiry/new');
    expect(portalDetailPath('complaint', 'id1', 'SLUG123456')).toBe('/portal/c/SLUG123456/complaint/id1');
    expect(portalVerifyPath({ slug: 'SLUG123456', type: 'complaint' })).toBe(
      '/portal/c/SLUG123456/verify?type=complaint',
    );
    expect(portalDuplicatePath('complaint', 'id1', 'SLUG123456')).toBe(
      '/portal/c/SLUG123456/complaint/new?from=id1',
    );
    expect(portalRevisePath('complaint', 'id1', 'SLUG123456')).toBe(
      '/portal/c/SLUG123456/complaint/id1?revise=1',
    );
  });

  it('a path that merely contains my-requests later is not the CRM tree', () => {
    at('/portal/c/SLUG123456/my-requests');
    expect(portalBase('SLUG123456')).toBe('/portal/c/SLUG123456');
  });
});
