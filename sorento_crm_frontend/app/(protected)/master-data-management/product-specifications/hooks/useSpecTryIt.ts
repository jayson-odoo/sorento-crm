'use client';

import { useEffect, useRef, useState } from 'react';
import { trySpecRules } from '../services/productSpecService';
import type {
  SpecDerivationRule,
  SpecTryResult,
} from '../types/productSpec.types';

const DEBOUNCE_MS = 300;

/** What the try-it panel is trying: a real product (by id) or pasted text. */
export type TryItSource =
  | { type: 'product'; productId: string; productLabel: string }
  | { type: 'text'; text: string };

export interface UseSpecTryItResult {
  result: SpecTryResult | null;
  loading: boolean;
  error: string | null;
}

/**
 * Runs the draft rules against a real product or pasted text (AC-B.3), debounced so
 * every keystroke in a blank does not fire a call. Any edit to `rules` or `source`
 * re-runs it; picking `source` to null clears the result rather than calling with
 * nothing to try.
 */
export function useSpecTryIt(
  specKey: string,
  rules: SpecDerivationRule[],
  source: TryItSource | null,
): UseSpecTryItResult {
  const [result, setResult] = useState<SpecTryResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const requestSeq = useRef(0);

  useEffect(() => {
    if (!source || (source.type === 'text' && !source.text.trim())) {
      setResult(null);
      setError(null);
      setLoading(false);
      return;
    }

    const seq = ++requestSeq.current;
    setLoading(true);
    setError(null);

    const timer = window.setTimeout(() => {
      const body =
        source.type === 'product'
          ? {
              rules,
              productId: source.productId,
              productLabel: source.productLabel,
            }
          : { rules, text: source.text };
      trySpecRules(specKey, body)
        .then((r) => {
          if (requestSeq.current !== seq) return; // stale
          setResult(r);
        })
        .catch((e) => {
          if (requestSeq.current !== seq) return;
          setError(
            e instanceof Error ? e.message : 'Could not try these rules',
          );
          setResult(null);
        })
        .finally(() => {
          if (requestSeq.current === seq) setLoading(false);
        });
    }, DEBOUNCE_MS);

    return () => window.clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [specKey, JSON.stringify(rules), source && JSON.stringify(source)]);

  return { result, loading, error };
}
