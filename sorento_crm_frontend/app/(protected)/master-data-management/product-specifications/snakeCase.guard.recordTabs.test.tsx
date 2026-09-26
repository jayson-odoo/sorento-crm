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
vi.mock('./hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({ result: null, loading: false, error: null }),
}));

import { HeaderTab } from './components/record/HeaderTab';
import { ValuesAndWordsTab } from './components/record/ValuesAndWordsTab';
import { RulesTab } from './components/record/RulesTab';
import type { SpecRegistryKey } from './types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function assertNoSnakeCase(container: HTMLElement) {
  const match = (container.textContent ?? '').match(SNAKE_CASE);
  expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
}

/** A choice with no `value_labels` override, so the tab has to call
 *  `readableValue`/`readable` to avoid printing the raw slug. */
const FINISH_ROW: SpecRegistryKey = {
  spec_key: 'finish',
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
    const { container } = render(
      <HeaderTab row={FINISH_ROW} mode="view" draft={null} setDraft={() => {}} />,
    );
    assertNoSnakeCase(container);
  });

  it('Choices and words reads rose_gold as "Rose gold"', async () => {
    const { container } = render(
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
    assertNoSnakeCase(container);
  });

  it('How it is read renders the code rule\'s value as "Rose gold"', async () => {
    const { container } = render(
      withClient(
        <RulesTab row={FINISH_ROW} registry={[FINISH_ROW]} mode="view" draft={null} setDraft={() => {}} />,
      ),
    );
    await screen.findByText('Rose gold');
    assertNoSnakeCase(container);
  });
});
