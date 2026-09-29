/**
 * AC-S1.18 - every single-pick selector in the rule modal is `SearchableSelect`
 * and every several-pick selector is `SearchableMultiSelect`, both from
 * `components/common/`. No segmented control, radio strip or hand-made chip box
 * renders, for any of the five kinds.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

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
import type { SpecRegistryKey } from '../types/productSpec.types';

function withClient(children: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const SHAPE_ROW: SpecRegistryKey = {
  spec_key: 'shape',
  label: 'Shape',
  data_type: 'enum',
  unit: null,
  allowed_values: ['round', 'square'],
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

const FINISH_ROW: SpecRegistryKey = {
  ...SHAPE_ROW,
  spec_key: 'finish',
  label: 'Finish or colour',
  allowed_values: ['chrome', 'gunmetal'],
};

function renderModal() {
  return render(
    withClient(
      <SpecRuleModal
        open
        onOpenChange={() => {}}
        spec={FINISH_ROW}
        registry={[FINISH_ROW, SHAPE_ROW]}
        rules={[]}
        editingIndex={null}
        onSave={() => {}}
      />,
    ),
  );
}

function assertNoRawControls(container: HTMLElement) {
  expect(container.querySelectorAll('input[type="radio"]')).toHaveLength(0);
  expect(container.querySelectorAll('[role="radiogroup"]')).toHaveLength(0);
  // A segmented control in this codebase renders as a button strip, never a
  // native <select> either - the two other things a rule field must not be.
  expect(container.querySelectorAll('select')).toHaveLength(0);
}

function switchKind(label: string) {
  const kindField = screen.getByText('Kind').closest('div')!;
  fireEvent.click(kindField.querySelector('button[role="combobox"]')!);
  fireEvent.click(screen.getByRole('option', { name: label }));
}

describe('AC-S1.18 - the rule modal, every kind', () => {
  // The modal is a Radix `Dialog`, which portals its content to `document.body`
  // rather than into the render's own container - every query below reads the
  // whole document for that reason.

  it('Words: Where to look, Kind, What to find and Skip after are all Searchable(Multi)Select', () => {
    renderModal();

    const selects = document.body.querySelectorAll('[data-slot="searchable-select-trigger"]');
    const multiSelects = document.body.querySelectorAll('[data-slot="searchable-multi-select-trigger"]');
    // Where to look, Kind, Value it sets, Only when spec, Only when is/is-not = 5 single-picks.
    expect(selects.length).toBeGreaterThanOrEqual(5);
    // What to find, Skip after, Only when values = 3 multi-picks.
    expect(multiSelects.length).toBeGreaterThanOrEqual(3);
    assertNoRawControls(document.body);
  });

  it('Number: The number, After/Before, Written in are all Searchable(Multi)Select', () => {
    renderModal();
    switchKind('Number');

    expect(screen.getByText('The number')).toBeInTheDocument();
    expect(screen.getByText('Written in')).toBeInTheDocument();
    expect(document.body.querySelectorAll('[data-slot="searchable-select-trigger"]').length).toBeGreaterThan(0);
    expect(
      document.body.querySelectorAll('[data-slot="searchable-multi-select-trigger"]').length,
    ).toBeGreaterThan(0);
    assertNoRawControls(document.body);
  });

  it('Size: Take is a SearchableSelect, no radio strip for 1st/2nd/3rd/4th/L/W/H', () => {
    renderModal();
    switchKind('Size');

    expect(screen.getByText('Take')).toBeInTheDocument();
    expect(document.body.querySelectorAll('[data-slot="searchable-select-trigger"]').length).toBeGreaterThan(0);
    assertNoRawControls(document.body);
  });

  it('Code: The code and Text are Searchable(Multi)Select', () => {
    renderModal();
    switchKind('Code');

    expect(screen.getByText('The code')).toBeInTheDocument();
    expect(screen.getByText('Text')).toBeInTheDocument();
    expect(document.body.querySelectorAll('[data-slot="searchable-select-trigger"]').length).toBeGreaterThan(0);
    expect(
      document.body.querySelectorAll('[data-slot="searchable-multi-select-trigger"]').length,
    ).toBeGreaterThan(0);
    assertNoRawControls(document.body);
  });

  it('Product: Use is a SearchableSelect, and Value it sets has no FIELD (only the grid-preview column survives)', () => {
    renderModal();
    switchKind('Product');

    expect(screen.getByText('Use')).toBeInTheDocument();
    // "Value it sets" still names a column in "This rule in the grid" below the
    // form - what disappears for Product is the FORM FIELD, a <label>; none of
    // the remaining occurrences may be one.
    const occurrences = screen.getAllByText('Value it sets');
    expect(occurrences.every((el) => el.tagName !== 'LABEL')).toBe(true);
    assertNoRawControls(document.body);
  });
});

/** Opens the multi-select under `label` (Radix Popover, portalled to
 *  `document.body`) - once per field. Reclicking the trigger while it is
 *  already open would toggle it CLOSED, so a run of `createWord` calls opens
 *  it exactly once and adds every word into that same open popover. */
function openMultiSelect(label: string) {
  const field = screen.getByText(label).closest('div')!;
  fireEvent.click(field.querySelector('button[role="combobox"]')!);
}

function createWord(word: string) {
  const input = screen.getByPlaceholderText('Search...');
  fireEvent.change(input, { target: { value: word } });
  fireEvent.click(document.body.querySelector('[data-slot="searchable-multi-select-create"]')!);
}

function saveButton() {
  return screen.getByRole('button', { name: 'Save rule' });
}

describe('Security review fix round (#1286, B1) - the same three limits the server refuses', () => {
  it('a phrase with more than one ... is refused inline under the words multi-select, Save disabled', () => {
    renderModal();
    openMultiSelect('What to find');
    createWord('A ... B ... C');

    expect(screen.getByRole('alert')).toHaveTextContent('Use at most one ... in a phrase.');
    expect(saveButton()).toBeDisabled();
  });

  it('a word over 60 characters is refused inline, Save disabled', () => {
    renderModal();
    openMultiSelect('What to find');
    createWord('X'.repeat(61));

    expect(screen.getByRole('alert')).toHaveTextContent('Keep each word to 60 characters or fewer.');
    expect(saveButton()).toBeDisabled();
  });

  it('more than 20 words in one list is refused inline, Save disabled', () => {
    renderModal();
    openMultiSelect('What to find');
    for (let i = 0; i < 21; i += 1) createWord(`WORD${i}`);

    expect(screen.getByRole('alert')).toHaveTextContent('Use at most 20 words in a list.');
    expect(saveButton()).toBeDisabled();
  });

  it('within every limit, no alert renders and Save stays enabled', () => {
    renderModal();
    openMultiSelect('What to find');
    createWord('ROUND');

    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(saveButton()).not.toBeDisabled();
  });
});
