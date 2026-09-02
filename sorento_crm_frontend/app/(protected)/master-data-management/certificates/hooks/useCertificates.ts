import { useMutation, useQuery, useQueryClient, type QueryKey } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  addCertificateProduct,
  bulkDeleteCertificates,
  createCertificate,
  getCertificate,
  getCertificates,
  mergeCertificateInto,
  removeCertificateProduct,
  updateCertificate,
} from '../services/certificateService';
import type { CertificatesListParams } from '../services/certificateService';
import type { CertificateFormData } from '../types/certificate.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

/**
 * Certificate register hooks.
 *
 * Layering: components -> THESE hooks -> services/certificateService -> lib/api-client
 * -> backend. No component fetches directly.
 *
 * Phase 1 resolved fixtures here; S9 swapped each body for the matching service
 * call. The query keys, params and return shapes never changed, so no component
 * needed touching.
 */

/**
 * The list's React Query key. The detail page's pager rebuilds the SAME key from
 * the URL, so it reads the page the list already fetched.
 */
export function certificatesListQueryKey(params: CertificatesListParams): QueryKey {
  return [
    'certificates',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.validity_state,
    params.expiring_within_days,
    params.scheme,
    params.status,
    params.needs_review,
  ];
}

/** The list query a detail URL describes, in the shape the list passes. */
export function certificatesListParamsFromUrl(params: ListPagerParams): CertificatesListParams {
  const f = params.filters;
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    validity_state: f.validity_state as CertificatesListParams['validity_state'],
    expiring_within_days: f.expiring_within_days
      ? Number(f.expiring_within_days)
      : undefined,
    scheme: f.scheme,
    status: f.status as CertificatesListParams['status'],
    needs_review: f.needs_review === 'true' ? true : undefined,
  };
}

/** The pager's two hooks into the certificates list. */
export const certificatesPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    certificatesListQueryKey(certificatesListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getCertificates(certificatesListParamsFromUrl(params)),
};

export function useCertificates(params: CertificatesListParams) {
  return useQuery({
    queryKey: certificatesListQueryKey(params),
    queryFn: () => getCertificates(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useCertificate(id: string | null) {
  return useQuery({
    queryKey: ['certificate', id],
    queryFn: () => {
      if (!id) throw new Error('Certificate ID is required');
      return getCertificate(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

/** Merge targets: certificates of the same scheme, excluding this one. */
export function useCertificateMergeTargets(id: string | null) {
  return useQuery({
    queryKey: ['certificate-merge-targets', id],
    // Merge targets are same-scheme certificates other than this one. Resolved
    // from the list endpoint rather than a bespoke route: the scheme comes from
    // the certificate itself, and the source row is filtered out client-side.
    queryFn: async (): Promise<{ value: string; label: string }[]> => {
      if (!id) throw new Error('Certificate ID is required');
      const source = await getCertificate(id);
      const page = await getCertificates({
        pageIndex: 0,
        pageSize: 200,
        scheme: source.scheme,
        status: 'active',
      });
      return page.data
        .filter((row) => row.id !== id)
        .map((row) => ({
          value: row.id,
          label: row.certifying_body
            ? `${row.scheme} ${row.certificate_number} - ${row.certifying_body}`
            : `${row.scheme} ${row.certificate_number}`,
        }));
    },
    enabled: !!id,
    retry: 1,
  });
}

export function useCreateCertificate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: CertificateFormData) => createCertificate(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      toast.success('Certificate created successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create certificate'),
  });
}

export function useUpdateCertificate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<CertificateFormData> }) =>
      updateCertificate(id, data),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      queryClient.invalidateQueries({ queryKey: ['certificate', variables.id] });
      toast.success('Certificate updated successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update certificate'),
  });
}

/**
 * Bulk delete stays SILENT: it is driven by the caller's own `AlertDialog`, which
 * owns the success toast and the error alert. Toasting here would double up.
 */
export function useBulkDeleteCertificates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (ids: string[]) => bulkDeleteCertificates(ids),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['certificates'] }),
  });
}

export function useMergeCertificate() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, targetId }: { id: string; targetId: string }) =>
      mergeCertificateInto(id, targetId),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      queryClient.invalidateQueries({ queryKey: ['certificate', variables.targetId] });
      toast.success('Certificates merged successfully');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to merge certificates'),
  });
}

export function useAddCertificateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, productId }: { id: string; productId: string }) =>
      addCertificateProduct(id, productId),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      queryClient.invalidateQueries({ queryKey: ['certificate', variables.id] });
      toast.success('Product added to coverage');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to add covered product'),
  });
}

export function useRemoveCertificateProduct() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, coverageId }: { id: string; coverageId: string }) =>
      removeCertificateProduct(id, coverageId),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['certificates'] });
      queryClient.invalidateQueries({ queryKey: ['certificate', variables.id] });
      toast.success('Product removed from coverage');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to remove covered product'),
  });
}
