'use client';

import { useCallback, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  buildSpecTableRows,
  type SimilarKeyMatch,
  type SpecKeyDefinition,
  type SpecScalar,
  type SpecTableRow,
} from '@/components/spec-table';
import {
  addValueToSpecKey,
  clearSpecValueByHand,
  createSpecKey,
  getApplicableSpecKeys,
  getProductSpecDetail,
  getSimilarSpecKey,
  setSpecValueByHand,
  type ApplicableSpecKey,
} from '../../product-specifications/services/productSpecService';
import type { ProductSpecDetail } from '../../product-specifications/types/productSpec.types';

/**
 * Everything the Specifications tab needs, on react-query.
 *
 * The tab used to call services directly out of `useState` + `useEffect`, which is why
 * every write ended with a hand-rolled `load()` and why two writes in quick succession
 * could leave the last response on screen rather than the last write. One query key,
 * invalidated by every mutation, is the repo's pattern and it is what makes the
 * conflict raised by an authored write appear in the same click.
 */

/**
 * The two query keys this product's specifications live under.
 *
 * Exported because the extraction panel writes the same rows through a different
 * hook, and a second copy of either key would be a write that invalidates nothing.
 */
export const DETAIL_KEY = (productId: string) => ['product-spec-detail', productId];
export const APPLICABLE_KEY = (productCode: string) => [
  'product-spec-applicable-keys',
  productCode,
];

export interface UseProductSpecTableResult {
  detail: ProductSpecDetail | undefined;
  rows: SpecTableRow[];
  /** The registry as the table needs it, for the synonym lookup behind add-a-value. */
  registry: SpecKeyDefinition[];
  /** Keys this product may carry and does not hold - the picker's first list. */
  applicableKeys: SpecKeyDefinition[];
  /** Everything else it does not hold - the picker's "show everything". */
  otherKeys: SpecKeyDefinition[];
  /** Already on the table. Not offerable, and not creatable under the same name. */
  heldKeys: SpecKeyDefinition[];
  isLoading: boolean;
  error: string | null;
  refetch: () => void;
  setValue: (specKey: string, value: SpecScalar) => Promise<void>;
  tombstone: (specKey: string) => Promise<void>;
  revert: (specKey: string) => Promise<void>;
  addValue: (specKey: string, value: string) => Promise<void>;
  createKey: (input: { spec_key: string; label: string; data_type: string }) => Promise<void>;
  checkSimilarKey: (label: string) => Promise<SimilarKeyMatch | null>;
}

function toDefinition(key: ApplicableSpecKey): SpecKeyDefinition {
  return {
    spec_key: key.spec_key,
    label: key.label,
    data_type: key.data_type,
    unit: key.unit,
    allowed_values: key.allowed_values,
    synonyms: key.synonyms,
  };
}

