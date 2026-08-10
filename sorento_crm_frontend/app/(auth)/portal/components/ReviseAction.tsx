'use client';

import { PencilLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { PortalRevisionPolicy } from '../lib/portal-client';

/**
 * The Revise action, driven by ONE policy block.
 *
 * Rendered in two places (submission detail + the long-press preview card), so
 * the two can never disagree about whether a revision is possible: both read
 * the same `revision` block the backend puts on the submission.
 *
 * Allowed  -> the button plus the remaining budget.
 * Blocked  -> no button at all, and exactly one short sentence saying why.
 *             Never a disabled button with nothing next to it.
 */
export function ReviseAction({
  policy,
  onRevise,
  disabled,
  className,
}: {
  policy: PortalRevisionPolicy | null | undefined;
  onRevise: () => void;
  disabled?: boolean;
  className?: string;
}) {
  if (!policy) return null;

  if (!policy.allowed) {
    if (!policy.blocked_reason) return null;
    return (
      <p
        className={`text-sm text-muted-foreground break-words ${className ?? ''}`}
        data-testid="revise-blocked"
      >
        {policy.blocked_reason}
      </p>
    );
  }

  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1 ${className ?? ''}`}>
      <Button type="button" onClick={onRevise} disabled={disabled} className="h-10">
        <PencilLine className="h-4 w-4 mr-2" />
        Revise
      </Button>
      <span className="text-sm text-muted-foreground" data-testid="revise-remaining">
        {policy.remaining} of {policy.max} revisions left
      </span>
    </div>
  );
}
