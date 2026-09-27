/**
 * Fix round 4 (owner hand test, 27 Sep) on the rule modal:
 * - F1: Only when on a yes-or-no specification offers Yes and No, and stores the
 *   value the engine compares ("true" / "false"). An empty list never reads
 *   "No results found."; a specification with no choices yet says so in words.
 * - F3: the modal explains the rule in one plain sentence, the one `ruleSentence`
 *   builds, Only when included.
 */
import React from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

vi.mock('@/lib/toast', () => ({
  toast: { success: vi.fn(), error: vi.fn(), custom: vi.fn(), message: vi.fn(), dismiss: vi.fn() },
}));
vi.mock('../hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({ result: null, loading: false, error: null }),
}));
vi.mock('../hooks/useSpecPreview', () => ({
  useSpecPreview: () => ({ status: 'idle', result: null, error: null, run: vi.fn() }),
}));
vi.mock('../services/productSpecService', () => ({
  fetchProductPickerOptions: vi.fn().mockResolvedValue([]),
}));

import { SpecRuleModal } from './SpecRuleModal';
import type { SpecDerivationRule, SpecRegistryKey } from '../types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const FINISH: SpecRegistryKey = {
  spec_key: 'finish',
  label: 'Finish or colour',
  data_type: 'enum',
  unit: null,
  allowed_values: ['black', 'chrome'],
  excluded_values: [],
  user_values: [],
  suppressed_values: [],
  value_weights: {},
  derivation_rules: [],
  effective_rules: [],
  synonyms: {},
  value_labels: {},
  applies_when: {},
  read_from: 'rules',
  rank_weight: null,
  measured_coverage: 0,
  source: 'seed',
  user_synonyms: {},
  suppressed_synonyms: {},
  match_tolerance: 0,
  match_decay: 0,
  is_active: true,
};
const BOARD: SpecRegistryKey = {
  ...FINISH,
  spec_key: 'chopping_board',
  label: 'Chopping board',
  data_type: 'boolean',
  allowed_values: [],
};
const NEW_CHOICE: SpecRegistryKey = {
  ...FINISH,
  spec_key: 'basin_style',
  label: 'Basin style',
  allowed_values: [],
};

function renderEditing(rule: SpecDerivationRule) {
  const onSave = vi.fn();
  render(
    withClient(
      <SpecRuleModal
        open
        onOpenChange={() => {}}
        spec={FINISH}
        registry={[FINISH, BOARD, NEW_CHOICE]}
        rules={[rule]}
        editingIndex={0}
        onSave={onSave}
      />,
    ),
  );
  return { onSave };
}

const blackWhen = (spec: string, values: string[], is = true): SpecDerivationRule => ({
  builder: { kind: 'words', words: ['BLACK'], value: 'black', only_when: { spec, is, values } },
  _uid: 'r0',
});

function openItsValues() {
  const dialog = screen.getByRole('dialog', { name: /a rule/ });
  const box = within(dialog).getByText('Only when (optional)', { selector: 'label' }).closest('div')!;
  const triggers = box.querySelectorAll('[data-slot="searchable-multi-select-trigger"]');
  fireEvent.click(triggers[triggers.length - 1]);
}

describe('F1 - Only when on a yes-or-no specification', () => {
  it('offers Yes and No', () => {
    renderEditing(blackWhen('chopping_board', ['true']));
    openItsValues();
    const names = screen.getAllByRole('option').map((o) => o.textContent?.trim());
    expect(names).toEqual(expect.arrayContaining(['Yes', 'No']));
    expect(screen.queryByText('No results found.')).not.toBeInTheDocument();
    expect(document.body.textContent).not.toContain('True');
  });

  it('stores "false" for No, the value the engine compares', () => {
    const { onSave } = renderEditing(blackWhen('chopping_board', ['true']));
    openItsValues();
    fireEvent.click(screen.getByRole('option', { name: 'No' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));

    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0].builder.only_when).toEqual({
      spec: 'chopping_board',
      is: true,
      values: ['true', 'false'],
    });
  });

  it('a specification with no choices yet says so, never "No results found."', () => {
    renderEditing(blackWhen('basin_style', []));
    openItsValues();
    expect(screen.queryByText('No results found.')).not.toBeInTheDocument();
    expect(screen.getByText('Basin style has no choices yet.')).toBeInTheDocument();
  });
});

describe('F3 - the rule in one plain sentence', () => {
  it('reads the BLACK rule with its Only when', () => {
    renderEditing(blackWhen('chopping_board', ['true']));
    expect(
      screen.getByText(
        'When the description or flyer contains the word BLACK and Chopping board is Yes, set Finish or colour to Black.',
      ),
    ).toBeInTheDocument();
  });

  it('shows no sentence while the rule has nothing to read', () => {
    render(
      withClient(
        <SpecRuleModal
          open
          onOpenChange={() => {}}
          spec={FINISH}
          registry={[FINISH]}
          rules={[]}
          editingIndex={null}
          onSave={() => {}}
        />,
      ),
    );
    expect(screen.queryByTestId('rule-sentence')).not.toBeInTheDocument();
  });
});
