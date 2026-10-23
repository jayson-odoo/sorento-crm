/** Copy without `navigator.clipboard` (R19/AC-30b): the owner reaches the stack over http
 *  on a LAN or tailnet hostname, a non-secure context where the Clipboard API does not
 *  exist at all. A hidden, off-screen textarea is the standard fallback - select it, ask
 *  the browser to copy the current selection, then remove it. iOS Safari ignores
 *  `select()` on its own, so the range is set explicitly too. */
export function copyViaExecCommand(text: string): boolean {
  if (typeof document === 'undefined' || typeof document.execCommand !== 'function') return false;
  const textarea = document.createElement('textarea');
  textarea.value = text;
  // readonly keeps the phone keyboard from opening; 12pt stops iOS zooming on focus.
  textarea.setAttribute('readonly', '');
  textarea.style.position = 'fixed';
  textarea.style.top = '-1000px';
  textarea.style.opacity = '0';
  textarea.style.fontSize = '12pt';
  document.body.appendChild(textarea);
  textarea.focus();
  textarea.select();
  textarea.setSelectionRange(0, text.length);
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(textarea);
  return ok;
}

/** The Clipboard API when it exists and accepts the write, else the execCommand fallback.
 *  Resolves to whether the text landed on the clipboard. */
export async function copyTextToClipboard(text: string): Promise<boolean> {
  if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return true;
    } catch {
      // Refused (policy, permissions): fall through to the fallback below.
    }
  }
  return copyViaExecCommand(text);
}
