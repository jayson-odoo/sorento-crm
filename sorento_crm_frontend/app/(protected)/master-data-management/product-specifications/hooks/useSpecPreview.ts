'use client';

import { useCallback, useRef, useState } from 'react';
import {
  getSpecPreview,
  previewSpecRules,
} from '../services/productSpecService';
import type {
  SpecDerivationRule,
  SpecPreviewJobResult,
} from '../types/productSpec.types';

const POLL_MS = 1_000;

export interface UseSpecPreviewResult {
  status: 'idle' | 'pending' | 'done' | 'error';
  result: SpecPreviewJobResult | null;
  error: string | null;
  /** Start (or restart) a preview run against the current draft rules. */
  run: (rules: SpecDerivationRule[]) => void;
}

/**
 * "Preview on catalogue" (AC-B.2, B.4): enqueues the job, then polls until it stops
 * being `pending`. No countdown - the reader only ever sees a spinner while it waits,
 * because the job's actual duration is not knowable up front.
 */
export function useSpecPreview(specKey: string): UseSpecPreviewResult {
  const [status, setStatus] = useState<'idle' | 'pending' | 'done' | 'error'>(
    'idle',
  );
  const [result, setResult] = useState<SpecPreviewJobResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const runSeq = useRef(0);

  const poll = useCallback(
    (jobId: string, seq: number) => {
      getSpecPreview(specKey, jobId)
        .then((r) => {
          if (runSeq.current !== seq) return; // a newer run superseded this one
          if (r.status === 'pending') {
            window.setTimeout(() => poll(jobId, seq), POLL_MS);
            return;
          }
          setResult(r);
          setStatus('done');
        })
        .catch((e) => {
          if (runSeq.current !== seq) return;
          setError(
            e instanceof Error ? e.message : 'Could not read the preview',
          );
          setStatus('error');
        });
    },
    [specKey],
  );

  const run = useCallback(
    (rules: SpecDerivationRule[]) => {
      const seq = ++runSeq.current;
      setStatus('pending');
      setError(null);
      setResult(null);
      previewSpecRules(specKey, { rules })
        .then(({ jobId }) => {
          if (runSeq.current !== seq) return;
          poll(jobId, seq);
        })
        .catch((e) => {
          if (runSeq.current !== seq) return;
          setError(
            e instanceof Error ? e.message : 'Could not start the preview',
          );
          setStatus('error');
        });
    },
    [specKey, poll],
  );

  return { status, result, error, run };
}
