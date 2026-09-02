/**
 * S6 feedback C - the click on a record that is already gone.
 *
 * A deferred delete leaves its row on screen for the window, and the grid may
 * serve it from cache for a moment longer. Clicking it used to land on a detail
 * page whose reads all 404: a red toast, then "not found" on an empty page, for
 * something the user themselves asked for. Only an id this tab watched a delete
 * commit on gets the quiet answer - a wrong URL is a genuine surprise and has to
 * keep saying so.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

const toastPlain = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: Object.assign(
    (...args: unknown[]) => toastPlain(...args),
    { success: vi.fn(), error: vi.fn() },
  ),
}));

const replace = vi.fn();
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, push: vi.fn() }),
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(),
}));

import { useDeletedRecordGuard } from './useDeletedRecordGuard';
import { pendingEntityStore } from '@/lib/pending-entity-store';

beforeEach(() => {
  vi.clearAllMocks();
  pendingEntityStore.reset();
});

function render(entityId: string, notFound: boolean) {
  return renderHook(() =>
    useDeletedRecordGuard({
      entityId,
      notFound,
      listPath: '/master-data-management/products',
    }),
  );
}

describe('useDeletedRecordGuard (S6 feedback C)', () => {
  it('returns a deleted record to its list, once and quietly', () => {
    pendingEntityStore.noteCommittedDelete('p-1');

    const { result, rerender } = render('p-1', true);

    expect(result.current).toBe(true);
    expect(toastPlain).toHaveBeenCalledWith('Already deleted', expect.anything());
    expect(replace).toHaveBeenCalledWith('/master-data-management/products');

    // The page keeps rendering while Next navigates; it must not stack up.
    rerender();
    expect(toastPlain).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledTimes(1);
  });

  it('a URL that was simply wrong keeps the not-found page', () => {
    const { result } = render('p-404', true);

    expect(result.current).toBe(false);
    expect(replace).not.toHaveBeenCalled();
    expect(toastPlain).not.toHaveBeenCalled();
  });

  it('a record that loaded is left alone, deleted sibling or not', () => {
    pendingEntityStore.noteCommittedDelete('p-1');

    const { result } = render('p-1', false);

    expect(result.current).toBe(false);
    expect(replace).not.toHaveBeenCalled();
  });
});
