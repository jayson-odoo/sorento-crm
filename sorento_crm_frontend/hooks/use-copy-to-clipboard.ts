'use client';

import * as React from 'react';

/**
 * One copy, and the checkmark that answers it (S7-05).
 *
 * A copy is confirmed where it was asked for: the button's icon becomes a tick
 * for two seconds. It does not raise a toast. A toast is the app interrupting
 * to report something the reader could not otherwise know, and the reader
 * pressed Copy on purpose, one moment ago, on a button they are still looking
 * at - so a card sliding in from the corner of the screen is telling them what
 * they already did.
 *
 * `copyToClipboard` resolves to whether the write landed, because failure is a
 * different matter: the clipboard is refused over plain HTTP and by some
 * browser policies, and nothing on screen would otherwise say so. That path
 * keeps its toast, at the call site, which is also where the fallback lives
 * (show the link so the reader can copy it by hand).
 */
export function useCopyToClipboard({
  timeout = 2000,
  onCopy,
}: {
  timeout?: number;
  onCopy?: () => void;
} = {}) {
  const [isCopied, setIsCopied] = React.useState(false);
  const resetTimer = React.useRef<ReturnType<typeof setTimeout> | null>(null);

  React.useEffect(
    () => () => {
      if (resetTimer.current) clearTimeout(resetTimer.current);
    },
    [],
  );

  const copyToClipboard = React.useCallback(
    async (value: string): Promise<boolean> => {
      if (typeof window === 'undefined' || !navigator.clipboard?.writeText) return false;
      if (!value) return false;

      try {
        await navigator.clipboard.writeText(value);
      } catch {
        return false;
      }

      setIsCopied(true);
      onCopy?.();

      if (resetTimer.current) clearTimeout(resetTimer.current);
      resetTimer.current = setTimeout(() => setIsCopied(false), timeout);
      return true;
    },
    [onCopy, timeout],
  );

  return { isCopied, copyToClipboard };
}
