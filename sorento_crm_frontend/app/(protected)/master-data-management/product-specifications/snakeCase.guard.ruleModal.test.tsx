/**
 * D15 - Add a rule / Edit never renders a raw slug: the Value it sets picker
 * offers "Rose gold" over a spec whose only choice is `rose_gold`, with no
 * `value_labels` override to fall back on.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const SNAKE_CASE = /\w_\w/;

vi.mock('./hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({ result: null, loading: false, error: null }),
}));
vi.mock('./hooks/useSpecPreview', () => ({
  useSpecPreview: () => ({ status: 'idle', result: null, error: null, run: vi.fn() }),
}));
vi.mock('./services/productSpecService', () => ({
  fetchProductPickerOptions: vi.fn().mockResolvedValue([]),
}));

import { SpecRuleModal } from './components/SpecRuleModal';
import type { SpecRegistryKey } from './types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

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

describe('D15 guard - the rule modal', () => {
  it('the Value it sets picker opens on "Rose gold", never rose_gold, and nothing else renders it raw', () => {
    const { container } = render(
      withClient(
        <SpecRuleModal
          open
          onOpenChange={() => {}}
          spec={FINISH_ROW}
          registry={[FINISH_ROW]}
          rules={[]}
          editingIndex={null}
          onSave={() => {}}
        />,
      ),
    );

    // Default kind is Words, so Value it sets is shown; open its own picker to
    // force the option list (not just the placeholder trigger) to render.
    const valueField = screen.getByText('Value it sets').closest('div')!;
    fireEvent.click(valueField.querySelector('button[role="combobox"]')!);

    expect(screen.getByText('Rose gold')).toBeInTheDocument();
    const match = (container.textContent ?? '').match(SNAKE_CASE);
    expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
  });
});
