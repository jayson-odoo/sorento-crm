'use client';

import { useCallback, useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import type { SpecProposal } from '@/components/spec-proposals';
import {
  applySpecProposals,
  extractSpecProposals,
  type SpecExtractionResult,
  type SpecProposalEntry,
} from '../../product-specifications/services/productSpecService';
import { APPLICABLE_KEY, DETAIL_KEY } from './useProductSpecTable';

/**
 * Read a pasted text, hold what it proposed, and write what was accepted.
 *
 * Two mutations rather than a query: extraction is something a person asks for by
 * pressing a button, and a query would re-run it on every refocus - the same text
 * read three times, billed three times, for an answer nobody asked for again.
 *
 * The result is held here, not in the panel, so the ticked selection and the
 * proposals it indexes cannot get out of step with each other: applying clears both
 * in the same place, and a failed apply keeps both.
 */

export interface UseSpecExtractionResult {
  result: SpecExtractionResult | null;
  proposals: SpecProposal[];
  /** The ticked keys. Seeded with every non-conflict key when proposals arrive. */
  selectedKeys: string[];
  setSelectedKeys: (keys: string[]) => void;
  isExtracting: boolean;
  isApplying: boolean;
  /** The last extraction failure, kept on screen with the text that caused it. */
  error: string | null;
  extract: (text: string) => Promise<void>;
  apply: () => Promise<boolean>;
  /** Throw the proposals away without writing anything. */
  discard: () => void;
}

export function useSpecExtraction(
  productId: string,
  productCode: string,
): UseSpecExtractionResult {
  const queryClient = useQueryClient();
  const [result, setResult] = useState<SpecExtractionResult | null>(null);
  const [selectedKeys, setSelectedKeys] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const discard = useCallback(() => {
    setResult(null);
    setSelectedKeys([]);
    setError(null);
  }, []);

  const extractMutation = useMutation({
    mutationFn: (text: string) => extractSpecProposals(productId, text),
    onSuccess: (answer) => {
      setResult(answer);
      // Conflicts arrive UNTICKED (AC-B.7): everything else is the machine agreeing
      // with itself, but a conflict would overwrite a value a person vouched for, and
      // a default that does that is a default nobody reviewed.
      setSelectedKeys(
        answer.proposals.filter((row) => row.kind !== 'conflict').map((row) => row.spec_key),
      );
      setError(null);
    },
    // Shown in place rather than as a toast alone: the text that caused it is still in
    // the box, and the message is what tells the user whether to change it or retry.
    onError: (failure: Error) => {
      setResult(null);
      setSelectedKeys([]);
      setError(failure.message);
    },
  });

  const applyMutation = useMutation({
    mutationFn: (entries: SpecProposalEntry[]) => applySpecProposals(productId, entries),
    onSuccess: (answer) => {
      queryClient.invalidateQueries({ queryKey: DETAIL_KEY(productId) });
      // The picker's held/not-held split moves with every write.
      if (productCode) {
        queryClient.invalidateQueries({ queryKey: APPLICABLE_KEY(productCode) });
      }
      // `spec_keys`, never `rows_written`: the write fans out to every company copy
      // of the code, so two accepted specifications on a two-company code report four
      // rows written. The user ticked two, and a toast that says four is the system
      // describing its own plumbing back at them.
      const saved = answer.spec_keys.length;
      toast.success(`${saved} specification${saved === 1 ? '' : 's'} saved`, {
        description: 'Each one carries the words it was read from.',
      });
      discard();
    },
    onError: (failure: Error) => toast.error(failure.message, { duration: 10_000 }),
  });

  return {
    result,
    proposals: result?.proposals ?? [],
    selectedKeys,
    setSelectedKeys,
    isExtracting: extractMutation.isPending,
    isApplying: applyMutation.isPending,
    error,
    extract: async (text: string) => {
      await extractMutation.mutateAsync(text).catch(() => undefined);
    },
    apply: async () => {
      const picked = new Set(selectedKeys);
      const entries: SpecProposalEntry[] = (result?.proposals ?? [])
        .filter((row) => picked.has(row.spec_key))
        .map((row) => ({
          spec_key: row.spec_key,
          value: row.value,
          unit: row.unit,
          evidence: row.evidence,
        }));
      try {
        await applyMutation.mutateAsync(entries);
        return true;
      } catch {
        return false;
      }
    },
    discard,
  };
}
