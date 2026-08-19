'use client';

import * as React from 'react';
import { AlertTriangle, FileWarning, Loader2, RefreshCw, Upload } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Skeleton } from '@/components/ui/skeleton';
import type { POVersion } from '../../_shared/types/poIntake.types';
import { describeWaitingFor } from '../../_shared/lib/readingTime';

/** The skeleton matches the screen it becomes: viewer left, header and lines right. */
export function POIntakeSkeleton() {
  return (
    <div className="space-y-4">
      <Skeleton className="h-16 w-full" />
      <div className="flex flex-col gap-4 lg:flex-row">
        <Skeleton className="h-[45vh] w-full lg:h-[60vh] lg:w-2/5" />
        <div className="w-full space-y-3 lg:w-3/5">
          <Skeleton className="h-28 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </div>
    </div>
  );
}

/**
 * Extraction is on a queue, so this says where it is rather than blocking the screen. The
 * bar is deliberately indeterminate on `queued`: we know the page count, not the progress,
 * and a fake percentage is a lie about a two minute wait.
 */
export function POIntakeExtractionProgress({ version }: { version: POVersion }) {
  const running = version.extraction_state === 'running';
  const waitingFor = describeWaitingFor(version.extraction_started_at);
  const read = version.pages_extracted;
  const total = version.page_count;
  // Pages land as they finish (the reader runs several at once), so this counts up
  // while running rather than sitting still until the whole document is done.
  const pageDetail =
    running && typeof read === 'number' && typeof total === 'number' && total > 0
      ? `Page ${Math.min(read + 1, total)} of ${total}`
      : total
        ? `${total} page${total === 1 ? '' : 's'}`
        : null;
  return (
    <Card>
      <CardHeader className="block">
        <div className="flex flex-wrap items-center gap-2">
          <Loader2 className="size-4 animate-spin text-muted-foreground" aria-hidden />
          <p className="text-sm font-medium">
            {running ? 'Reading the document' : 'Waiting to be read'}
          </p>
          {pageDetail ? (
            <span className="text-xs text-muted-foreground">{pageDetail}</span>
          ) : null}
          {waitingFor ? (
            <span className="text-xs text-muted-foreground">{waitingFor}</span>
          ) : null}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <Progress value={running ? 60 : 15} className="h-1.5" />
        <p className="text-xs text-muted-foreground">
          This page updates itself. You can leave it and come back.
        </p>
        <div className="space-y-2 pt-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * Two ways out, and which one leads is deliberate.
 *
 * A read can end for two quite different reasons, and the answer is different each time.
 * If the reader was stopped part-way, the document was never the problem and reading it
 * again on the same version is the whole fix: same version number, same stored file, same
 * history. If the document really could not be read, a better scan is the fix. Retry
 * therefore leads and re-upload stays as the secondary action.
 */
export function POIntakeExtractionFailed({
  version,
  onReupload,
  onRetry,
  isRetrying = false,
}: {
  version: POVersion;
  onReupload?: () => void;
  onRetry?: () => void;
  isRetrying?: boolean;
}) {
  return (
    <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
      <FileWarning className="mx-auto size-6 text-destructive" aria-hidden />
      <h3 className="mt-2 text-sm font-semibold text-destructive">
        This document could not be read
      </h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground break-words">
        {version.extraction_error ||
          'Nothing was extracted. A sharper scan, or the pages as separate images, usually reads.'}
      </p>
      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        {onRetry && (
          <Button type="button" disabled={isRetrying} onClick={onRetry}>
            <RefreshCw
              className={`size-4 ${isRetrying ? 'animate-spin' : ''}`}
              aria-hidden
            />
            {isRetrying ? 'Starting…' : 'Read it again'}
          </Button>
        )}
        {onReupload && (
          <Button
            type="button"
            variant={onRetry ? 'outline' : 'primary'}
            onClick={onReupload}
          >
            <Upload className="size-4" aria-hidden />
            Upload it again
          </Button>
        )}
      </div>
    </div>
  );
}

/**
 * A short read is NOT a success. It is stated above everything else, with the pages named,
 * because the lines that did come back look perfectly healthy on their own.
 */
export function POIntakePartialBanner({
  version,
  onReupload,
}: {
  version: POVersion;
  onReupload?: () => void;
}) {
  const failed = version.failed_pages ?? [];
  const read = version.pages_extracted;
  const total = version.page_count;
  const headline =
    read != null && total != null
      ? `Only ${read} of ${total} pages were read`
      : 'Some of this document was not read';

  return (
    <div className="flex flex-col gap-2 rounded-lg border border-amber-500/50 bg-amber-50 px-4 py-3 text-amber-900 sm:flex-row sm:items-start sm:justify-between dark:bg-amber-950/30 dark:text-amber-300">
      <div className="flex min-w-0 gap-2">
        <AlertTriangle className="size-4 shrink-0" aria-hidden />
        <div className="min-w-0 break-words">
          <p className="text-sm font-semibold">{headline}</p>
          <p className="mt-0.5 text-xs">
            {failed.length > 0
              ? `Pages ${failed.join(', ')} produced nothing. The lines below are only what the readable pages contained.`
              : 'The lines below are only what the readable pages contained.'}
          </p>
          {version.extraction_error && (
            <p className="mt-0.5 text-xs opacity-90 break-words">
              {version.extraction_error}
            </p>
          )}
        </div>
      </div>
      {onReupload && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={onReupload}
        >
          <Upload className="size-3.5" aria-hidden />
          Upload a better scan
        </Button>
      )}
    </div>
  );
}

export function POIntakeNoLines({ onReupload }: { onReupload?: () => void }) {
  return (
    <div className="rounded-lg border border-dashed border-border px-6 py-10 text-center">
      <h3 className="text-sm font-semibold">No lines came back from this document</h3>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
        Nothing can be confirmed from an empty read. Upload a sharper scan, or record the
        PO by hand from the POs tab.
      </p>
      {onReupload && (
        <Button type="button" className="mt-4" onClick={onReupload}>
          <Upload className="size-4" aria-hidden />
          Upload it again
        </Button>
      )}
    </div>
  );
}
