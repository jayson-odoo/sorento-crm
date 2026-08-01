'use client';

import * as React from 'react';
import Link from 'next/link';
import { FileText, Upload } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { formatDateTimeInMalaysia } from '@/lib/helpers';
import { usePOVersions } from '../../_shared/hooks/usePOIntake';
import type { POExtractionState } from '../../_shared/types/poIntake.types';

const STATE_LABELS: Record<POExtractionState, string> = {
  queued: 'Waiting to be read',
  running: 'Being read',
  done: 'Read',
  failed: 'Could not be read',
};

/**
 * The uploaded documents behind one PO row, so a half finished review can be re-entered
 * instead of re-uploaded.
 *
 * When the backend has no version list endpoint yet the hook resolves to `null` and this
 * renders NOTHING: printing "no documents" for an endpoint that does not exist would be a
 * confident wrong answer, and the upload button beside it is already the way forward.
 */
export function POIntakeVersionsStrip({
  projectId,
  poId,
  canEdit,
  onUpload,
}: {
  projectId: string;
  poId: string;
  canEdit: boolean;
  onUpload: () => void;
}) {
  const versions = usePOVersions(poId);

  if (versions.isLoading) {
    return <Skeleton className="h-9 w-full" />;
  }

  if (versions.isError || versions.data === null || versions.data === undefined) {
    return null;
  }

  if (versions.data.length === 0) {
    return (
      <div className="flex flex-col gap-2 rounded-md border border-dashed border-border px-3 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="min-w-0 text-xs text-muted-foreground">
          No scan of this PO has been uploaded.
        </p>
        {canEdit && (
          <Button type="button" variant="outline" size="sm" onClick={onUpload}>
            <Upload className="size-3.5" aria-hidden />
            Upload the document
          </Button>
        )}
      </div>
    );
  }

  return (
    <ul className="space-y-1.5">
      {[...versions.data]
        .sort((a, b) => b.version_no - a.version_no)
        .map((version) => (
          <li
            key={version.id}
            className="flex flex-col gap-1.5 rounded-md border border-border px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
          >
            <span className="flex min-w-0 flex-wrap items-center gap-2 text-xs">
              <FileText className="size-3.5 shrink-0 text-muted-foreground" aria-hidden />
              <span className="font-medium">{`Version ${version.version_no}`}</span>
              {version.extraction_state && (
                <Badge
                  variant={
                    version.extraction_state === 'failed'
                      ? 'destructive'
                      : version.extraction_state === 'done'
                        ? 'secondary'
                        : 'warning'
                  }
                  className="text-[11px]"
                >
                  {STATE_LABELS[version.extraction_state]}
                </Badge>
              )}
              {version.confirmed_at ? (
                <span className="text-muted-foreground">
                  {`Confirmed ${formatDateTimeInMalaysia(version.confirmed_at)}`}
                </span>
              ) : (
                <span className="text-muted-foreground">Not confirmed</span>
              )}
            </span>
            <Button asChild variant="outline" size="sm" className="shrink-0">
              <Link href={`/project-sales/${projectId}/purchase-orders/${version.id}`}>
                {version.confirmed_at ? 'Open' : 'Review what we read'}
              </Link>
            </Button>
          </li>
        ))}
    </ul>
  );
}
