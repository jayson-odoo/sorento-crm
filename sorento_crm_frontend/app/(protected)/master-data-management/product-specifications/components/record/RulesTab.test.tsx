/**
 * AC-S1.6, AC-S1.11, AC-S1.14 - How it is read: a structured grid, one row per
 * rule, one column per part. No sentence anywhere, no "default"/"shipped" badge,
 * no Advanced.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('../../hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({ result: null, loading: false, error: null }),
}));

import { RulesTab } from './RulesTab';
import type { SpecDerivationRule, SpecRegistryKey } from '../../types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function baseRow(overrides: Partial<SpecRegistryKey> = {}): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish or colour',
    data_type: 'enum',
    unit: null,
    allowed_values: ['gunmetal'],
    synonyms: {},
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

const gunmetalRule: SpecDerivationRule = {
  builder: { kind: 'code', code_match: 'ends_with', texts: ['-GM'], value: 'gunmetal' },
};

describe('RulesTab - a structured grid, never a sentence (AC-S1.6, AC-S1.14)', () => {
  it('renders the rule as labelled grid cells', () => {
    const row = baseRow({ effective_rules: [gunmetalRule] });
    render(withClient(<RulesTab row={row} registry={[row]} mode="view" draft={null} setDraft={() => {}} />));

    expect(screen.getByText('Ends with: -GM')).toBeInTheDocument();
    expect(screen.getByText('Gunmetal')).toBeInTheDocument();
    expect(screen.queryByText(/^If /)).not.toBeInTheDocument();
  });

  it('renders no "default", "shipped" or "built in" badge, and no Advanced', () => {
    const row = baseRow({ effective_rules: [gunmetalRule] });
    render(withClient(<RulesTab row={row} registry={[row]} mode="view" draft={null} setDraft={() => {}} />));

    expect(screen.queryByText('default')).not.toBeInTheDocument();
    expect(screen.queryByText('shipped')).not.toBeInTheDocument();
    expect(screen.queryByText(/built in/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/advanced/i)).not.toBeInTheDocument();
  });

  it('an empty key shows "No rules yet" with no CTA in view mode', () => {
    const row = baseRow({ effective_rules: [], derivation_rules: [] });
    render(withClient(<RulesTab row={row} registry={[row]} mode="view" draft={null} setDraft={() => {}} />));

    expect(screen.getByText('No rules yet')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Add a rule/i })).not.toBeInTheDocument();
  });

  it('Add a rule is offered in edit mode only', () => {
    const row = baseRow({ effective_rules: [gunmetalRule] });
    render(
      withClient(
        <RulesTab
          row={row}
          registry={[row]}
          mode="edit"
          draft={{
            label: row.label,
            unit: '',
            isActive: true,
            maxValue: '',
            liveValues: row.allowed_values,
            droppedValues: [],
            words: {},
            droppedWords: {},
            valueLabels: {},
            rules: [gunmetalRule],
          }}
          setDraft={() => {}}
        />,
      ),
    );

    expect(screen.getByRole('button', { name: 'Add a rule' })).toBeInTheDocument();
  });
});
