/**
 * Tests for the thin `useFormNeighbours` wrapper around the generic
 * `useRecordNeighbours` hook.
 *
 * Verifies the wrapper:
 *  - calls the generic hook with the canonical FORM_NEIGHBOURS_PATH,
 *  - forwards the current form id verbatim,
 *  - serializes the list query (search/sort) AND the resource-specific
 *    filters (language/status/form_type) via `buildDataGridParams`, dropping
 *    empty/undefined values, so list and neighbours can't drift.
 *
 * Mirrors hooks/useRecordNeighbours.test.ts conventions (the shared hook test).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

import { useFormNeighbours } from './useForms';
import { FORM_NEIGHBOURS_PATH } from '../services/formService';

const useRecordNeighbours = vi.fn((..._args: unknown[]) => ({
  prevId: null,
  nextId: null,
  index: null,
  total: 0,
  isLoading: false,
}));

vi.mock('@/hooks/useRecordNeighbours', () => ({
  useRecordNeighbours: (...args: unknown[]) => useRecordNeighbours(...args),
}));

beforeEach(() => {
  useRecordNeighbours.mockClear();
});

function callArgs() {
  const [path, id, params] = useRecordNeighbours.mock.calls[0] as [
    string,
    string | null,
    URLSearchParams,
  ];
  return { path, id, params };
}

describe('useFormNeighbours', () => {
  it('targets the canonical forms neighbours path and forwards the id', () => {
    renderHook(() =>
      useFormNeighbours('form-1', {
        pageIndex: 0,
        pageSize: 50,
        sorting: [{ id: 'name', desc: false }],
        searchQuery: '',
      }),
    );
    const { path, id } = callArgs();
    expect(path).toBe(FORM_NEIGHBOURS_PATH);
    expect(id).toBe('form-1');
  });

  it('serializes search + sort into the neighbours params', () => {
    renderHook(() =>
      useFormNeighbours('form-2', {
        pageIndex: 2,
        pageSize: 50,
        sorting: [{ id: 'name', desc: true }],
        searchQuery: 'flower',
      }),
    );
    const { params } = callArgs();
    expect(params.get('query')).toBe('flower');
    expect(params.get('sort')).toBe('name');
    expect(params.get('dir')).toBe('desc');
  });

  it('forwards resource-specific filters (language/status/form_type)', () => {
    renderHook(() =>
      useFormNeighbours('form-3', {
        pageIndex: 0,
        pageSize: 50,
        sorting: [{ id: 'updated_at', desc: true }],
        searchQuery: '',
        language: 'en',
        status: 'active',
        form_type: 'marketing',
      }),
    );
    const { params } = callArgs();
    expect(params.get('language')).toBe('en');
    expect(params.get('status')).toBe('active');
    expect(params.get('form_type')).toBe('marketing');
  });

  it('drops empty/undefined filters from the params', () => {
    renderHook(() =>
      useFormNeighbours('form-4', {
        pageIndex: 0,
        pageSize: 50,
        sorting: [{ id: 'name', desc: false }],
        searchQuery: '',
        language: undefined,
        status: '',
        form_type: 'marketing',
      }),
    );
    const { params } = callArgs();
    expect(params.has('language')).toBe(false);
    expect(params.has('status')).toBe(false);
    expect(params.has('query')).toBe(false);
    expect(params.get('form_type')).toBe('marketing');
  });
});
