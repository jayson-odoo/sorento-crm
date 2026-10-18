import { useMemo, useRef } from 'react';
import { usePermissions } from '@/hooks/usePermissions';
import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryKey,
} from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import type { LookupFetcher } from '@/components/common/NewProductApplicationSheet';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import type {
  NewProductApplicationFeedbackWrite,
  NewProductApplicationWrite,
} from '@/types/newProductApplication';
import {
  approveNewProductApplication,
  cancelNewProductApplication,
  closeNewProductApplicationLine,
  createNewProductApplication,
  getNewProductApplication,
  getNewProductApplicationPrefill,
  getNewProductApplications,
  getStockInquiryApplications,
  linkNewProductApplicationLine,
  rejectNewProductApplication,
  reviseNewProductApplication,
  saveNewProductApplicationFeedback,
  submitNewProductApplication,
  undoNewProductApplicationLine,
  updateNewProductApplication,
  type NewProductApplicationListParams,
} from '../services/newProductApplicationService';

const NPA_SLUGS = [
  'procurement.new_product_applications.view',
  'procurement.new_product_applications.approve',
  'procurement.new_product_applications.open_code',
  'procurement.new_product_applications.create',
] as const;

/**
 * Column preferences are authorised by the listing key's slug
 * (list_query._can_view_listing_key), so each grid is keyed by a slug the reader
 * actually holds; a create-only applicant keyed by `view` got a 403 and a grid
 * stuck on its skeleton (browser pass, 18 Oct).
 */
export function useNewProductApplicationListingKey(suffix?: string): string | null {
  const { permissionSet, isLoading } = usePermissions();
  // null (no preference fetch at all, data-grid.tsx) until the permissions are known:
  // guessing `view` on the first render fired a 403 and a "Permission denied" toast at a
  // create-only applicant on every visit (browser pass, 18 Oct).
  const slug = isLoading ? undefined : NPA_SLUGS.find((s) => permissionSet.has(s));
  if (!slug) return null;
  return suffix ? `${slug}::${suffix}` : slug;
}

/** The list's React Query key; the detail pager rebuilds the SAME key from the URL. */
export function newProductApplicationsListQueryKey(
  params: NewProductApplicationListParams,
): QueryKey {
  return [
    'new-product-applications',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.status,
    params.applicantId,
  ];
}

function listParamsFromUrl(
  params: ListPagerParams,
): NewProductApplicationListParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: params.filters.status,
    applicantId: params.filters.applicant_id,
  };
}

/** The pager's two hooks into the applications list. */
export const newProductApplicationsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    newProductApplicationsListQueryKey(listParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getNewProductApplications(listParamsFromUrl(params)),
};

