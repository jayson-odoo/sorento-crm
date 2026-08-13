import { describe, it, expect } from 'vitest';

import {
  revisionBadgeLabel,
  stripRevisionSuffix,
  withRevisionSuffix,
} from './document-number';

describe('withRevisionSuffix', () => {
  it('renders the bare number at revision 0 (no -R0)', () => {
    expect(withRevisionSuffix('SI-26-0184', 0)).toBe('SI-26-0184');
  });

  it('renders the bare number when the counter is missing', () => {
    expect(withRevisionSuffix('SI-26-0184', null)).toBe('SI-26-0184');
    expect(withRevisionSuffix('SI-26-0184', undefined)).toBe('SI-26-0184');
  });

  it('appends -R{n} from the denormalized counter', () => {
    expect(withRevisionSuffix('SI-26-0184', 2)).toBe('SI-26-0184-R2');
    expect(withRevisionSuffix('PR26-0332', 11)).toBe('PR26-0332-R11');
  });

  it('returns null when there is no document number', () => {
    expect(withRevisionSuffix(null, 3)).toBeNull();
    expect(withRevisionSuffix('   ', 3)).toBeNull();
  });
});

describe('revisionBadgeLabel', () => {
  it('is null at revision 0 so the list shows no badge', () => {
    expect(revisionBadgeLabel(0)).toBeNull();
    expect(revisionBadgeLabel(null)).toBeNull();
  });

  it('reads "Rev N" from the counter', () => {
    expect(revisionBadgeLabel(1)).toBe('Rev 1');
    expect(revisionBadgeLabel(7)).toBe('Rev 7');
  });
});

describe('stripRevisionSuffix', () => {
  it('recovers the stored number from a suffixed one', () => {
    expect(stripRevisionSuffix('SI-26-0184-R2')).toBe('SI-26-0184');
    expect(stripRevisionSuffix('SI-26-0184')).toBe('SI-26-0184');
  });

  it('is the exact inverse of the render helper', () => {
    expect(stripRevisionSuffix(withRevisionSuffix('PR26-0334', 4))).toBe('PR26-0334');
  });
});
