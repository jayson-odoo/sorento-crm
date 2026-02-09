'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface RecordNavigationProps {
  currentId: string;
  items: Array<{ id: string }>;
  basePath: string;
  className?: string;
}

export default function RecordNavigation({
  currentId,
  items,
  basePath,
  className,
}: RecordNavigationProps) {
  const router = useRouter();
  const { previousId, nextId } = useMemo(() => {
    const currentIndex = items.findIndex((item) => item.id === currentId);
    return {
      previousId: currentIndex > 0 ? items[currentIndex - 1].id : null,
      nextId:
        currentIndex >= 0 && currentIndex < items.length - 1
          ? items[currentIndex + 1].id
          : null,
    };
  }, [items, currentId]);

  return (
    <div
      className={['flex gap-2', className].filter(Boolean).join(' ')}
      aria-label="Record navigation"
    >
      <Button
        variant="outline"
        size="icon"
        aria-label="Previous record"
        disabled={!previousId}
        onClick={() => previousId && router.push(`${basePath}/${previousId}`)}
      >
        <ChevronLeft className="size-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        aria-label="Next record"
        disabled={!nextId}
        onClick={() => nextId && router.push(`${basePath}/${nextId}`)}
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
