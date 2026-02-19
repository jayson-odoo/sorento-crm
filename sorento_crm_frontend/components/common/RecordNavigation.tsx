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
  /** Optional: show "current / total" when both provided (no circular when using ids) */
  currentIndex?: number;
  totalCount?: number;
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
  /** When true (default), navigation wraps: next on last goes to first, previous on first goes to last */
  circular?: boolean;
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
 * With list mode: shows "current / total" and circular scrolling (next on last → first, previous on first → last).
 */
export default function RecordNavigation(props: RecordNavigationProps) {
  const router = useRouter();
  const { basePath, ariaLabel = 'record', className, onSelect } = props;

  const { previousId, nextId, currentIndex, totalCount } = useMemo(() => {
    if (isIdsProps(props)) {
      const total =
        props.totalCount != null && props.currentIndex != null
          ? props.totalCount
          : null;
      const current =
        props.currentIndex != null ? props.currentIndex + 1 : null;
      return {
        previousId: props.prevId,
        nextId: props.nextId,
        currentIndex: current,
        totalCount: total,
      };
    }
    const { currentId, items, circular = true } = props;
    const total = items.length;
    const idx = items.findIndex((item) => item.id === currentId);
    const currentOneBased = idx >= 0 ? idx + 1 : 0;

    let previousId: string | null;
    let nextId: string | null;
    if (total === 0) {
      previousId = null;
      nextId = null;
    } else if (circular) {
      previousId =
        idx <= 0 ? items[total - 1].id : items[idx - 1].id;
      nextId =
        idx < 0 || idx >= total - 1 ? items[0].id : items[idx + 1].id;
    } else {
      previousId = idx > 0 ? items[idx - 1].id : null;
      nextId =
        idx >= 0 && idx < total - 1 ? items[idx + 1].id : null;
    }

    return {
      previousId,
      nextId,
      currentIndex: currentOneBased,
      totalCount: total,
    };
  }, [props]);

  const showCounter =
    totalCount != null && totalCount > 0 && currentIndex != null;
  const counterLabel = showCounter ? `${currentIndex} / ${totalCount}` : null;

  const handleNavigate = (id: string) => {
    if (onSelect) onSelect(id);
    else router.push(`${basePath}/${id}`);
  };

  return (
    <div
      className={['flex items-center gap-2', className].filter(Boolean).join(' ')}
      aria-label={`${ariaLabel} navigation`}
    >
      <Button
        variant="outline"
        size="icon"
        aria-label={`Previous ${ariaLabel}`}
        disabled={!previousId}
        onClick={() => previousId && handleNavigate(previousId)}
      >
        <ChevronLeft className="size-4" />
      </Button>
      {showCounter && (
        <span
          className="min-w-[3rem] text-center text-sm text-muted-foreground tabular-nums"
          aria-label={`${currentIndex} of ${totalCount} records`}
        >
          {counterLabel}
        </span>
      )}
      <Button
        variant="outline"
        size="icon"
        aria-label={`Next ${ariaLabel}`}
        disabled={!nextId}
        onClick={() => nextId && handleNavigate(nextId)}
      >
        <ChevronRight className="size-4" />
      </Button>
    </div>
  );
}
