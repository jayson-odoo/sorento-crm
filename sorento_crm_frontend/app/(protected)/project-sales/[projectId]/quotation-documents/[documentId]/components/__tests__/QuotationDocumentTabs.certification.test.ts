/** QUOTE-CERT-TAB FE-1: the Certification tab is the LAST tab and a route segment. */
import { describe, expect, it } from 'vitest';

import { quotationDocumentTabs } from '../QuotationDocumentTabs';

describe('quotationDocumentTabs certification', () => {
  const tabs = quotationDocumentTabs('p1', 'd1');

  it('ends with the certification tab titled Certification', () => {
    const last = tabs[tabs.length - 1];
    expect(last.key).toBe('certification');
    expect(last.title).toBe('Certification');
    expect(last.path).toBe('/project-sales/p1/quotation-documents/d1/certification');
  });

  it('comes after the spec sheet tab and keeps the others in order', () => {
    const keys = tabs.map((t) => t.key);
    expect(keys.indexOf('certification')).toBe(keys.indexOf('spec-sheet') + 1);
    expect(keys.slice(0, 6)).toEqual(['header', 'cover-letter', 'terms', 'signatures', 'feedback', 'spec-sheet']);
    expect(keys).toHaveLength(7);
  });
});
