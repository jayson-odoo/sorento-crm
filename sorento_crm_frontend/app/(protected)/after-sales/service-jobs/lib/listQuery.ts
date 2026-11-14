import type { QueryKey } from '@tanstack/react-query';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import { splitMulti } from '@/lib/list-filters/multiValue';
import { getServiceJobs, type ServiceJobsListParams } from '../services/serviceJobService';

/**
 * The list's React Query key. The job page's pager rebuilds the SAME key from the URL, so it
 * reads the page the list already fetched.
 */
export function serviceJobsListQueryKey(params: ServiceJobsListParams): QueryKey {
  return [
    'service-jobs',
    params.pageIndex,
    params.pageSize,
    params.sorting,
    params.searchQuery,
    params.status?.join(',') ?? '',
    params.technician_id?.join(',') ?? '',
    params.warranty_summary?.join(',') ?? '',
    params.date_from ?? '',
    params.date_to ?? '',
  ];
}

export function serviceJobsListParamsFromUrl(params: ListPagerParams): ServiceJobsListParams {
  const f = params.filters;
  return {
    pageIndex: params.pageIndex,
    pageSize: params.pageSize,
    sorting: params.sorting,
    searchQuery: params.searchQuery,
    status: f.status ? splitMulti(f.status) : undefined,
    technician_id: f.technician_id ? splitMulti(f.technician_id) : undefined,
    warranty_summary: f.warranty_summary ? splitMulti(f.warranty_summary) : undefined,
    date_from: f.date_from || undefined,
    date_to: f.date_to || undefined,
  };
}

/** The pager's two hooks into the service jobs list. */
export const serviceJobsPagerQuery = {
  listQueryKey: (params: ListPagerParams): QueryKey =>
    serviceJobsListQueryKey(serviceJobsListParamsFromUrl(params)),
  fetchPage: (params: ListPagerParams): Promise<ListPagerPage> =>
    getServiceJobs(serviceJobsListParamsFromUrl(params)),
};
