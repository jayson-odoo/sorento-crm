/**
 * AC-B.4, D16 - one Edit button per record page. Rules loses its "Using the
 * shipped rules" card and its own empty-state CTA; the record page's Edit button
 * is the only entry point.
 */
import React from 'react';
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { RulesTab } from './RulesTab';
import type { SpecRegistryKey } from '../../types/productSpec.types';

function baseRow(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome'],
    synonyms: {},
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

describe('RulesTab - no per-tab Edit (D16)', () => {
  it('the shipped rules list plainly with their "default" pill - no banner, no button', () => {
    const row = baseRow({
      rules_are_default: true,
      effective_rules: [{ match: 'contains', pattern: 'chrome', shipped: true }],
    });
    render(<RulesTab row={row} mode="view" draft={null} setDraft={() => {}} />);

    expect(screen.queryByText('Using the shipped rules')).not.toBeInTheDocument();
    expect(screen.getByText('default')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).not.toBeInTheDocument();
  });

  it('an empty key shows "No rules yet" with no CTA', () => {
    const row = baseRow({ effective_rules: [], derivation_rules: [] });
    render(<RulesTab row={row} mode="view" draft={null} setDraft={() => {}} />);

    expect(screen.getByText('No rules yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add rule/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /^Edit$/i })).not.toBeInTheDocument();
  });
});
