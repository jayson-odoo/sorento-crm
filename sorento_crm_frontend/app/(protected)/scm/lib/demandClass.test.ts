import { describe, expect, it } from 'vitest';
import { demandClassBadge } from './demandClass';

describe('demandClassBadge', () => {
  it('reads other as a neutral Other chip, not Unclassified', () => {
    expect(demandClassBadge('other')).toEqual({ variant: 'secondary', label: 'Other' });
  });
  it('keeps retail and project, and unset as Unclassified', () => {
    expect(demandClassBadge('retail').label).toBe('Retail');
    expect(demandClassBadge('project').label).toBe('Project');
    expect(demandClassBadge(null).label).toBe('Unclassified');
  });
});
