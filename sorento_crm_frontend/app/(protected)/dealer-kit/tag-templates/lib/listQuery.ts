/**
 * The Tag Templates list query, in ONE place, for the list and the editor's prev/next pager
 * (TAG-TEMPLATE-DUPLICATE items 2 + 5).
 *
 * The server answers the whole filtered, sorted list (it is small and unpaged); the grid pages it.
 * Both callers build their React Query key here, so the pager walks the exact rows, order and
 * filter the reader came from, and reads them from the list's own cache when it has them.
 */
import type { QueryClient, QueryKey } from '@tanstack/react-query';
import type { SortingState } from '@tanstack/react-table';
import type { ListPagerPage, ListPagerParams } from '@/hooks/useListPager';
import type { TagTemplate } from '@/lib/dealer-kit/tag-template-types';
import { listTemplates, type TemplateListFilter } from '../../services/tagTemplateService';

/** The list's filters, each a comma-joined multi-select value (`''` = no filter). */
export const TAG_TEMPLATE_FILTER_KEYS = ['price_type', 'family', 'status'] as const;
export type TagTemplateFilterKey = (typeof TAG_TEMPLATE_FILTER_KEYS)[number];
export type TagTemplateFilters = Partial<Record<TagTemplateFilterKey, string>>;

export interface TagTemplateListQuery {
  sorting: SortingState;
  searchQuery: string;
  filters: TagTemplateFilters;
}

/** Only the known filter keys, blanks dropped: the key and the request must not differ by noise. */
export function cleanFilters(filters: Record<string, string | undefined>): TagTemplateFilters {
  const out: TagTemplateFilters = {};
  for (const key of TAG_TEMPLATE_FILTER_KEYS) {
    const value = filters[key];
    if (value) out[key] = value;
  }
  return out;
}

export function toListFilter(q: TagTemplateListQuery): TemplateListFilter {
  const sort = q.sorting[0];
  const filters = cleanFilters(q.filters);
  return {
    ...filters,
    query: q.searchQuery || undefined,
    sort: sort?.id,
    dir: sort ? (sort.desc ? 'desc' : 'asc') : undefined,
  };
}

/** The list's key: the whole result for this sort + search + filter. */
export function tagTemplateListKey(q: TagTemplateListQuery): QueryKey {
  const sort = q.sorting[0];
  const filters = cleanFilters(q.filters);
  return [
    'tag-templates',
    'list',
    sort ? `${sort.id}:${sort.desc ? 'desc' : 'asc'}` : 'manual',
    q.searchQuery || '',
    ...TAG_TEMPLATE_FILTER_KEYS.map((key) => filters[key] ?? ''),
  ];
}

export function fetchTagTemplateList(q: TagTemplateListQuery): Promise<TagTemplate[]> {
  return listTemplates(toListFilter(q));
}

/** The pager's key for one page of that list. */
export function tagTemplatePageKey(params: ListPagerParams): QueryKey {
  return [...tagTemplateListKey(params), 'page', params.pageIndex, params.pageSize];
}

/** One page of the list, cut from the whole list (from the list's own cache when it has it). */
export async function fetchTagTemplatePage(
  queryClient: QueryClient,
  params: ListPagerParams,
): Promise<ListPagerPage> {
  const rows = await queryClient.fetchQuery({
    queryKey: tagTemplateListKey(params),
    queryFn: () => fetchTagTemplateList(params),
    staleTime: 30_000,
  });
  const start = params.pageIndex * params.pageSize;
  return {
    data: rows.slice(start, start + params.pageSize).map((row) => ({ id: row.id })),
    pagination: { total: rows.length },
  };
}
