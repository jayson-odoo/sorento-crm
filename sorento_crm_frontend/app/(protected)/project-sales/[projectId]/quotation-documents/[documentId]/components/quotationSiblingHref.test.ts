/**
 * NAV-KEEP-TAB: the quotation document's tabs are route segments, so prev/next must land on
 * the neighbour's SAME segment rather than its Header.
 */
import { describe, expect, it } from 'vitest';
import { quotationSiblingHref } from './QuotationDocumentTabs';

const base = '/project-sales/p1/quotation-documents';

describe('quotationSiblingHref', () => {
  it('keeps the open tab segment on the neighbouring document', () => {
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1/feedback`)).toBe(`${base}/d2/feedback`);
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1/cover-letter`)).toBe(`${base}/d2/cover-letter`);
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1/terms`)).toBe(`${base}/d2/terms`);
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1/signatures`)).toBe(`${base}/d2/signatures`);
  });

  it('Header (the bare path) stays bare', () => {
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1`)).toBe(`${base}/d2`);
  });

  it('a path that is not a tab (the edit form, null) lands on the Header', () => {
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1/edit`)).toBe(`${base}/d2`);
    expect(quotationSiblingHref('p1', 'd1', 'd2', null)).toBe(`${base}/d2`);
    // The retired Lines tab (PROPOSAL-HEADER-LAYOUT) is not a tab any more.
    expect(quotationSiblingHref('p1', 'd1', 'd2', `${base}/d1/lines`)).toBe(`${base}/d2`);
  });
});