export function useProductSpecTable(productId: string): UseProductSpecTableResult {
  const queryClient = useQueryClient();

  const detailQuery = useQuery({
    queryKey: DETAIL_KEY(productId),
    queryFn: () => getProductSpecDetail(productId),
    enabled: Boolean(productId),
  });

  const productCode = detailQuery.data?.product_code ?? '';

  // Keyed on the CODE, not the product id: applicability is a fact about the model,
  // and a code with two company copies must not answer differently per copy.
  const keysQuery = useQuery({
    queryKey: APPLICABLE_KEY(productCode),
    queryFn: () => getApplicableSpecKeys(productCode),
    enabled: Boolean(productCode),
  });

  const allKeys = useMemo(() => keysQuery.data?.keys ?? [], [keysQuery.data]);
  const registry = useMemo(() => allKeys.map(toDefinition), [allKeys]);

  const rows = useMemo(
    () =>
      buildSpecTableRows({
        values: detailQuery.data?.spec?.values ?? {},
        provenance: detailQuery.data?.spec?.provenance ?? {},
        registry,
        exceptions: detailQuery.data?.exceptions ?? [],
      }),
    [detailQuery.data, registry],
  );

  const applicableKeys = useMemo(
    () => allKeys.filter((key) => key.applicable && !key.held).map(toDefinition),
    [allKeys],
  );
  const otherKeys = useMemo(
    () => allKeys.filter((key) => !key.applicable && !key.held).map(toDefinition),
    [allKeys],
  );
  const heldKeys = useMemo(
    () => allKeys.filter((key) => key.held).map(toDefinition),
    [allKeys],
  );

  const invalidate = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: DETAIL_KEY(productId) });
    // The picker's held/not-held split moves with every write, tombstones included.
    if (productCode) {
      queryClient.invalidateQueries({ queryKey: APPLICABLE_KEY(productCode) });
    }
  }, [queryClient, productId, productCode]);

  const setValueMutation = useMutation({
    mutationFn: ({ specKey, value }: { specKey: string; value: SpecScalar }) =>
      setSpecValueByHand(productId, specKey, value),
    onSuccess: (_data, { specKey }) => {
      invalidate();
      const label = registry.find((key) => key.spec_key === specKey)?.label ?? specKey;
      toast.success(`${label} saved`, {
        description: 'It will survive every later re-derivation.',
      });
    },
    onError: (error: Error) => toast.error(error.message, { duration: 10_000 }),
  });

  const removeMutation = useMutation({
    mutationFn: ({ specKey, mode }: { specKey: string; mode: 'absent' | 'revert' }) =>
      clearSpecValueByHand(productId, specKey, mode),
    onSuccess: invalidate,
    onError: (error: Error) => toast.error(error.message, { duration: 10_000 }),
  });

  const addValueMutation = useMutation({
    // The word alone. The server appends it under a row lock, so a word somebody else
    // added since this page loaded is still there afterwards - which sending a list
    // rebuilt from `allKeys` could not promise.
    mutationFn: ({ specKey, value }: { specKey: string; value: string }) =>
      addValueToSpecKey(specKey, value),
    onSuccess: (_data, { specKey, value }) => {
      if (productCode) {
        queryClient.invalidateQueries({ queryKey: APPLICABLE_KEY(productCode) });
      }
      const label = registry.find((key) => key.spec_key === specKey)?.label ?? specKey;
      toast.success(`"${value}" added to ${label}`);
    },
    // The near-duplicate refusal names the existing word, and saying which one is
    // the entire point - "could not add the value" leaves the user retyping it.
    onError: (error: Error) => toast.error(error.message, { duration: 10_000 }),
  });

  const createKeyMutation = useMutation({
    mutationFn: (input: { spec_key: string; label: string; data_type: string }) =>
      createSpecKey({ ...input, allowed_values: [] }),
    onSuccess: (_data, input) => {
      if (productCode) {
        queryClient.invalidateQueries({ queryKey: APPLICABLE_KEY(productCode) });
      }
      toast.success(`${input.label} created`);
    },
    onError: (error: Error) => toast.error(error.message, { duration: 10_000 }),
  });

  return {
    detail: detailQuery.data,
    rows,
    registry,
    applicableKeys,
    otherKeys,
    heldKeys,
    isLoading: detailQuery.isPending || (Boolean(productCode) && keysQuery.isPending),
    error: detailQuery.error
      ? (detailQuery.error as Error).message
      : keysQuery.error
        ? (keysQuery.error as Error).message
        : null,
    refetch: () => {
      void detailQuery.refetch();
      void keysQuery.refetch();
    },
    setValue: async (specKey, value) => {
      await setValueMutation.mutateAsync({ specKey, value });
    },
    tombstone: async (specKey) => {
      await removeMutation.mutateAsync({ specKey, mode: 'absent' });
    },
    revert: async (specKey) => {
      await removeMutation.mutateAsync({ specKey, mode: 'revert' });
    },
    addValue: async (specKey, value) => {
      await addValueMutation.mutateAsync({ specKey, value });
    },
    createKey: async (input) => {
      await createKeyMutation.mutateAsync(input);
    },
    checkSimilarKey: (label) => getSimilarSpecKey(label),
  };
}
