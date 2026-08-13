'use client';

import { PencilLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import type { PortalRevisionPolicy } from '../lib/portal-client';

/**
 * The Revise action, driven by ONE policy block.
 *
 * Rendered in two places (submission detail + the long-press preview card), so
 * the two can never disagree about whether a revision is possible: both read
 * the same `revision` block the backend puts on the submission.
 *
 * Allowed  -> the action plus the remaining budget.
 * Blocked  -> no action at all, and exactly one short sentence saying why.
 *             Never a disabled button with nothing next to it.
 *
 * Two presentations of that same policy (round 6):
 *
 * `inline` (default) is the original prominent button + budget row. The
 * long-press preview dialog uses it, where the action IS the point of the card
 * and a gear tucked in a corner would read as decoration.
 *
 * `menu` is the submission detail page: budget text then a gear, both pushed
 * right. Revise is one thing the contact can do to a submission they came to
 * read, so it sits where the office detail pages put record actions instead of
 * being the loudest thing above the form.
 */
export function ReviseAction({
  policy,
  onRevise,
  disabled,
  className,
  variant = 'inline',
}: {
  policy: PortalRevisionPolicy | null | undefined;
  onRevise: () => void;
  disabled?: boolean;
  className?: string;
  variant?: 'inline' | 'menu';
}) {
  if (!policy) return null;

  const asMenu = variant === 'menu';

  if (!policy.allowed) {
    if (!policy.blocked_reason) return null;
    return (
      <p
        className={`text-sm text-muted-foreground break-words ${
          asMenu ? 'text-right' : ''
        } ${className ?? ''}`}
        data-testid="revise-blocked"
      >
        {policy.blocked_reason}
      </p>
    );
  }

  const remaining = (
    <span className="text-sm text-muted-foreground" data-testid="revise-remaining">
      {policy.remaining} of {policy.max} revisions left
    </span>
  );

  if (asMenu) {
    return (
      <div
        className={`flex flex-wrap items-center justify-end gap-x-3 gap-y-1 ${
          className ?? ''
        }`}
      >
        {remaining}
        {/* 44px square: the portal is a phone surface, and the shared gear's
            default 34px is under the touch minimum. `size-11` (not `h-11 w-11`)
            so tailwind-merge actually drops the variant's own `size-8.5` -
            `h`/`w` do not displace a `size`, they just race it in the cascade. */}
        <DetailActionsMenu ariaLabel="Submission actions" className="size-11">
          <DropdownMenuItem disabled={disabled} onSelect={() => onRevise()}>
            <PencilLine className="size-4" />
            Revise
          </DropdownMenuItem>
        </DetailActionsMenu>
      </div>
    );
  }

  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 ${className ?? ''}`}>
      <Button type="button" onClick={onRevise} disabled={disabled} className="h-10">
        <PencilLine className="h-4 w-4 mr-2" />
        Revise
      </Button>
      {remaining}
    </div>
  );
}
