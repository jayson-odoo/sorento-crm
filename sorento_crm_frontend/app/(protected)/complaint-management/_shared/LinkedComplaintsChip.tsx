'use client';

/**
 * LinkedComplaintsChip - the "Complaints" count cell on the Root Causes /
 * Resolutions lists, clickable to peek at the linked complaints without leaving
 * the list. The dialog body is the same `LinkedComplaintsPanel` the detail page
 * renders, so the two surfaces can never show different columns or links.
 *
 * The count comes from the row (`complaint_count`), so the query only runs when
 * the dialog is opened.
 */

import { useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

import { LinkedComplaintsPanel } from './LinkedComplaintsPanel';

export interface LinkedComplaintsChipProps {
  /** Exactly one of these is set. */
  rootCauseId?: string;
  resolutionId?: string;
  /** Human-readable name of the root cause / resolution, for the dialog title. */
  label?: string;
  count: number;
  /** Deep link to the full detail page, offered from inside the dialog. */
  detailHref: string;
}

export function LinkedComplaintsChip({
  rootCauseId,
  resolutionId,
  label,
  count,
  detailHref,
}: LinkedComplaintsChipProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={(e) => {
          // The row itself navigates to the detail page; the chip must not.
          e.stopPropagation();
          setOpen(true);
        }}
        title={
          count > 0 ? 'View the complaints linked to this' : 'No complaints linked yet'
        }
        className="w-fit rounded-md transition-colors hover:bg-muted"
      >
        <Badge variant="secondary" size="sm" className="shrink-0 w-fit cursor-pointer">
          {count}
        </Badge>
      </button>

      <Dialog open={open} onOpenChange={setOpen} modal>
        <DialogContent
          className="max-w-3xl"
          onClick={(e) => e.stopPropagation()}
        >
          <DialogHeader>
            <DialogTitle className="text-base">
              Linked complaints{label ? ` · ${label}` : ''}
            </DialogTitle>
          </DialogHeader>
          <DialogBody className="space-y-3">
            <LinkedComplaintsPanel
              rootCauseId={rootCauseId}
              resolutionId={resolutionId}
              maxHeightClassName="max-h-[50vh]"
            />
            <Link
              href={detailHref}
              className="inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
            >
              Open full details
              <ArrowUpRight className="size-3.5" />
            </Link>
          </DialogBody>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default LinkedComplaintsChip;
