'use client';

import { useEffect, useState } from 'react';

/**
 * Re-emits `value` only after it has settled for `delayMs`, without the
 * settling/search-box concerns `useDebouncedSearch` carries (S7-02's hook is
 * string-only and owns its own input state). Used by the email theme and
 * email template live previews, which would otherwise re-request a render on
 * every keystroke.
 */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(value), delayMs]);

  return debounced;
}
