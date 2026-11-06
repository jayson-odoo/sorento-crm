'use client';

/**
 * Prev/next + "N / M" in the template editor's header (TAG-TEMPLATE-DUPLICATE item 2): the shared
 * `ListPager` (`components/common/ListPager.tsx`) walking the Tag Templates list the reader came
 * from, in its order (manual or a sorted column) and with its search and filters, all read back
 * from the editor URL the list's row link wrote. Hidden on a deep link that names no such list.
 */
import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import ListPager from '@/components/common/ListPager';
import type { ListPagerParams } from '@/hooks/useListPager';
import { fetchTagTemplatePage, tagTemplatePageKey } from '../lib/listQuery';

export function TemplateRecordPager({ id }: { id: string }) {
  const queryClient = useQueryClient();
  const fetchPage = useCallback(
    (params: ListPagerParams) => fetchTagTemplatePage(queryClient, params),
    [queryClient],
  );
  return (
    <ListPager
      listQueryKey={tagTemplatePageKey}
      fetchPage={fetchPage}
      detailPath="/dealer-kit/tag-templates"
      currentId={id}
      ariaLabel="template"
    />
  );
}
