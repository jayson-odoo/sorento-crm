/**
 * D12 - `is_active` stays on the record card as a labelled switch in both modes
 * (the seed-key delete refusal tells the user to switch the key off instead).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

import { SpecKeyRecordCard } from './SpecKeyRecordCard';
import { projectSpecKeyDraft } from '../../hooks/useSpecKeyRecord';
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

describe('SpecKeyRecordCard - Active switch (D12)', () => {
  it('view mode shows the switch disabled, reflecting the stored value', () => {
    const row = seedRow({ is_active: false });
    render(
      <SpecKeyRecordCard
        row={row}
        mode="view"
        draft={null}
        setDraft={() => {}}
        pagerNode={null}
        actions={[]}
        pending={null}
        primary={null}
      />,
    );

    const toggle = screen.getByRole('switch', { name: 'Active' });
    expect(toggle).toBeDisabled();
    expect(toggle).toHaveAttribute('aria-checked', 'false');
  });

  it('edit mode shows the switch enabled at the same place, and toggling it changes the draft', () => {
    const row = seedRow({ is_active: true });
    const draft = projectSpecKeyDraft(row);
    let current = draft;
    const setDraft = (updater: (d: typeof draft) => typeof draft) => {
      current = updater(current);
    };

    const { rerender } = render(
      <SpecKeyRecordCard
        row={row}
        mode="edit"
        draft={current}
        setDraft={setDraft}
        pagerNode={null}
        actions={[]}
        pending={null}
        primary={null}
      />,
    );

    const toggle = screen.getByRole('switch', { name: 'Active' });
    expect(toggle).not.toBeDisabled();
    expect(toggle).toHaveAttribute('aria-checked', 'true');

    fireEvent.click(toggle);
    expect(current.isActive).toBe(false);

    rerender(
      <SpecKeyRecordCard
        row={row}
        mode="edit"
        draft={current}
        setDraft={setDraft}
        pagerNode={null}
        actions={[]}
        pending={null}
        primary={null}
      />,
    );
    expect(screen.getByRole('switch', { name: 'Active' })).toHaveAttribute(
      'aria-checked',
      'false',
    );
  });
});
