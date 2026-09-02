import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

// Capture the onError callback that QueryProvider passes to QueryCache.
let capturedOnError:
  | ((
      error: Error,
      query: { meta?: Record<string, unknown>; queryKey: readonly unknown[] },
    ) => void)
  | null = null;

vi.mock('@tanstack/react-query', () => {
  const actual = vi.importActual('@tanstack/react-query');
  return {
    ...actual,
    QueryCache: class {
      constructor(opts?: { onError?: typeof capturedOnError }) {
        capturedOnError = opts?.onError ?? null;
      }
    },
    QueryClient: class {
      constructor() {
        // no-op
      }
      invalidateQueries() {}
    },
    QueryClientProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  };
});

const toastCustom = vi.fn();
vi.mock('@/lib/toast', () => ({
  toast: { custom: (...args: unknown[]) => toastCustom(...args) },
}));

vi.mock('@/components/ui/alert', () => ({
  Alert: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertIcon: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
  AlertTitle: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}));

vi.mock('@remixicon/react', () => ({
  RiErrorWarningFill: () => <span>icon</span>,
}));

vi.mock('@/lib/revision-fence', () => ({
  registerRevisionStaleHandler: vi.fn(),
}));

vi.mock('@/services/pendingActionService', () => ({
  createPendingAction: vi.fn(),
  cancelPendingAction: vi.fn(),
  getCurrentPendingAction: vi.fn(),
}));

import { QueryProvider } from './query-provider';
import { pendingEntityStore } from '@/lib/pending-entity-store';

function fireOnError(
  message: string,
  meta?: Record<string, unknown>,
  queryKey: readonly unknown[] = ['something'],
) {
  if (!capturedOnError) throw new Error('onError not captured - render QueryProvider first');
  capturedOnError(new Error(message), { meta, queryKey });
}

describe('QueryProvider toast deduplication', () => {
  beforeEach(() => {
    capturedOnError = null;
    toastCustom.mockClear();
    pendingEntityStore.reset();
    render(
      <QueryProvider>
        <div />
      </QueryProvider>,
    );
  });

  it('collapses three concurrent permission-denied 403s into one toast', () => {
    fireOnError('Permission required: scm.dashboard.view');
    fireOnError('Permission required: scm.reorder.run');
    fireOnError('Permission required: scm.policy.manage');

    // All three should produce calls, but they share the same id so sonner
    // deduplicates them into one visible toast. We verify the id is set.
    expect(toastCustom).toHaveBeenCalledTimes(3);
    for (const call of toastCustom.mock.calls) {
      expect(call[1]).toEqual(
        expect.objectContaining({ id: 'permission-denied' }),
      );
    }
  });

  it('toasts "One of these permissions required:" with the same deduped id', () => {
    fireOnError('One of these permissions required: a.b, c.d');

    expect(toastCustom).toHaveBeenCalledTimes(1);
    expect(toastCustom.mock.calls[0][1]).toEqual(
      expect.objectContaining({ id: 'permission-denied' }),
    );
  });

  it('passes a 500 error through with no id (no dedup)', () => {
    fireOnError('Internal server error');

    expect(toastCustom).toHaveBeenCalledTimes(1);
    // M6-04: the Toaster is mounted once at top-center, so an ungrouped toast
    // carries no options at all (no per-call `position`, no dedup `id`).
    const opts = toastCustom.mock.calls[0][1];
    expect(opts?.id).toBeUndefined();
  });

  it('keeps permission toast and regular toast separate', () => {
    fireOnError('Permission required: scm.dashboard.view');
    fireOnError('Internal server error');

    expect(toastCustom).toHaveBeenCalledTimes(2);
    // First call: permission-denied id
    expect(toastCustom.mock.calls[0][1]).toEqual(
      expect.objectContaining({ id: 'permission-denied' }),
    );
    // Second call: no options at all
    expect(toastCustom.mock.calls[1][1]?.id).toBeUndefined();
  });

  it('suppresses toast when query meta has silent: true', () => {
    fireOnError('Permission required: scm.dashboard.view', { silent: true });

    expect(toastCustom).not.toHaveBeenCalled();
  });

  // S6 feedback C: a record the user watched a delete commit on is gone on
  // purpose. The detail read, its tabs and its counts all 404 at once, and a
  // stack of red toasts for the thing they asked for is not an answer.
  it('says nothing about reads keyed on a record this tab just deleted', () => {
    pendingEntityStore.noteCommittedDelete('p-1');

    fireOnError('Product not found', undefined, ['product', 'p-1']);
    fireOnError('Product not found', undefined, ['product-attachments', 'p-1']);

    expect(toastCustom).not.toHaveBeenCalled();

    // Everything else still reports normally.
    fireOnError('Internal server error', undefined, ['product', 'p-2']);
    expect(toastCustom).toHaveBeenCalledTimes(1);
  });
});
