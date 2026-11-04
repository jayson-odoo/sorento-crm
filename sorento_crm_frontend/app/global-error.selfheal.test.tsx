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

import GlobalError from './global-error';

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
  it('a chunk error reloads once and shows no screen', () => {
    render(<GlobalError error={chunkError()} reset={vi.fn()} />);
    expect(reload).toHaveBeenCalledTimes(1);
    expect(screen.queryByText('Something went wrong')).toBeNull();
    expect(reportClientError).not.toHaveBeenCalled();
  });

  it('a chunk error after that reload shows the screen, reports, and does not reload again', () => {
    render(<GlobalError error={chunkError()} reset={vi.fn()} />);
    cleanup();
    reload.mockClear();
    // The page reloaded on the same build and failed again.
    const second = chunkError();
    render(<GlobalError error={second} reset={vi.fn()} />);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Reload' })).toBeTruthy();
    expect(reportClientError).toHaveBeenCalledTimes(1);
    expect(reportClientError).toHaveBeenCalledWith(second, 'global');
  });

  it('without sessionStorage it never auto-reloads (cannot guard a loop)', () => {
    vi.spyOn(window.sessionStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('denied');
    });
    render(<GlobalError error={chunkError()} reset={vi.fn()} />);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('Something went wrong')).toBeTruthy();
  });

  it('a real error shows the screen, reports once, and never reloads', () => {
    const err = new TypeError("undefined is not an object (evaluating 'x.y')");
    const { rerender } = render(<GlobalError error={err} reset={vi.fn()} />);
    rerender(<GlobalError error={err} reset={vi.fn()} />);
    expect(reload).not.toHaveBeenCalled();
    expect(screen.getByText('Something went wrong')).toBeTruthy();
    expect(reportClientError).toHaveBeenCalledTimes(1);
    expect(reportClientError).toHaveBeenCalledWith(err, 'global');
  });
});
