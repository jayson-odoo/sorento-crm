import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render } from '@testing-library/react';

// Capture the onError callback that QueryProvider passes to QueryCache.
let capturedOnError: ((error: Error, query: { meta?: Record<string, unknown> }) => void) | null =
  null;

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
vi.mock('sonner', () => ({
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

import { QueryProvider } from './query-provider';

function fireOnError(message: string, meta?: Record<string, unknown>) {
  if (!capturedOnError) throw new Error('onError not captured - render QueryProvider first');
  capturedOnError(new Error(message), { meta });
}

describe('QueryProvider toast deduplication', () => {
  beforeEach(() => {
    capturedOnError = null;
    toastCustom.mockClear();
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
    const opts = toastCustom.mock.calls[0][1];
    expect(opts.id).toBeUndefined();
  });

  it('keeps permission toast and regular toast separate', () => {
    fireOnError('Permission required: scm.dashboard.view');
    fireOnError('Internal server error');

    expect(toastCustom).toHaveBeenCalledTimes(2);
    // First call: permission-denied id
    expect(toastCustom.mock.calls[0][1]).toEqual(
      expect.objectContaining({ id: 'permission-denied' }),
    );
    // Second call: no id
    expect(toastCustom.mock.calls[1][1].id).toBeUndefined();
  });

  it('suppresses toast when query meta has silent: true', () => {
    fireOnError('Permission required: scm.dashboard.view', { silent: true });

    expect(toastCustom).not.toHaveBeenCalled();
  });
});
