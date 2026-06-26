'use client';

import { useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import RecordNavigation from '@/components/common/RecordNavigation';
import { parseDetailSearch } from '@/lib/listNavQuery';
import { useFormNeighbours } from '../../hooks/useForms';

interface FormNavigationProps {
  formId: string;
  className?: string;
}

export default function FormNavigation({ formId, className }: FormNavigationProps) {
  const router = useRouter();
  const searchParams = useSearchParams();

  // Reconstruct the list query the user navigated from (carried in the detail URL).
  const listParams = useMemo(() => {
    const parsed = parseDetailSearch(
      new URLSearchParams(searchParams.toString()),
    );
    return {
      pageIndex: parsed.pageIndex,
      pageSize: parsed.pageSize,
      sorting: parsed.sorting,
      searchQuery: parsed.searchQuery,
      language: parsed.filters.language,
      status: parsed.filters.status,
      form_type: parsed.filters.form_type,
    };
  }, [searchParams]);

  const { prevId, nextId, index, total, isLoading } = useFormNeighbours(
    formId,
    listParams,
  );

  // Preserve the list query when stepping to a neighbour so the set stays stable.
  const handleSelect = (id: string) => {
    const qs = searchParams.toString();
    router.push(`/forms-management/forms/${id}${qs ? `?${qs}` : ''}`);
  };

  return (
    <RecordNavigation
      basePath="/forms-management/forms"
      prevId={prevId}
      nextId={nextId}
      currentIndex={index != null ? index - 1 : undefined}
      totalCount={total}
      isLoading={isLoading}
      onSelect={handleSelect}
      ariaLabel="form"
      className={className}
    />
  );
}
