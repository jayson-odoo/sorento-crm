'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useComplaints } from '../hooks/useComplaints';

interface ComplaintNavigationProps {
  complaintId: string;
  className?: string;
}

export default function ComplaintNavigation({
  complaintId,
  className,
}: ComplaintNavigationProps) {
  const router = useRouter();
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
  const currentIndex = navigationItems.findIndex(
    (item) => item.id === complaintId,
  );
  const previousId = currentIndex > 0 ? navigationItems[currentIndex - 1].id : null;
  const nextId =
    currentIndex >= 0 && currentIndex < navigationItems.length - 1
      ? navigationItems[currentIndex + 1].id
      : null;

  return (
    <div
      className={['flex gap-2', className].filter(Boolean).join(' ')}
      aria-label="Complaint navigation"
    >
      <Button
        variant="outline"
        size="icon"
        aria-label="Previous complaint"
        disabled={!previousId}
        onClick={() =>
          previousId &&
          router.push(`/complaint-management/complaints/${previousId}`)
        }
      >
        <ChevronLeft className="size-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        aria-label="Next complaint"
        disabled={!nextId}
        onClick={() =>
          nextId &&
          router.push(`/complaint-management/complaints/${nextId}`)
        }
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
