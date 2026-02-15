'use client';

import { useMemo } from 'react';
import RecordNavigation from '@/components/common/RecordNavigation';
import { usePackingLists } from '../hooks/usePackingLists';

interface PackingListNavigationProps {
  packingListId: string;
  className?: string;
}

export default function PackingListNavigation({
  packingListId,
  className,
}: PackingListNavigationProps) {
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = usePackingLists(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  return (
    <RecordNavigation
      basePath="/procurement-management/packing-lists"
      currentId={packingListId}
      items={navigationItems}
      ariaLabel="packing list"
      className={className}
    />
  );
}
