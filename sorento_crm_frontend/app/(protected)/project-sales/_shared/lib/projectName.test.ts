import { describe, expect, it } from 'vitest';
import { PROJECT_NAME_MAX_LENGTH, projectDisplayName } from './projectName';

describe('projectDisplayName', () => {
  it('shows the name when there is one', () => {
    expect(projectDisplayName({ name: 'Residensi Contoh Phase 2', title: 'CADANGAN ...' })).toBe(
      'Residensi Contoh Phase 2',
    );
  });

  it('falls back to the title when the name is missing, null or blank', () => {
    expect(projectDisplayName({ title: 'CADANGAN ...' })).toBe('CADANGAN ...');
    expect(projectDisplayName({ name: null, title: 'CADANGAN ...' })).toBe('CADANGAN ...');
    expect(projectDisplayName({ name: '   ', title: 'CADANGAN ...' })).toBe('CADANGAN ...');
  });

  it('caps the name at the column length', () => {
    expect(PROJECT_NAME_MAX_LENGTH).toBe(80);
  });
});
