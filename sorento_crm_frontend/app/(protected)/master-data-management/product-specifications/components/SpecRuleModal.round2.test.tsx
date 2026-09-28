/**
 * Review round 2 (PR #1302) on the rule modal:
 * - S-11 / AC-S1.7: Save rule refuses what the server refuses, with the same
 *   shared check the grid uses - no value on a Words or Code rule, a word with no
 *   letter or number, "..." in more than one phrase - so the page Save never
 *   answers 400 for a rule the modal let through.
 * - N-8: no explanatory sentence where the rule preview has nothing to show.
 */
import React from 'react';
import { beforeEach, describe, it, expect, vi } from 'vitest';
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

import { toast } from '@/lib/toast';
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
  allowed_values: ['chrome', 'gunmetal'],
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

function renderModal(rules: SpecDerivationRule[] = [], editingIndex: number | null = null) {
  const onSave = vi.fn();
  render(
    withClient(
      <SpecRuleModal
        open
        onOpenChange={() => {}}
        spec={FINISH}
        registry={[FINISH]}
        rules={rules}
        editingIndex={editingIndex}
        onSave={onSave}
      />,
    ),
  );
  return { onSave };
}

function field(label: string) {
  const dialog = screen.getByRole('dialog', { name: /a rule/ });
  return within(dialog).getByText(label, { selector: 'label' }).closest('div')!;
}

function createWords(label: string, list: string[]) {
  fireEvent.click(field(label).querySelector('button[role="combobox"]')!);
  for (const word of list) {
    fireEvent.change(screen.getByPlaceholderText('Search...'), { target: { value: word } });
    fireEvent.click(document.body.querySelector('[data-slot="searchable-multi-select-create"]')!);
  }
  // Close this popover so the next field's own search box is the only one.
  fireEvent.click(field(label).querySelector('button[role="combobox"]')!);
}

function switchKind(label: string) {
  fireEvent.click(field('Kind').querySelector('button[role="combobox"]')!);
  fireEvent.click(screen.getByRole('option', { name: label }));
}

const saveButton = () => screen.getByRole('button', { name: 'Save rule' });

beforeEach(() => {
  vi.mocked(toast.error).mockClear();
});

describe('S-11 - Save rule refuses what the server refuses', () => {
  it('a Words rule with no value is refused: "Pick the value it sets."', () => {
    const { onSave } = renderModal();
    createWords('What to find', ['ROUND']);
    fireEvent.click(saveButton());

    expect(onSave).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Pick the value it sets.');
  });

  it('a Code rule with no value is refused the same way', () => {
    const { onSave } = renderModal();
    switchKind('Code');
    createWords('Text', ['-GM']);
    fireEvent.click(saveButton());

    expect(onSave).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Pick the value it sets.');
  });

  it('editing rule 2 names it: "Rule 2: pick the value it sets."', () => {
    const rules: SpecDerivationRule[] = [
      { builder: { kind: 'words', words: ['CHROME'], value: 'chrome' }, _uid: 'r0' },
      { builder: { kind: 'words', words: ['GM'], value: '' }, _uid: 'r1' },
    ];
    const { onSave } = renderModal(rules, 1);
    fireEvent.click(saveButton());

    expect(onSave).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Rule 2: pick the value it sets.');
  });

  it('a word of only dots and dashes is refused inline, Save disabled', () => {
    renderModal();
    createWords('What to find', ['-']);

    expect(screen.getByRole('alert')).toHaveTextContent('Each word needs more than dots and dashes.');
    expect(saveButton()).toBeDisabled();
  });

  it('"..." in two phrases across the lists is refused inline, Save disabled', () => {
    renderModal();
    createWords('What to find', ['ROSE ... GOLD']);
    createWords('Skip it when it comes right after some words', ['NOT ... EVER']);

    expect(screen.getByRole('alert')).toHaveTextContent('Use ... in one phrase only.');
    expect(saveButton()).toBeDisabled();
  });

  it('a whole rule saves, carrying an id', () => {
    const { onSave } = renderModal();
    createWords('What to find', ['GM']);
    fireEvent.click(field('Value it sets').querySelector('button[role="combobox"]')!);
    fireEvent.click(screen.getByRole('option', { name: 'Gunmetal' }));
    fireEvent.click(saveButton());

    expect(toast.error).not.toHaveBeenCalled();
    expect(onSave).toHaveBeenCalledTimes(1);
    expect(onSave.mock.calls[0][0]).toMatchObject({
      builder: { kind: 'words', words: ['GM'], value: 'gunmetal' },
    });
    expect(onSave.mock.calls[0][0]._uid).toMatch(/^new-/);
  });
});

describe('N-8 - no explanatory copy in the modal', () => {
  it('the empty rule preview, See what would change and Try it carry no sentence of explanation', () => {
    renderModal();
    const text = document.body.textContent ?? '';
    expect(text).not.toContain('Fill in the fields above');
    expect(text).not.toContain('See how many products this rule would change');
    expect(text).not.toContain('Pick a product or paste text to see');
  });
});
