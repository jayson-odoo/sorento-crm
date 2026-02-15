'use client';

import { useMemo } from 'react';
import RecordNavigation from '@/components/common/RecordNavigation';
import { useComplaints } from '../hooks/useComplaints';

interface ComplaintNavigationProps {
  complaintId: string;
  className?: string;
}

export default function ComplaintNavigation({
  complaintId,
  className,
}: ComplaintNavigationProps) {
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'complaint_date', desc: true }],
      searchQuery: '',
    }),
    [],
  );
  const { data: navigationData } = useComplaints(navigationParams);
  const navigationItems = navigationData?.data ?? [];

  return (
    <RecordNavigation
      basePath="/complaint-management/complaints"
      currentId={complaintId}
      items={navigationItems}
      ariaLabel="complaint"
      className={className}
    />
  );
}
