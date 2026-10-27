import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { getRelatedDocuments } from './relatedDocumentsService';
import type {
  RelatedAnchorKind,
  RelatedSortKey,
} from './relatedDocuments.types';

export const RELATED_DOCUMENTS_KEY = ['related-documents'] as const;

export function useRelatedDocuments(
  kind: RelatedAnchorKind,
  id: string,
  sort: RelatedSortKey,
  dir: 'asc' | 'desc',
  enabled = true,
) {
  return useQuery({
    queryKey: [...RELATED_DOCUMENTS_KEY, kind, id, sort, dir],
    queryFn: () => getRelatedDocuments(kind, id, sort, dir),
    enabled: enabled && !!id,
    // A re-sort keeps the rows on screen while the server's new order loads.
    placeholderData: keepPreviousData,
  });
}
