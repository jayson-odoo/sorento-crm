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
  it('selects the whole text (setSelectionRange for iOS) and leaves no textarea behind', () => {
    let selected = '';
    Object.defineProperty(document, 'execCommand', {
      value: vi.fn(() => {
        const el = document.activeElement as HTMLTextAreaElement;
        selected = el.value.slice(el.selectionStart, el.selectionEnd);
        return true;
      }),
      configurable: true,
    });
    expect(copyViaExecCommand('hello world')).toBe(true);
    expect(selected).toBe('hello world');
    expect(document.querySelector('textarea')).toBeNull();
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
