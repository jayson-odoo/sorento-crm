/**
 * AC-B.3, AC-E.1/E.2, AC-G.8 - the Values and words tab.
 *
 * Ported from `SpecKeyEditor.suppressedWords.test.tsx` (rendering half; the save-diff
 * half now lives in `useSpecKeyRecord.test.ts`, where the diff actually runs).
 * Suppression is reversible, so a suppressed row must keep its staff words visible
 * and editable rather than hiding them.
 */
import { useState } from 'react';
import { describe, expect, it } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ValuesAndWordsTab } from './ValuesAndWordsTab';
import { projectSpecKeyDraft, type SpecKeyDraft } from '../../hooks/useSpecKeyRecord';
import type { SpecRegistryKey } from '../../types/productSpec.types';

/** `finish` after an admin suppressed the shipped value staff had added a word to. */
function finishWithASuppressedValue(): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish',
    data_type: 'enum',
    unit: null,
    allowed_values: ['chrome'],
    synonyms: { chrome: ['chrome'] },
    excluded_values: [],
    user_values: [],
    suppressed_values: ['brushed_brass'],
    value_weights: {},
    derivation_rules: [],
    effective_rules: [],
    rules_are_default: true,
    applies_when: {},
    read_from: 'rules',
    rank_weight: 1,
    measured_coverage: null,
    source: 'seed',
    user_synonyms: { brushed_brass: ['old brass'] },
    suppressed_synonyms: {},
    match_tolerance: 0,
    match_decay: 0,
    is_active: true,
  };
}

function EditHarness({
  row,
  onDraftChange,
}: {
  row: SpecRegistryKey;
  onDraftChange?: (draft: SpecKeyDraft) => void;
}) {
  const [draft, setDraftState] = useState<SpecKeyDraft>(() => projectSpecKeyDraft(row));
  return (
    <ValuesAndWordsTab
      row={row}
      mode="edit"
      draft={draft}
      setDraft={(updater) =>
        setDraftState((current) => {
          const next = updater(current);
          onDraftChange?.(next);
          return next;
        })
      }
      onEnterEdit={() => {}}
    />
  );
}

describe('ValuesAndWordsTab - suppressed values (edit mode)', () => {
  it('shows the suppressed value its own row, so the words are visible to edit', () => {
    render(<EditHarness row={finishWithASuppressedValue()} />);

    expect(screen.getByText('old brass')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Put Brushed brass back' }),
    ).toBeInTheDocument();
  });

  it('strikes that row through, the way a restored row is not struck through', () => {
    render(<EditHarness row={finishWithASuppressedValue()} />);

    expect(screen.getByText('Brushed brass')).toHaveClass('line-through');
    expect(screen.getByText('Chrome')).not.toHaveClass('line-through');
  });
});

describe('ValuesAndWordsTab - display label (E.1, E.2)', () => {
  it('the label input carries the automatic wording as its placeholder', () => {
    render(<EditHarness row={finishWithASuppressedValue()} />);

    expect(
      screen.getByPlaceholderText('Chrome') as HTMLInputElement,
    ).toBeInTheDocument();
  });

  it('typing a label feeds the draft', () => {
    let latest: SpecKeyDraft | undefined;
    render(
      <EditHarness
        row={finishWithASuppressedValue()}
        onDraftChange={(draft) => (latest = draft)}
      />,
    );

    fireEvent.change(screen.getByLabelText('Display label for Chrome'), {
      target: { value: 'Chrome finish' },
    });

    expect(latest?.valueLabels.chrome).toBe('Chrome finish');
  });

  it('view mode shows a stored label instead of the automatic wording', () => {
    const row = { ...finishWithASuppressedValue(), value_labels: { chrome: 'Chrome finish' } };
    render(<ValuesAndWordsTab row={row} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />);

    expect(screen.getByText('Chrome finish')).toBeInTheDocument();
  });
});

describe('ValuesAndWordsTab - view and edit share field labels (G.8)', () => {
  // "Display label" is the one named exception (item 3): the row heading already
  // IS the label (`readableValue(value, undefined, valueLabels)`), so a second,
  // read-only "Display label" span in view mode would just repeat it - it renders
  // only in edit mode, where it is an input. Every other field label matches.
  it('renders the same shared-field labels in both modes, Display label edit-only', () => {
    const row = finishWithASuppressedValue();
    const { unmount } = render(
      <ValuesAndWordsTab row={row} mode="view" draft={null} setDraft={() => {}} onEnterEdit={() => {}} />,
    );
    expect(screen.queryByText('Display label')).not.toBeInTheDocument();
    const viewLabels = screen.getAllByText(/Words customers say/).map((el) => el.textContent);
    unmount();

    render(<EditHarness row={row} />);
    expect(screen.getAllByText('Display label')).toHaveLength(2);
    const editLabels = screen.getAllByText(/Words customers say/).map((el) => el.textContent);

    expect(editLabels).toEqual(viewLabels);
  });
});

describe('ValuesAndWordsTab - empty state', () => {
  it('offers Add value when the key has none', () => {
    const row: SpecRegistryKey = {
      ...finishWithASuppressedValue(),
      spec_key: 'fresh_key',
      allowed_values: [],
      suppressed_values: [],
      synonyms: {},
      user_synonyms: {},
      suppressed_synonyms: {},
    };
    render(<EditHarness row={row} />);

    expect(screen.getByText('No values yet')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add value' })).toBeInTheDocument();
  });
});
