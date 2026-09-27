/**
 * D15 - Add a rule / Edit never renders a raw slug: the Value it sets picker
 * offers "Rose gold" over a spec whose only choice is `rose_gold`, with no
 * `value_labels` override to fall back on.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const SNAKE_CASE = /\w_\w/;

// Real answers, not nulls (review round 2, B-7): a Try it read and a preview
// sample that carry a slug (`rose_gold`) and a boolean, so a screen that prints
// the raw value is caught rather than never exercised.
vi.mock('./hooks/useSpecTryIt', () => ({
  useSpecTryIt: () => ({
    result: {
      description: 'SRT100 ROSE GOLD BASIN',
      reads: [{ index: 0, value: 'rose_gold', evidence: 'ROSE GOLD' }],
      winner_index: 0,
    },
    loading: false,
    error: null,
  }),
}));
vi.mock('./hooks/useSpecPreview', () => ({
  useSpecPreview: () => ({
    status: 'done',
    result: {
      status: 'done',
      changed: 2,
      added: 0,
      removed: 0,
      unchanged: 5,
      sample: [
        { code: 'SRT100', before: 'rose_gold', after: 'matt_black' },
        { code: 'SRT200', before: null, after: true },
      ],
    },
    error: null,
    run: vi.fn(),
  }),
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
  spec_key: 'finish_colour',
  label: 'Finish or colour',
  data_type: 'enum',
  unit: null,
  allowed_values: ['rose_gold', 'matt_black'],
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

/** Capacity (oz): the AC's own snake_case key, in the registry the modal's
 *  "Only when" picker lists. */
const CAPACITY_ROW: SpecRegistryKey = {
  ...FINISH_ROW,
  spec_key: 'capacity_oz',
  label: 'Capacity (oz)',
  data_type: 'numeric',
  unit: 'oz',
  allowed_values: [],
};

/** A document-wide read: the modal is a Radix Dialog, portalled to
 *  `document.body`, so the render's own container is an empty div. */
function assertNoSnakeCase() {
  const match = (document.body.textContent ?? '').match(SNAKE_CASE);
  expect(match, `rendered a snake_case value: "${match?.[0]}"`).toBeNull();
}

describe('D15 guard - the rule modal', () => {
  it('the Value it sets picker opens on "Rose gold", never rose_gold, and nothing else renders it raw', () => {
    render(
      withClient(
        <SpecRuleModal
          open
          onOpenChange={() => {}}
          spec={FINISH_ROW}
          registry={[FINISH_ROW, CAPACITY_ROW]}
          rules={[]}
          editingIndex={null}
          onSave={() => {}}
        />,
      ),
    );

    // Default kind is Words, so Value it sets is shown; open its own picker to
    // force the option list (not just the placeholder trigger) to render.
    const valueField = screen.getByText('Value it sets', { selector: 'label' }).closest('div')!;
    fireEvent.click(valueField.querySelector('button[role="combobox"]')!);

    expect(screen.getByRole('option', { name: 'Rose gold' })).toBeInTheDocument();
    assertNoSnakeCase();
  });

  it('Try it, See what would change and Only when read slugs and booleans as words', () => {
    render(
      withClient(
        <SpecRuleModal
          open
          onOpenChange={() => {}}
          spec={FINISH_ROW}
          registry={[FINISH_ROW, CAPACITY_ROW]}
          rules={[
            {
              builder: {
                kind: 'words',
                words: ['ROSE GOLD'],
                value: 'rose_gold',
                // A spec the registry no longer carries: the cell must still not
                // print its key (N-9).
                only_when: { spec: 'from_category', is: true, values: ['rose_gold'] },
              },
              _uid: 'r0',
            },
          ]}
          editingIndex={0}
          onSave={() => {}}
        />,
      ),
    );

    fireEvent.change(screen.getByPlaceholderText('Paste a product description to try instead'), {
      target: { value: 'SRT100 ROSE GOLD BASIN' },
    });

    expect(screen.getByText('Reads Rose gold.')).toBeInTheDocument();
    expect(screen.getByText('Matt black')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
    assertNoSnakeCase();
  });
});
