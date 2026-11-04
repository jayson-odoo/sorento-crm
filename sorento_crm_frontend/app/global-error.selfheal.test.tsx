/**
 * CLIENT-ERROR-REPORT: the root boundary reloads ONCE on a stale chunk and reports
 * every error it actually shows.
 */
import React from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';

const reportClientError = vi.fn();
vi.mock('@/lib/client-error-report', () => ({
  reportClientError: (...args: unknown[]) => reportClientError(...args),
}));

import { claimStaleChunkReload } from '@/lib/chunk-load-error';

/** A fresh module per simulated page load, as a real reload gives. */
async function loadBoundary() {
  vi.resetModules();
  return (await import('./global-error')).default;
}

function chunkError() {
  const e = new Error('Loading chunk 123 failed.');
  e.name = 'ChunkLoadError';
  return e;
}

let reload: ReturnType<typeof vi.fn>;

beforeEach(() => {
  window.sessionStorage.clear();
  reload = vi.fn();
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { ...window.location, reload, pathname: '/inventory/stock-inquiries' },
  });
  vi.spyOn(console, 'error').mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  reportClientError.mockReset();
  vi.restoreAllMocks();
});

describe('global-error stale chunk self-heal', () => {
  it('a chunk error reloads once and shows no screen', async () => {
    const GlobalError = await loadBoundary();
    render(<GlobalError error={chunkError()} reset={vi.fn()} />);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Something went wrong')).toBeNull();
    expect(reportClientError).not.toHaveBeenCalled();
  });

  it('a chunk error after that reload shows the screen, reports, and does not reload again', async () => {
    const FirstLoad = await loadBoundary();
    render(<FirstLoad error={chunkError()} reset={vi.fn()} />);
    cleanup();
    reload.mockClear();
    // The page reloaded on the same build and failed again.
    const GlobalError = await loadBoundary();
    const second = chunkError();
    render(<GlobalError error={second} reset={vi.fn()} />);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy();
    expect(reportClientError).toHaveBeenCalledTimes(1);
    expect(reportClientError).toHaveBeenCalledWith(second, 'global');
  });

  it('without sessionStorage it never auto-reloads (cannot guard a loop)', async () => {
    const GlobalError = await loadBoundary();
    vi.spyOn(window.sessionStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    render(<GlobalError error={chunkError()} reset={vi.fn()} />);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('Something went wrong')).toBeTruthy();
  });

  it('a real error shows the screen, reports once, and never reloads', async () => {
    const GlobalError = await loadBoundary();
    const err = new TypeError("undefined is not an object (evaluating 'x.y')");
    const { rerender } = render(<GlobalError error={err} reset={vi.fn()} />);
    rerender(<GlobalError error={err} reset={vi.fn()} />);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(reportClientError).toHaveBeenCalledTimes(1);
    expect(reportClientError).toHaveBeenCalledWith(err, 'global');
  });

  it('under StrictMode (dev double effect) a chunk error still only reloads, no screen, no report', async () => {
    const GlobalError = await loadBoundary();
    render(
      <React.StrictMode>
        <GlobalError error={chunkError()} reset={vi.fn()} />
      </React.StrictMode>,
    );
    expect(reload).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Something went wrong')).toBeNull();
    expect(reportClientError).not.toHaveBeenCalled();
  });
});

describe('claimStaleChunkReload', () => {
  it('allows one reload per build sha', () => {
    expect(claimStaleChunkReload('build-a')).toBe(true);
    expect(claimStaleChunkReload('build-a')).toBe(false);
    // A newer build (after the reload fetched it) gets its own one reload.
    expect(claimStaleChunkReload('build-b')).toBe(true);
  });
});
