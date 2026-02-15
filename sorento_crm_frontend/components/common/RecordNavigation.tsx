'use client';

import { useMemo } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

/** Props when using API neighbours (prevId/nextId from useRecordNeighbours or similar). */
export interface RecordNavigationIdsProps {
  basePath: string;
  prevId: string | null;
  nextId: string | null;
  /** e.g. "record", "complaint", "purchase request" for aria-label */
  ariaLabel?: string;
  className?: string;
  /** When provided, called with prevId/nextId instead of router.push (e.g. modal in-place navigation) */
  onSelect?: (id: string) => void;
}

/** Props when using a full list (compute prev/next from currentId + items). */
export interface RecordNavigationListProps {
  basePath: string;
  currentId: string;
  items: Array<{ id: string }>;
  ariaLabel?: string;
  className?: string;
  /** When provided, called with selected id instead of router.push (e.g. modal in-place navigation) */
  onSelect?: (id: string) => void;
}

export type RecordNavigationProps = RecordNavigationIdsProps | RecordNavigationListProps;

function isIdsProps(
  props: RecordNavigationProps,
): props is RecordNavigationIdsProps {
  return 'prevId' in props && 'nextId' in props;
}

/**
 * Reusable prev/next (chevron) navigation for detail/form views.
 * Use with useRecordNeighbours when the backend has a neighbours endpoint,
 * or pass currentId + items when you have the full list in memory.
 */
export default function RecordNavigation(props: RecordNavigationProps) {
  const router = useRouter();
  const { basePath, ariaLabel = 'record', className, onSelect } = props;

  const { previousId, nextId } = useMemo(() => {
    if (isIdsProps(props)) {
      return { previousId: props.prevId, nextId: props.nextId };
    }
    const { currentId, items } = props;
    const currentIndex = items.findIndex((item) => item.id === currentId);
    return {
      previousId: currentIndex > 0 ? items[currentIndex - 1].id : null,
      nextId:
        currentIndex >= 0 && currentIndex < items.length - 1
          ? items[currentIndex + 1].id
          : null,
    };
  }, [props]);

  return (
    <div
      className={['flex gap-2', className].filter(Boolean).join(' ')}
      aria-label={`${ariaLabel} navigation`}
    >
      <Button
        variant="outline"
        size="icon"
        aria-label={`Previous ${ariaLabel}`}
        disabled={!previousId}
        onClick={() => {
          if (!previousId) return;
          if (onSelect) onSelect(previousId);
          else router.push(`${basePath}/${previousId}`);
        }}
      >
        <ChevronLeft className="size-4" />
      </Button>
      <Button
        variant="outline"
        size="icon"
        aria-label={`Next ${ariaLabel}`}
        disabled={!nextId}
        onClick={() => {
          if (!nextId) return;
          if (onSelect) onSelect(nextId);
          else router.push(`${basePath}/${nextId}`);
        }}
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
