/**
 * Suppression is reversible, so a save must not quietly delete what it restores to.
 *
 * The published vocabulary drops a suppressed value's words - `merged_synonyms` no
 * longer advertises words for a value the same response reports as not allowed. This
 * editor is the one screen that edits the RAW columns, and the API replaces
 * `user_synonyms` wholesale, so a form built only from the merged map sends a payload
 * that no longer mentions the staff words for a suppressed value: they are gone on the
 * next save of the key, for a reason no screen states.
 */
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));
vi.mock('../services/productSpecService', () => ({
  updateSpecKey: vi.fn(),
}));

import { updateSpecKey } from '../services/productSpecService';
import SpecKeyEditor from './SpecKeyEditor';
import type { SpecRegistryKey } from '../types/productSpec.types';

const mockUpdate = vi.mocked(updateSpecKey);

/** `finish` after an admin suppressed the shipped value staff had added a word to. */
function finishWithASuppressedValue(): SpecRegistryKey {
  return {
    spec_key: 'finish',
    label: 'Finish',
    data_type: 'enum',
    unit: null,
    // Merged, so the suppressed value is absent from both of these.
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
    // The raw column still holds what staff added, which is what makes it restorable.
    user_synonyms: { brushed_brass: ['old brass'] },
    suppressed_synonyms: {},
    match_tolerance: 0,
    match_decay: 0,
    is_active: true,
  };
}

beforeEach(() => vi.clearAllMocks());

describe('a save that was not about the suppressed value', () => {
  it('keeps the staff words for it, so restoring the value brings them back', async () => {
    mockUpdate.mockResolvedValue(finishWithASuppressedValue());
    render(
      <SpecKeyEditor
        specKey={finishWithASuppressedValue()}
        onSaved={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save' }));

    await waitFor(() => expect(mockUpdate).toHaveBeenCalled());
    const [, payload] = mockUpdate.mock.calls[0];
    expect(payload.user_synonyms?.brushed_brass).toEqual(['old brass']);
    // And the value itself stays suppressed - this save was about neither.
    expect(payload.suppressed_values).toEqual(['brushed_brass']);
  });

  it('shows the suppressed value its own row, so the words are visible to edit', () => {
    render(
      <SpecKeyEditor
        specKey={finishWithASuppressedValue()}
        onSaved={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(
      screen.getByRole('button', { name: 'Clear the words for brushed_brass' }),
    ).toBeInTheDocument();
    expect(screen.getByText('old brass')).toBeInTheDocument();
  });
});
