/**
 * D15b - the record card is never editable: label, slug, type + source pills, unit
 * and Active are read-only facts in both modes. Editing them lives on the Header
 * tab (see `HeaderTab.test.tsx`).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SpecKeyRecordCard } from './SpecKeyRecordCard';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function seedRow(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome'],
    synonyms: { chrome: ['chrome'] },
    excluded_values: [],
    user_values: [],
    suppressed_values: [],
    value_weights: {},
    derivation_rules: [],
    effective_rules: [],
    rules_are_default: true,
    applies_when: {},
    read_from: 'rules',
    rank_weight: 1,
    measured_coverage: null,
    source: 'seed',
    user_synonyms: {},
    suppressed_synonyms: {},
    match_tolerance: 0,
    match_decay: 0,
    is_active: true,
    ...overrides,
  } as SpecRegistryKey;
}

function renderCard(row: SpecRegistryKey, mode: 'view' | 'edit') {
  return render(
    <SpecKeyRecordCard
      row={row}
      mode={mode}
      pagerNode={null}
      actions={[]}
      pending={null}
      primary={null}
    />,
  );
}

describe('SpecKeyRecordCard - read-only in both modes (D15b)', () => {
  it('view mode shows label, unit and Active as plain facts', () => {
    const row = seedRow({ label: 'Finish', unit: 'mm', is_active: false });
    renderCard(row, 'view');

    expect(screen.getByText('Finish')).toBeInTheDocument();
    expect(screen.getByText('mm')).toBeInTheDocument();
    expect(screen.getByText('Inactive')).toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('edit mode renders the SAME facts, not inputs - nothing on the card is editable', () => {
    const row = seedRow({ label: 'Finish', unit: 'mm', is_active: true });
    renderCard(row, 'edit');

    expect(screen.getByText('Finish')).toBeInTheDocument();
    expect(screen.getByText('mm')).toBeInTheDocument();
    // "Active" appears twice with the field on (the field's own label, and the
    // badge's state text) - both read-only, neither an input.
    expect(screen.getAllByText('Active')).toHaveLength(2);
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows the slug and the type/source pills', () => {
    const row = seedRow({ spec_key: 'finish', data_type: 'enum', source: 'user' });
    renderCard(row, 'view');

    expect(screen.getByText('finish')).toBeInTheDocument();
    expect(screen.getByText('Choice')).toBeInTheDocument();
    expect(screen.getByText('User')).toBeInTheDocument();
  });
});
