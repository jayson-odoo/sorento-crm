/**
 * B.2 - the record page's one PATCH.
 *
 * A save that was not about the suppressed value must not quietly delete what it
 * restores to (ported from `SpecKeyEditor.suppressedWords.test.tsx`, which exercised
 * the same `wordPayload`/`valuePayload` diff this hook now runs at `save()`).
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

const updateSpecKey = vi.fn();
vi.mock('../services/productSpecService', () => ({
  updateSpecKey: (...a: unknown[]) => updateSpecKey(...a),
  createSpecKey: vi.fn(),
  rereadCatalogue: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

import { useSpecKeyRecord } from './useSpecKeyRecord';
import type { SpecRegistryKey } from '../types/productSpec.types';

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

let client: QueryClient;
function wrapper({ children }: { children: React.ReactNode }) {
  return React.createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  updateSpecKey.mockReset();
  client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

describe('useSpecKeyRecord', () => {
  it('edit() seeds the draft from the row, cancel() drops it', () => {
    const row = finishWithASuppressedValue();
    const { result } = renderHook(() => useSpecKeyRecord(row), { wrapper });

    expect(result.current.mode).toBe('view');
    expect(result.current.draft).toBeNull();

    act(() => result.current.edit());
    expect(result.current.mode).toBe('edit');
    expect(result.current.draft?.label).toBe('Finish');
    expect(result.current.draft?.liveValues).toEqual(['chrome']);
    expect(result.current.draft?.droppedValues).toEqual(['brushed_brass']);

    act(() => result.current.cancel());
    expect(result.current.mode).toBe('view');
    expect(result.current.draft).toBeNull();
  });

  it('a save that was not about the suppressed value keeps its staff words and its suppression', async () => {
    const row = finishWithASuppressedValue();
    updateSpecKey.mockResolvedValue({ ...row, label: 'Finish' });
    const { result } = renderHook(() => useSpecKeyRecord(row), { wrapper });

    act(() => result.current.edit());
    await act(async () => {
      const ok = await result.current.save();
      expect(ok).toBe(true);
    });

    await waitFor(() => expect(updateSpecKey).toHaveBeenCalled());
    const [, payload] = updateSpecKey.mock.calls[0];
    expect(payload.user_synonyms?.brushed_brass).toEqual(['old brass']);
    // And the value itself stays suppressed - this save was about neither.
    expect(payload.suppressed_values).toEqual(['brushed_brass']);
  });

  it('drops back to view mode once the save resolves', async () => {
    const row = finishWithASuppressedValue();
    updateSpecKey.mockResolvedValue(row);
    const { result } = renderHook(() => useSpecKeyRecord(row), { wrapper });

    act(() => result.current.edit());
    await act(async () => {
      await result.current.save();
    });

    expect(result.current.mode).toBe('view');
    expect(result.current.draft).toBeNull();
  });

  it('a failed save leaves the session open, with nothing typed lost', async () => {
    const row = finishWithASuppressedValue();
    updateSpecKey.mockRejectedValue(new Error('Failed to save the spec key'));
    const { result } = renderHook(() => useSpecKeyRecord(row), { wrapper });

    act(() => result.current.edit());
    act(() => {
      result.current.setDraft((draft) => ({ ...draft, label: 'Finish colour' }));
    });
    await act(async () => {
      const ok = await result.current.save();
      expect(ok).toBe(false);
    });

    expect(result.current.mode).toBe('edit');
    expect(result.current.draft?.label).toBe('Finish colour');
  });
});
