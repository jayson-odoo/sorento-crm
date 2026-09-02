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
   * The two records whose whole list is already in memory (a project's delivery
   * schedules, the series list) step through it without a query of their own, so
   * they hand over a presentational `RecordNavigation` instead. Same slot, same
   * position; `pager` and `pagerNode` are exclusive.
   */
  pagerNode?: ReactNode;
  /**
   * The entity's action set (D15) - the same array the list row's "..." renders.
   * Secondary items first, then a separator, then Delete in red, last.
   */
  actions?: RecordAction[];
  /**
   * The entity's own menu, for the records whose secondary actions are a
   * WORKFLOW rather than a record action set (complaints, purchase requests,
   * stock inquiries, the project-sales clients): conditional groups, labels,
   * server-driven eligibility, their own dialogs. Those menus keep their shape
   * and only move into the gear slot; `actions` and `gear` are exclusive.
   */
  gear?: ReactNode;
  /** The one primary button (Edit ...). */
  primary?: ReactNode;
  /**
   * The countdown of an action parked on this record (D7, S6-06).
   *
   * It stands WHERE the primary button stands, and while it is there the primary
   * button is not: a record on its way out has one thing to offer, and that is
   * Cancel. `useDeferredAction` hands this back as `countdown`, null when nothing
   * is parked, so the caller passes it straight through.
   */
  pendingAction?: ReactNode;
  /** Dialogs the actions need mounted, from `use<Entity>Actions`. */
  dialogs?: ReactNode;
  gearLabel?: string;
  className?: string;
  /**
   * Disables the gear trigger while staying mounted (the pager's own `disabled`
   * travels with `pagerNode`/`pager` instead, since `DetailActions` does not
   * build that element).
   */
  disabled?: boolean;
  /** For the two clients whose tests read the whole action group as one node. */
  'data-testid'?: string;
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
  pagerNode,
  actions,
  gear,
  primary,
  pendingAction,
  dialogs,
  gearLabel = 'Actions',
  className,
  disabled,
  'data-testid': testId,
}: DetailActionsProps) {
  return (
    <div
      data-testid={testId}
      className={cn('flex flex-wrap items-center justify-end gap-2', className)}
    >
      {pager && <ListPager {...pager} />}
      {!pager && pagerNode}
      {actions && actions.length > 0 && (
        <DetailActionsMenu
          actions={actions}
          trigger="gear"
          ariaLabel={gearLabel}
          disabled={disabled}
        />
      )}
      {!actions && gear}
      {pendingAction ?? primary}
      {dialogs}
    </div>
  );
}
