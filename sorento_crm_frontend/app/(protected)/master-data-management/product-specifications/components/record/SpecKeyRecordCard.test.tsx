/**
 * The record header card (fix round 5, owner ruling 27 Sep 13:20 MYT: "still
 * pretty empty"). Like every other record header (Users & Access), the card above
 * the tabs carries the specification's identity: the name as the title, the In use
 * state as a pill, the type, the choices count, the products count and when the
 * catalogue was last read. It never renders as an empty box, in read or edit mode.
 * Still no code name, no "Built in", no rule count (AC-S3.7).
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen, within } from '@testing-library/react';

import { SpecKeyRecordCard } from './SpecKeyRecordCard';
import { formatDate } from '@/lib/helpers';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function seedRow(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome', 'rose_gold', 'matt_black'],
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

const LAST_READ = '2026-09-26T08:15:00';

function renderCard(
  row: SpecRegistryKey,
  mode: 'view' | 'edit',
  extra: Partial<React.ComponentProps<typeof SpecKeyRecordCard>> = {},
) {
  return render(
    <SpecKeyRecordCard
      row={row}
      productsCount={1234}
      lastReadAt={LAST_READ}
      mode={mode}
      pagerNode={<span>1 of 12</span>}
      actions={[]}
      pending={null}
      primary={<button type="button">Edit</button>}
      {...extra}
    />,
  );
}

const field = (label: string) => screen.getByTestId(`spec-header-${label}`);

describe.each(['view', 'edit'] as const)('SpecKeyRecordCard in %s mode - the record header', (mode) => {
  it('renders the name as the title', () => {
    renderCard(seedRow({ label: 'Finish or colour' }), mode);
    expect(screen.getByRole('heading', { name: 'Finish or colour' })).toBeInTheDocument();
  });

  it('renders In use as a pill, and Not in use when the specification is off', () => {
    const { unmount } = renderCard(seedRow({ is_active: true }), mode);
    expect(screen.getByTestId('spec-header-state')).toHaveTextContent('In use');
    unmount();
    renderCard(seedRow({ is_active: false }), mode);
    expect(screen.getByTestId('spec-header-state')).toHaveTextContent('Not in use');
  });

  it('renders the type, the choices count, the products count and when it was last read', () => {
    renderCard(seedRow(), mode);
    expect(within(field('type')).getByText('List')).toBeInTheDocument();
    expect(within(field('choices')).getByText('3')).toBeInTheDocument();
    expect(within(field('products')).getByText((1234).toLocaleString())).toBeInTheDocument();
    expect(field('last-read')).toHaveTextContent(formatDate(LAST_READ));
  });

  it('folds the unit into a Number type and shows no choices count for it', () => {
    renderCard(seedRow({ data_type: 'numeric', unit: 'mm', allowed_values: [] }), mode);
    expect(within(field('type')).getByText('Number (mm)')).toBeInTheDocument();
    expect(field('choices')).toHaveTextContent('None');
  });

  it('counts Product class choices from the class list, not its empty allowed values', () => {
    renderCard(seedRow({ spec_key: 'class', label: 'Product class', allowed_values: [] }), mode, {
      classChoiceCount: 41,
    });
    expect(within(field('choices')).getByText('41')).toBeInTheDocument();
  });

  it('never renders empty: identity still shows before the counts arrive', () => {
    renderCard(seedRow(), mode, { productsCount: undefined, lastReadAt: undefined });
    expect(screen.getByRole('heading', { name: 'Finish or colour' })).toBeInTheDocument();
    expect(field('products')).not.toHaveTextContent(/^Products$/);
    expect(field('last-read')).not.toHaveTextContent(/^Last read$/);
  });

  it('says Not read yet when no product carries it', () => {
    renderCard(seedRow(), mode, { productsCount: 0, lastReadAt: null });
    expect(within(field('products')).getByText('0')).toBeInTheDocument();
    expect(field('last-read')).toHaveTextContent('Not read yet');
  });

  it('keeps the pager and the primary action beside the identity', () => {
    renderCard(seedRow(), mode);
    expect(screen.getByText('1 of 12')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Edit' })).toBeInTheDocument();
  });

  it('shows no code name, no source badge, no rule count, and nothing editable', () => {
    renderCard(seedRow({ spec_key: 'finish', source: 'user' }), mode);
    expect(screen.queryByText('finish')).not.toBeInTheDocument();
    expect(screen.queryByText('User')).not.toBeInTheDocument();
    expect(screen.queryByText('Seed')).not.toBeInTheDocument();
    expect(screen.queryByText(/rules?$/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('switch')).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });
});
