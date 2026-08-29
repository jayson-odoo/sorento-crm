'use client';

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import ListPager, { type ListPagerProps } from './ListPager';
import { DetailActionsMenu } from './DetailActionsMenu';
import type { RecordAction } from './recordActions';

export interface DetailActionsProps {
  /** Prev/next across the list page the record was opened from. */
  pager?: ListPagerProps;
  /**
   * The entity's action set (D15) - the same array the list row's "..." renders.
   * Secondary items first, then a separator, then Delete in red, last.
   */
  actions?: RecordAction[];
  /** The one primary button (Edit ...). */
  primary?: ReactNode;
  /** Dialogs the actions need mounted, from `use<Entity>Actions`. */
  dialogs?: ReactNode;
  gearLabel?: string;
  className?: string;
}

/**
 * The action group on a detail page's record card (D6, S3-02).
 *
 * Reads left to right: pager, gear, primary. Nothing else goes here, and nothing
 * of this goes on the toolbar row - that row carries the title, the breadcrumb
 * and one Back (`BackToList`).
 *
 * The caller's header is `flex flex-col gap-3 sm:flex-row sm:items-start
 * sm:justify-between`, so at 375 this group wraps under the record's identity
 * instead of squeezing beside it.
 */
export default function DetailActions({
  pager,
  actions,
  primary,
  dialogs,
  gearLabel = 'Actions',
  className,
}: DetailActionsProps) {
  return (
    <div className={cn('flex flex-wrap items-center justify-end gap-2', className)}>
      {pager && <ListPager {...pager} />}
      {actions && actions.length > 0 && (
        <DetailActionsMenu actions={actions} trigger="gear" ariaLabel={gearLabel} />
      )}
      {primary}
      {dialogs}
    </div>
  );
}
