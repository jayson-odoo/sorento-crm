/**
 * S7-05 - a copy confirms itself on the button, not in the corner of the screen.
 *
 * The hook itself never imports `toast` - the tick IS the confirmation. A
 * refusal is a different matter (the clipboard is refused over plain HTTP, or
 * by browser policy) and stays the caller's job, exactly the pattern every
 * call site uses: `if (!(await copyToClipboard(v))) toast.error(...)`.
 */
import React from 'react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act, waitFor } from '@testing-library/react';
import { renderHook } from '@testing-library/react';

import { useCopyToClipboard } from './use-copy-to-clipboard';

vi.mock('@/lib/toast', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import { toast } from '@/lib/toast';

function mockClipboard(writeText: (value: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
}

describe('useCopyToClipboard (S7-05)', () => {
  beforeEach(() => {
    vi.mocked(toast.error).mockClear();
    vi.mocked(toast.success).mockClear();
  });

  afterEach(() => {
    // @ts-expect-error - test-only cleanup of the property we defined above.
    delete navigator.clipboard;
    // @ts-expect-error - see above.
    delete document.execCommand;
  });

  it('copies through the execCommand fallback when navigator.clipboard is undefined (http)', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true });
    const { result } = renderHook(() => useCopyToClipboard());

    let ok: boolean = false;
    await act(async () => {
      ok = await result.current.copyToClipboard('hello');
    });

    expect(ok).toBe(true);
    expect(result.current.isCopied).toBe(true);
    expect(execCommand).toHaveBeenCalledWith('copy');
  });

  it('copies through the execCommand fallback when writeText rejects', async () => {
    mockClipboard(() => Promise.reject(new Error('refused')));
    const execCommand = vi.fn().mockReturnValue(true);
    Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true });
    const { result } = renderHook(() => useCopyToClipboard());

    let ok: boolean = false;
    await act(async () => {
      ok = await result.current.copyToClipboard('hello');
    });

    expect(ok).toBe(true);
    expect(execCommand).toHaveBeenCalledWith('copy');
  });

  it('shows the tick and fires no toast on a successful copy', async () => {
    mockClipboard(() => Promise.resolve());
    const { result } = renderHook(() => useCopyToClipboard());

    let ok: boolean = false;
    await act(async () => {
      ok = await result.current.copyToClipboard('hello');
    });

    expect(ok).toBe(true);
    expect(result.current.isCopied).toBe(true);
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('resolves false and stays uncopied when the clipboard write and the fallback are both refused', async () => {
    mockClipboard(() => Promise.reject(new Error('refused')));
    Object.defineProperty(document, 'execCommand', { value: vi.fn().mockReturnValue(false), configurable: true });
    const { result } = renderHook(() => useCopyToClipboard());

    let ok: boolean = true;
    await act(async () => {
      ok = await result.current.copyToClipboard('hello');
    });

    expect(ok).toBe(false);
    expect(result.current.isCopied).toBe(false);
    // The hook itself still raises nothing - the refusal is the caller's to report.
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('the real call-site contract still toasts on a refused copy', async () => {
    mockClipboard(() => Promise.reject(new Error('refused')));

    function Consumer() {
      const { isCopied, copyToClipboard } = useCopyToClipboard();
      return (
        <button
          onClick={async () => {
            if (!(await copyToClipboard('hello'))) toast.error('Press Ctrl/Cmd+C to copy');
          }}
        >
          {isCopied ? 'Copied' : 'Copy'}
        </button>
      );
    }

    render(<Consumer />);
    const button = screen.getByRole('button', { name: 'Copy' });
    await act(async () => {
      button.click();
    });

    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Press Ctrl/Cmd+C to copy'));
    expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
  });

  it('the real call-site contract does not toast on a successful copy', async () => {
    mockClipboard(() => Promise.resolve());

    function Consumer() {
      const { isCopied, copyToClipboard } = useCopyToClipboard();
      return (
        <button
          onClick={async () => {
            if (!(await copyToClipboard('hello'))) toast.error('Press Ctrl/Cmd+C to copy');
          }}
        >
          {isCopied ? 'Copied' : 'Copy'}
        </button>
      );
    }

    render(<Consumer />);
    const button = screen.getByRole('button', { name: 'Copy' });
    await act(async () => {
      button.click();
    });

    await waitFor(() => expect(screen.getByRole('button', { name: 'Copied' })).toBeInTheDocument());
    expect(toast.error).not.toHaveBeenCalled();
    expect(toast.success).not.toHaveBeenCalled();
  });
});
