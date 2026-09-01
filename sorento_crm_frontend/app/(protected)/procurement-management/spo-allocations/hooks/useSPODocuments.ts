import { useQuery, type QueryKey } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import { listSPODocuments, getSPODocument } from '../services/spoDocumentService';
import type { SPODocumentState } from '../types/spoDocument.types';
import type { ListPagerParams, ListPagerPage } from '@/hooks/useListPager';

export interface UseSPODocumentsParams {
  pageIndex: number;
  pageSize: number;
  sorting: SortingState;
  searchQuery: string;
  state: SPODocumentState;
  productId: string | null;
  warehouseId: string | null;
  overdueOnly: boolean;
}

/** The list's React Query key. The form view's pager rebuilds the SAME key from the URL
 *  (`spoDocumentsListParamsFromUrl`), so it reads the page the list already fetched. */
export function spoDocumentsListQueryKey(params: UseSPODocumentsParams): QueryKey {
  return ['spo-allocations', 'documents', params];
}

/** The list query a form-view URL describes, in the shape the list passes. */
export function spoDocumentsListParamsFromUrl(params: ListPagerParams): UseSPODocumentsParams {
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    state: (params.filters.state as SPODocumentState) || 'outstanding',
    productId: params.filters.product_id || null,
    warehouseId: params.filters.warehouse_id || null,
    overdueOnly: params.filters.overdue_only === 'true',
  };
}

async function fetchDocumentsPage(params: UseSPODocumentsParams) {
  return listSPODocuments({
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sortField: params.sorting[0]?.id,
    sortDir: params.sorting[0]?.desc ? 'desc' : 'asc',
    searchQuery: params.searchQuery,
    state: params.state,
    product_id: params.productId,
    warehouse_id: params.warehouseId,
    overdue_only: params.overdueOnly,
  });
}

export function useSPODocuments(params: UseSPODocumentsParams) {
  return useQuery({
    queryKey: spoDocumentsListQueryKey(params),
    queryFn: () => fetchDocumentsPage(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    refetchOnWindowFocus: false,
    retry: 1,
  });
}

/** The pager's two hooks into the document list - `RecordNavigation`'s data contract
 *  (see `useListPager`). */
export const spoDocumentsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    spoDocumentsListQueryKey(spoDocumentsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    fetchDocumentsPage(spoDocumentsListParamsFromUrl(params)),
};

export function useSPODocument(spoNumber: string | null) {
  return useQuery({
    queryKey: ['spo-allocations', 'document', spoNumber],
    queryFn: () => {
      if (!spoNumber) throw new Error('SPO number is required');
      return getSPODocument(spoNumber);
    },
    enabled: !!spoNumber,
    retry: 1,
  });
}
