/** CONSOLE-PICKER-COPY: the shared copy helper, Clipboard API first, then the hidden
 *  textarea + execCommand fallback for a non-secure (plain http) context. */
import { describe, it, expect, vi, afterEach } from 'vitest';

import { copyTextToClipboard, copyViaExecCommand } from './clipboard';

function stubExecCommand(result: boolean) {
  const execCommand = vi.fn().mockReturnValue(result);
  Object.defineProperty(document, 'execCommand', { value: execCommand, configurable: true });
  return execCommand;
}

afterEach(() => {
  // @ts-expect-error - test-only cleanup of the properties defined in each test.
  delete navigator.clipboard;
  // @ts-expect-error - see above.
  delete document.execCommand;
});

describe('copyTextToClipboard', () => {
  it('uses navigator.clipboard when it accepts the write, without the fallback', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const execCommand = stubExecCommand(true);
    await expect(copyTextToClipboard('hi')).resolves.toBe(true);
    expect(writeText).toHaveBeenCalledWith('hi');
    expect(execCommand).not.toHaveBeenCalled();
  });

  it('falls back to execCommand when navigator.clipboard is undefined', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    const execCommand = stubExecCommand(true);
    await expect(copyTextToClipboard('hi')).resolves.toBe(true);
    expect(execCommand).toHaveBeenCalledWith('copy');
  });

  it('falls back to execCommand when writeText rejects', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('NotAllowedError'));
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
    const execCommand = stubExecCommand(true);
    await expect(copyTextToClipboard('hi')).resolves.toBe(true);
    expect(execCommand).toHaveBeenCalledWith('copy');
  });

  it('resolves false when neither path works', async () => {
    Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true });
    stubExecCommand(false);
    await expect(copyTextToClipboard('hi')).resolves.toBe(false);
  });
});

describe('copyViaExecCommand', () => {
  function recordSelectionOnCopy(): { selected: string | null } {
    const seen = { selected: null as string | null };
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => {
        const el = document.activeElement;
        seen.selected = el instanceof HTMLTextAreaElement ? el.value.slice(el.selectionStart, el.selectionEnd) : null;
        return true;
      }),
      configurable: true,
    });
    return seen;
  }

  it('selects the whole text and leaves no textarea behind', () => {
    const seen = recordSelectionOnCopy();
    expect(copyViaExecCommand('hello world')).toBe(true);
    expect(seen.selected).toBe('hello world');
    expect(document.querySelector('textarea')).toBeNull();
  });

  it('sets the selection range explicitly, since iOS Safari ignores select() alone', () => {
    const select = vi.spyOn(HTMLTextAreaElement.prototype, 'select').mockImplementation(() => {});
    const seen = recordSelectionOnCopy();
    copyViaExecCommand('hello world');
    expect(seen.selected).toBe('hello world');
    select.mockRestore();
  });

  it('keeps focus inside an open dialog or menu whose focus trap would pull it back', () => {
    const dialog = document.createElement('div');
    dialog.setAttribute('role', 'dialog');
    const button = document.createElement('button');
    dialog.appendChild(button);
    document.body.appendChild(dialog);
    button.focus();
    // The Radix FocusScope behaviour: focus landing outside the trap goes back inside it.
    const trap = (event: FocusEvent) => {
      if (!dialog.contains(event.target as Node)) button.focus();
    };
    document.addEventListener('focusin', trap);
    try {
      const seen = recordSelectionOnCopy();
      expect(copyViaExecCommand('inside the trap')).toBe(true);
      expect(seen.selected).toBe('inside the trap');
      expect(dialog.querySelector('textarea')).toBeNull();
    } finally {
      document.removeEventListener('focusin', trap);
      dialog.remove();
    }
  });

  it('returns false when execCommand throws', () => {
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => {
        throw new Error('nope');
      }),
      configurable: true,
    });
    expect(copyViaExecCommand('x')).toBe(false);
    expect(document.querySelector('textarea')).toBeNull();
  });
});
