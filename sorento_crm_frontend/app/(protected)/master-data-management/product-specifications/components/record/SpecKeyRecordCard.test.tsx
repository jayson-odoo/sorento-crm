/**
 * AC-S3.7 - the record card shows the label once (the page title carries it) and
 * one type chip; no code name, no "Built in", no rule count, no "Unit None", no
 * duplicate "Active", no Advanced.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';

import { SpecKeyRecordCard } from './SpecKeyRecordCard';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function seedRow(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish or colour',
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

describe('SpecKeyRecordCard - one type chip, nothing else (AC-S3.7)', () => {
  it('shows the type chip, and no label (the page title carries it)', () => {
    const row = seedRow({ label: 'Finish or colour', data_type: 'enum' });
    renderCard(row, 'view');

    expect(screen.getByText('List')).toBeInTheDocument();
    expect(screen.queryByText('Finish or colour')).not.toBeInTheDocument();
  });

  it('renders the same in edit mode - nothing on the card is editable', () => {
    const row = seedRow({ is_active: true });
    renderCard(row, 'edit');

    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows no code name, no source badge, no rule count, no duplicate Active', () => {
    const row = seedRow({ spec_key: 'finish', source: 'user', is_active: true, unit: 'mm' });
    renderCard(row, 'view');

    expect(screen.queryByText('finish')).not.toBeInTheDocument();
    expect(screen.queryByText('User')).not.toBeInTheDocument();
    expect(screen.queryByText('Seed')).not.toBeInTheDocument();
    expect(screen.queryByText('Active')).not.toBeInTheDocument();
    expect(screen.queryByText(/unit/i)).not.toBeInTheDocument();
  });
});