export function useNewProductApplicationsQuery(
  params: NewProductApplicationListParams,
) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: newProductApplicationsListQueryKey(params),
    queryFn: () => getNewProductApplications(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useNewProductApplicationQuery(id: string | null) {
  return useQuery({
    queryKey: ['new-product-application', id],
    queryFn: () => {
      if (!id) throw new Error('Application ID is required');
      return getNewProductApplication(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

/** The pre-fill copied from a responded stock inquiry; fetched once per inquiry. */
export function useNewProductApplicationPrefillQuery(
  stockInquiryId: string | null,
) {
  return useQuery({
    queryKey: ['new-product-application', 'prefill', stockInquiryId],
    queryFn: () => getNewProductApplicationPrefill(stockInquiryId as string),
    enabled: !!stockInquiryId,
    staleTime: Infinity,
    retry: 1,
  });
}

/** The applications raised from one stock inquiry; `enabled` is false for users with no NPA permission. */
export function useStockInquiryApplicationsQuery(
  stockInquiryId: string | null,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['new-product-applications', 'stock-inquiry', stockInquiryId],
    queryFn: () => getStockInquiryApplications(stockInquiryId as string),
    enabled: enabled && !!stockInquiryId,
    retry: 1,
  });
}

const matches = (label: string, q: string) =>
  label.toLowerCase().includes(q.trim().toLowerCase());

/**
 * The one select of the paper sheet: brand, from the master-data select hook (read once,
 * filtered here). The portal passes its own lookup to the same sheet.
 */
export function useNewProductApplicationLookups(): { brands: LookupFetcher } {
  const brands = useBrandSelectQuery();
  // The fetcher stays the same function between renders, so an open dropdown is not
  // refetched each time the query settles; it reads what the hook last returned.
  const latest = useRef<SearchableSelectOption[]>([]);
  latest.current = (brands.data ?? []).map((b) => ({
    value: b.id,
    label: b.brand_name,
    code: b.brand_code,
  }));
  return useMemo(
    () => ({
      brands: async (q: string) =>
        latest.current.filter(
          (o) => !q.trim() || matches(`${o.label} ${o.code ?? ''}`, q),
        ),
    }),
    [],
  );
}

export function useNewProductApplicationMutations() {
  const queryClient = useQueryClient();
  const refresh = () => {
    void queryClient.invalidateQueries({
      queryKey: ['new-product-applications'],
    });
    void queryClient.invalidateQueries({
      queryKey: ['new-product-application'],
    });
  };
  const fail = (fallback: string) => (error: Error) =>
    toast.error(error.message || fallback);
  const move = (fallback: string, done?: string) => ({
    onSuccess: () => {
      refresh();
      if (done) toast.success(done);
    },
    onError: fail(fallback),
  });

  const create = useMutation({
    mutationFn: (data: NewProductApplicationWrite) =>
      createNewProductApplication(data),
    ...move('Failed to save the application'),
  });
  const update = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: NewProductApplicationWrite;
    }) => updateNewProductApplication(id, data),
    ...move('Failed to save the application'),
  });
  const submit = useMutation({
    mutationFn: (id: string) => submitNewProductApplication(id),
    ...move('Failed to submit the application', 'Application submitted'),
  });
  const approve = useMutation({
    mutationFn: (id: string) => approveNewProductApplication(id),
    ...move('Failed to approve the application', 'Application approved'),
  });
  const reject = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      rejectNewProductApplication(id, reason),
    ...move('Failed to reject the application', 'Application rejected'),
  });
  const revise = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      reviseNewProductApplication(id, reason),
    ...move('Failed to revise the application', 'Back to draft'),
  });
  const cancel = useMutation({
    mutationFn: ({ id, reason }: { id: string; reason?: string }) =>
      cancelNewProductApplication(id, reason),
    ...move('Failed to cancel the application', 'Application cancelled'),
  });
  const link = useMutation({
    mutationFn: ({
      id,
      lineId,
      productId,
    }: {
      id: string;
      lineId: string;
      productId: string;
    }) => linkNewProductApplicationLine(id, lineId, productId),
    ...move('Failed to link the product', 'Product linked'),
    // Two purchasers on one line: the second write is refused (409) and the screen refreshes.
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to link the product');
      refresh();
    },
  });
  const close = useMutation({
    mutationFn: ({
      id,
      lineId,
      reason,
    }: {
      id: string;
      lineId: string;
      reason: string;
    }) => closeNewProductApplicationLine(id, lineId, reason),
    ...move('Failed to close the line'),
  });
  const feedback = useMutation({
    mutationFn: ({
      id,
      data,
    }: {
      id: string;
      data: NewProductApplicationFeedbackWrite;
    }) => saveNewProductApplicationFeedback(id, data),
    ...move('Failed to save the feedback', 'Feedback saved'),
  });
  const undo = useMutation({
    mutationFn: ({ id, lineId }: { id: string; lineId: string }) =>
      undoNewProductApplicationLine(id, lineId),
    ...move('Failed to undo the line'),
  });

  return {
    create,
    update,
    submit,
    approve,
    reject,
    revise,
    cancel,
    link,
    close,
    undo,
    feedback,
  };
}
