import { useCallback, useRef, useState } from 'react';

/**
 * The guided form's section rule, first written for the price tag request (D-P1) and shared with
 * the sample request (owner hand test 12 Nov: "similar to price tag request"):
 *
 * - The form starts with the sections in `initial` open (the first one) and the rest collapsed.
 * - `openOnce(key)` is a rule opening a section as the form gains the value it needs (the previous
 *   section filled, or a loaded record that already holds values). Each rule fires once per
 *   section per form load.
 * - `toggle(key, next)` is the person's own click, or a problem that must be in view: it always
 *   applies, and a section the person collapsed by hand is never reopened by a rule.
 */
export function useProgressiveSections<K extends string>(initial: Record<K, boolean>) {
  const [open, setOpen] = useState<Record<K, boolean>>(initial);
  const settled = useRef<Set<K>>(new Set());

  const openOnce = useCallback((key: K) => {
    if (settled.current.has(key)) return;
    settled.current.add(key);
    setOpen((prev) => (prev[key] ? prev : { ...prev, [key]: true }));
  }, []);

  const toggle = useCallback((key: K, next: boolean) => {
    settled.current.add(key);
    setOpen((prev) => ({ ...prev, [key]: next }));
  }, []);

  return { open, openOnce, toggle };
}
