'use client';

import { useEffect, useState } from 'react';

const QUERY = '(max-width: 639px)';

/** True below the Tailwind `sm` breakpoint (640px), where the page draws cards instead of the grid. */
export function useIsPhone(): boolean {
  const [phone, setPhone] = useState(false);
  useEffect(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    const mql = window.matchMedia(QUERY);
    const sync = () => setPhone(mql.matches);
    sync();
    mql.addEventListener('change', sync);
    return () => mql.removeEventListener('change', sync);
  }, []);
  return phone;
}
