/**
 * D15 - Details, Choices and words, and How it is read never render a raw slug.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const SNAKE_CASE = /\w_\w/;

vi.mock('./services/productSpecService', () => ({
  getSpecKeyProducts: vi.fn().mockResolvedValue({
    spec_key: 'finish',
    label: 'Finish or colour',
    total: 0,
    by_value: [],
    by_class: [],
    by_source: [],
    products: [],
  }),
  fetchProductPickerOptions: vi.fn().mockResolvedValue([]),
}));
// A real Try it answer (review round 2, B-7): a slug and a boolean, so the
// per-row read in How it is read is actually exercised.
vi.mock('./hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({
    result: {
      description: 'SRT100 ROSE GOLD BASIN',
      reads: [
        { index: 0, value: 'rose_gold', evidence: '-RG' },
        { index: 1, value: true, evidence: 'ROSE GOLD' },
      ],
      winner_index: 0,
    },
    loading: false,
    error: null,
  }),
}));
// `WordsDataGrid`/`SpecRulesGrid`/`ValuesAndWordsTab` park real deferred
// actions (fix round 1) - nothing here presses Remove.
vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn().mockResolvedValue({ pending: null, last_outcome: null }),
}));

import { HeaderTab } from './components/record/HeaderTab';
import { ValuesAndWordsTab } from './components/record/ValuesAndWordsTab';
import { RulesTab } from './components/record/RulesTab';
import type { SpecRegistryKey } from './types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** Document-wide, so a portalled surface cannot hide a leak from it. */
function assertNoSnakeCase() {
  const match = (document.body.textContent ?? '').match(SNAKE_CASE);
  expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
}

/** A choice with no `value_labels` override, so the tab has to call
 *  `readableValue`/`readable` to avoid printing the raw slug. */
const FINISH_ROW: SpecRegistryKey = {
  // The AC's own shape: the key, the choice and the Only-when key all carry an
  // underscore (`capacity_oz`, `rose_gold`, `from_category`).
  spec_key: 'capacity_oz',
  label: 'Finish or colour',
  data_type: 'enum',
  unit: null,
  allowed_values: ['rose_gold'],
  excluded_values: [],
  user_values: [],
  suppressed_values: [],
  value_weights: {},
  derivation_rules: [],
  effective_rules: [
    { builder: { kind: 'code', code_match: 'ends_with', texts: ['-RG'], value: 'rose_gold' } },
    {
      builder: {
        kind: 'words',
        words: ['ROSE GOLD'],
        value: 'rose_gold',
        only_when: { spec: 'from_category', is: true, values: ['rose_gold'] },
      },
    },
  ],
  synonyms: { rose_gold: ['rose gold'] },
  applies_when: {},
  read_from: 'rules',
  rank_weight: null,
  measured_coverage: 3,
  source: 'seed',
  user_synonyms: {},
  suppressed_synonyms: {},
  match_tolerance: 0,
  match_decay: 0,
  is_active: true,
};

describe('D15 guard - the record page tabs', () => {
  it('Details renders no underscore anywhere', () => {
    render(
      withClient(<HeaderTab row={FINISH_ROW} mode="view" draft={null} setDraft={() => {}} />),
    );
    assertNoSnakeCase();
  });

  it('Choices and words reads rose_gold as "Rose gold"', async () => {
    render(
      withClient(
        <ValuesAndWordsTab
          row={FINISH_ROW}
          mode="view"
          draft={null}
          setDraft={() => {}}
          onEnterEdit={() => {}}
        />,
      ),
    );
    await screen.findByText('Rose gold');
    assertNoSnakeCase();
  });

  it('How it is read renders the code rule\'s value as "Rose gold"', async () => {
    render(
      withClient(
        <RulesTab row={FINISH_ROW} registry={[FINISH_ROW]} mode="view" draft={null} setDraft={() => {}} />,
      ),
    );
    await screen.findAllByText('Rose gold');
    expect(screen.getByText('Reads: Rose gold')).toBeInTheDocument();
    expect(screen.getByText('Reads: Yes')).toBeInTheDocument();
    assertNoSnakeCase();
  });
});
