import { describe, it, expect } from 'vitest';

import { sanitizeLinked } from './useAttachmentIntegrationLog';
import { deriveLinkedFromAttachment } from './IntegrationPanel';

describe('sanitizeLinked', () => {
  it('drops malformed entries from an untrusted n8n payload and keeps the valid one', () => {
    const result = sanitizeLinked([
      { entity_id: 'x' }, // no entity_type
      { entity_type: 'product' }, // no entity_id
      null,
      'not-an-object',
      {
        entity_type: 'promotion',
        entity_id: 'promo-1',
        display_name: 'Promo One',
        matched_by: 'filename_token:PROMO1',
      },
    ]);
    expect(result).toEqual([
      {
        entity_type: 'promotion',
        entity_id: 'promo-1',
        display_name: 'Promo One',
        matched_by: 'filename_token:PROMO1',
      },
    ]);
  });

  it('defaults display_name to entity_id when missing', () => {
    const result = sanitizeLinked([{ entity_type: 'product', entity_id: 'prod-1' }]);
    expect(result).toEqual([
      {
        entity_type: 'product',
        entity_id: 'prod-1',
        display_name: 'prod-1',
        matched_by: 'unknown',
      },
    ]);
  });

  it('returns [] for non-array input', () => {
    expect(sanitizeLinked(undefined)).toEqual([]);
    expect(sanitizeLinked(null)).toEqual([]);
    expect(sanitizeLinked({ entity_type: 'product', entity_id: 'x' })).toEqual([]);
    expect(sanitizeLinked('linked')).toEqual([]);
  });
});

describe('deriveLinkedFromAttachment', () => {
  it('derives a certificate entry from linked_certificates', () => {
    const result = deriveLinkedFromAttachment({
      linked_certificates: [{ id: 'cert-1', name: 'ISO 9001' }],
    });
    expect(result).toEqual([
      {
        entity_type: 'certificate',
        entity_id: 'cert-1',
        display_name: 'ISO 9001',
        matched_by: 'manual_or_n8n',
      },
    ]);
  });

  it('falls back to the id when the certificate has no name', () => {
    const result = deriveLinkedFromAttachment({
      linked_certificates: [{ id: 'cert-2', name: '' }],
    });
    expect(result).toEqual([
      {
        entity_type: 'certificate',
        entity_id: 'cert-2',
        display_name: 'cert-2',
        matched_by: 'manual_or_n8n',
      },
    ]);
  });

  it('returns [] when the attachment is null', () => {
    expect(deriveLinkedFromAttachment(null)).toEqual([]);
  });
});
