/**
 * attachmentCompanyLabel - one reading of the owning company for both the
 * detail page card and the All-files modal, so the two cannot drift.
 */
import { describe, it, expect } from 'vitest';
import { attachmentCompanyLabel } from './attachment.types';

describe('attachmentCompanyLabel', () => {
  it('names the company when resolved', () => {
    expect(attachmentCompanyLabel({ company_id: 'x', company_name: 'Mocha' })).toBe('Mocha');
  });

  it('reads Shared when the file belongs to no company', () => {
    expect(attachmentCompanyLabel({ company_id: null, company_name: null })).toBe('Shared');
    expect(attachmentCompanyLabel({})).toBe('Shared');
  });

  it('never prints the id when the name is missing', () => {
    expect(attachmentCompanyLabel({ company_id: 'x', company_name: '  ' })).toBe('-');
  });
});
