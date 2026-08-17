'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  getSpecVerificationWorklist,
  unverifySpecBulk,
  verifySpecBulk,
} from '../services/specVerificationService';
import type {
  SpecVerificationSummary,
  SpecVerificationWorklistParams,
  SpecVerificationWorklistResponse,
  UnverifyBulkResponse,
  UnverifyBulkResult,
  VerifyBulkResponse,
  VerifyBulkResult,
  VerifyItem,
} from '../types/specVerification.types';

export const WORKLIST_KEY = 'spec-verification-worklist';

export function useSpecVerificationWorklist(
  params: SpecVerificationWorklistParams,
) {
  return useQuery({
    queryKey: [
      WORKLIST_KEY,
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.state,
      params.class_label,
      params.include_discontinued,
    ],
    queryFn: () => getSpecVerificationWorklist(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/** Outcomes that leave the code stamped; everything else is a skip. */
const ACTED_VERIFY_OUTCOMES = new Set(['verified', 'already_verified']);

const VERIFY_SKIP_LABEL: Record<string, string> = {
  exceptions_open: 'exceptions open',
  values_changed: 'changed while you were reviewing',
  not_found: 'no longer in the list',
};

/** "42 verified, 3 skipped - exceptions open, 1 skipped - changed while you were reviewing". */
export function summariseVerify(results: VerifyBulkResult[]): string {
  const acted = results.filter((r) =>
    ACTED_VERIFY_OUTCOMES.has(r.outcome),
  ).length;
  const parts = acted > 0 ? [`${acted} verified`] : [];
  for (const [outcome, label] of Object.entries(VERIFY_SKIP_LABEL)) {
    const n = results.filter((r) => r.outcome === outcome).length;
    if (n > 0) parts.push(`${n} skipped - ${label}`);
  }
  return parts.join(', ');
}

/** "3 unverified, 1 unchanged". */
export function summariseUnverify(results: UnverifyBulkResult[]): string {
  const acted = results.filter((r) => r.outcome === 'unverified').length;
  const parts = acted > 0 ? [`${acted} unverified`] : [];
  const unchanged = results.length - acted;
  if (unchanged > 0) parts.push(`${unchanged} unchanged`);
  return parts.join(', ');
}

/** Codes the batch could not act on. They stay selected so they can be dealt with. */
export function skippedVerifyCodes(results: VerifyBulkResult[]): string[] {
  return results
    .filter((r) => !ACTED_VERIFY_OUTCOMES.has(r.outcome))
    .map((r) => r.product_code);
}

export function skippedUnverifyCodes(results: UnverifyBulkResult[]): string[] {
  return results
    .filter((r) => r.outcome !== 'unverified')
    .map((r) => r.product_code);
}

function nextSummary(
  summary: SpecVerificationSummary,
  deltas: Record<string, number>,
): SpecVerificationSummary {
  return {
    total: summary.total,
    verified: summary.verified + (deltas.verified ?? 0),
    needs_reverify: summary.needs_reverify + (deltas.needs_reverify ?? 0),
    unverified: summary.unverified + (deltas.unverified ?? 0),
  };
}

/**
 * Patch the acted rows in place rather than refetching.
 *
 * The default order puts verified rows last, so a refetch would move the row the
 * user just stamped out from under their cursor (AC-D.22). The order is only
 * re-read when they page or reload.
 */
function patchRows(
  old: SpecVerificationWorklistResponse | undefined,
  results: (VerifyBulkResult | UnverifyBulkResult)[],
): SpecVerificationWorklistResponse | undefined {
  if (!old) return old;
  const byCode = new Map(results.map((r) => [r.product_code, r]));
  const deltas: Record<string, number> = {};
  const data = old.data.map((row) => {
    const result = byCode.get(row.product_code);
    if (!result?.verification) return row;
    const before = row.verification.state;
    const after = result.verification.state;
    if (before !== after) {
      deltas[before] = (deltas[before] ?? 0) - 1;
      deltas[after] = (deltas[after] ?? 0) + 1;
    }
    return {
      ...row,
      verification: result.verification,
      values_hash:
        'values_hash' in result && result.values_hash
          ? result.values_hash
          : row.values_hash,
    };
  });
  return { ...old, data, summary: nextSummary(old.summary, deltas) };
}

export function useSpecVerificationMutations() {
  const queryClient = useQueryClient();

  const applyToCache = (results: (VerifyBulkResult | UnverifyBulkResult)[]) => {
    queryClient.setQueriesData<SpecVerificationWorklistResponse>(
      { queryKey: [WORKLIST_KEY] },
      (old) => patchRows(old, results),
    );
  };

  const verify = useMutation<VerifyBulkResponse, Error, VerifyItem[]>({
    mutationFn: (items) => verifySpecBulk(items),
    onSuccess: (response) => {
      applyToCache(response.results);
      const message = summariseVerify(response.results);
      if (response.counts.verified > 0) toast.success(message);
      else toast.warning(message);
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : 'Failed to verify');
    },
  });

  const unverify = useMutation<UnverifyBulkResponse, Error, string[]>({
    mutationFn: (productCodes) => unverifySpecBulk(productCodes),
    onSuccess: (response) => {
      applyToCache(response.results);
      const message = summariseUnverify(response.results);
      if (response.counts.unverified > 0) toast.success(message);
      else toast.warning(message);
    },
    onError: (error) => {
      toast.error(
        error instanceof Error ? error.message : 'Failed to unverify',
      );
    },
  });

  return { verify, unverify };
}
