'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useAttachmentNeighbours } from '../hooks/useAttachments';

interface AttachmentNavigationProps {
  attachmentId: string;
  className?: string;
}

/**
 * Prev/next pager for the attachment detail page. Reconstructs the list query the
 * user navigated from (search/sort + folder/linkage/type/uploader/date filters,
 * carried in the detail URL via `buildDetailSearch`) and feeds it to the backend
 * neighbours endpoint so prev/next walks the exact same filtered+sorted set.
 */
export default function AttachmentNavigation({
  attachmentId,
  className,
}: AttachmentNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(
      new URLSearchParams(searchParams.toString()),
    );
    const { filters } = parsed;
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      entity_type: filters.entity_type,
      attachment_type_id: filters.attachment_type_id,
      directory_id: filters.directory_id,
      is_deleted: filters.is_deleted === 'true' ? true : undefined,
      link_status:
        filters.link_status === 'linked' || filters.link_status === 'unlinked'
          ? (filters.link_status as 'linked' | 'unlinked')
          : undefined,
      storage_status: filters.storage_status as
        | 'accessible'
        | 'missing'
        | 'unchecked'
        | undefined,
      uploaded_by: filters.uploaded_by,
      uploaded_at_from: filters.uploaded_at_from,
      uploaded_at_to: filters.uploaded_at_to,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useAttachmentNeighbours(
    attachmentId,
    listParams,
  );

  // Preserve the carried list query (and the from/directoryId back-link hints)
  // when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/resource-management/attachments/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath="/resource-management/attachments"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="attachment"
      className={className}
    />
  );
}
