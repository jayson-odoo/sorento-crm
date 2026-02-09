'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { usePackingLists } from '../hooks/usePackingLists';

interface PackingListNavigationProps {
  packingListId: string;
  className?: string;
}

export default function PackingListNavigation({
  packingListId,
  className,
}: PackingListNavigationProps) {
  const router = useRouter();
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
  const currentIndex = navigationItems.findIndex(
    (item) => item.id === packingListId,
  );
  const previousId =
    currentIndex > 0 ? navigationItems[currentIndex - 1].id : null;
  const nextId =
    currentIndex >= 0 && currentIndex < navigationItems.length - 1
      ? navigationItems[currentIndex + 1].id
      : null;

  return (
    <div
      className={['flex gap-2', className].filter(Boolean).join(' ')}
      aria-label="Packing list navigation"
    >
      <Button
        variant="outline"
        size="icon"
        aria-label="Previous packing list"
        disabled={!previousId}
        onClick={() =>
          previousId &&
          router.push(`/procurement-management/packing-lists/${previousId}`)
        }
      >
        <ChevronLeft className="size-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        aria-label="Next packing list"
        disabled={!nextId}
        onClick={() =>
          nextId &&
          router.push(`/procurement-management/packing-lists/${nextId}`)
        }
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
