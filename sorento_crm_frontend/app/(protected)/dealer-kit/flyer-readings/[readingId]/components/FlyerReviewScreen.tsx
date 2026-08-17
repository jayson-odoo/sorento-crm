'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AlertCircle, ArrowLeft, FileText, Loader2 } from 'lucide-react';

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { formatDateTimeInMalaysia } from '@/lib/helpers';

import { useBrochureImagePromotionOptions } from '../../../brochure-images/hooks/useBrochureImages';
import { PROMOTION_PAGE_SIZE } from '../../../services/brochureImageService';
import { MatchReportSections } from '../../components/MatchReportSections';
import { SeedPanel } from '../../components/SeedPanel';
import { useFlyerReadingQuery } from '../../hooks/useFlyerReadings';

/**
 * Step two of the journey: review what the system read, then seed.
 *
 * The promotion lives HERE rather than on the seed form, because it is a
 * question about the REPORT first - "which printed products does this offer not
 * carry" - and only afterwards a property of the brochure. Picking one refetches
 * the report against it, and the same choice is what the seed applies (PLAN D5:
 * explicit, never inferred; the click that approves the seed is the explicit
 * act).
 *
 * The reading may not have happened yet. A row exists from the moment the flyer
 * is handed over, so this screen opens on a read that is still running (it
 * waits, and fills itself in) or on one that failed (it says why). The report
 * sections, the sizes review and the seed panel appear only once the read is
 * done - the ADR's "always render every section" is about empty DATA, and a
 * report nobody has computed yet has no sections to be empty. The promotion
 * picker goes with them: it is a question about a report.
 */

/** What a promotion with no description of its own is called on screen. */
const UNTITLED = 'Untitled promotion';

function readableSize(bytes: number): string {
  if (bytes <= 0) return '';
  const mb = bytes / (1024 * 1024);
  return mb >= 1 ? `${mb.toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function FlyerReviewScreen({ readingId }: { readingId: string }) {
  const [promotionId, setPromotionId] = useState<string | null>(null);
  const { fetchOptions, optionFor } = useBrochureImagePromotionOptions();

  const { data, isLoading, isFetching, isError, error } = useFlyerReadingQuery(
    readingId,
    promotionId,
  );

  const selectedOption = promotionId
    ? optionFor(promotionId) ?? { value: promotionId, label: UNTITLED }
    : undefined;
  // Never the id: the whole point of holding the option is that the trigger and
  // every sentence below it can name the promotion.
  const promotionLabel = promotionId ? selectedOption?.label ?? UNTITLED : null;

  if (isError) {
    return (
      <Alert variant="destructive" data-testid="dk-fr-error">
        <AlertCircle className="size-4" />
        <AlertTitle>Could not open this flyer reading</AlertTitle>
        <AlertDescription className="flex flex-col items-start gap-3">
          <span>{error instanceof Error ? error.message : 'Something went wrong. Try again.'}</span>
          <Button variant="outline" size="sm" asChild>
            <Link href="/dealer-kit/flyer-readings">Back to flyers</Link>
          </Button>
        </AlertDescription>
      </Alert>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="flex flex-col gap-4" data-testid="dk-fr-loading">
        <Skeleton className="h-8 w-64" />
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[0, 1, 2, 3].map((index) => (
            <Skeleton key={index} className="h-16 w-full" />
          ))}
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  const isDone = data.status === 'done';
  // The counts are what the reader found, so they mean nothing until it has
  // read: 0 pages and 0 codes on a flyer being read right now is a figure that
  // looks like an answer.
  const facts = [
    isDone ? `${data.pageCount} page${data.pageCount === 1 ? '' : 's'}` : null,
    isDone ? `${data.codeCount} product code${data.codeCount === 1 ? '' : 's'}` : null,
    readableSize(data.byteSize) || null,
  ].filter(Boolean);
  const readAt = data.uploadedAt
    ? `${isDone ? 'read' : 'added'} ${formatDateTimeInMalaysia(data.uploadedAt)}`
    : '';
  // Joined rather than concatenated: a library flyer whose recorded size is 0
  // has no facts yet, and a line that opened with a stray separator would look
  // like something failed to load.
  const metaLine = [facts.join(', '), readAt].filter(Boolean).join(' · ');

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-3">
        <Button variant="ghost" size="sm" className="w-fit -ms-2" asChild>
          <Link href="/dealer-kit/flyer-readings">
            <ArrowLeft className="size-4" />
            All flyers
          </Link>
        </Button>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-2">
            <FileText className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
            <div className="min-w-0">
              <h1 className="min-w-0 break-words text-lg font-semibold" data-testid="dk-fr-filename">
                {data.filename}
              </h1>
              <p className="text-sm text-muted-foreground">{metaLine}</p>
              {isDone && isFetching && (
                // The report is derived, not stored, so it is recomputed every
                // time it is asked for. Saying so is the difference between a
                // figure that is a moment old and one that looks frozen.
                <p className="text-xs text-muted-foreground" data-testid="dk-fr-recomputing">
                  Matching against the product master
                </p>
              )}
            </div>
          </div>

          {isDone && (
            <div className="flex min-w-0 items-center gap-2">
              <span className="shrink-0 text-xs text-muted-foreground">Prices from</span>
              <SearchableSelect
                id="dk-fr-promotion"
                size="sm"
                value={promotionId ?? ''}
                onChange={(value) => setPromotionId(value || null)}
                // Server-searched and paged: there are hundreds of promotions, so
                // a static list would cap this at one page and hide the rest.
                fetchOptions={fetchOptions}
                paginated
                pageSize={PROMOTION_PAGE_SIZE}
                selectedOption={selectedOption}
                placeholder="List prices only"
                clearable
                triggerClassName="w-56"
              />
            </div>
          )}
        </div>
      </div>

      {data.status === 'processing' && (
        // The query polls itself while this is on screen, so the report takes
        // over without anybody reloading anything.
        <div
          className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-10 text-center"
          data-testid="dk-fr-review-processing"
        >
          <Loader2 className="size-6 animate-spin text-muted-foreground" />
          <p className="text-sm font-medium text-foreground">Reading this flyer</p>
          <p className="max-w-md text-sm text-muted-foreground">
            The report appears here when it is done.
          </p>
        </div>
      )}

      {data.status === 'failed' && (
        <Alert variant="destructive" data-testid="dk-fr-review-failed">
          <AlertCircle className="size-4" />
          <AlertTitle>This flyer could not be read</AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-3">
            {/* The words the read itself used. A generic message here would send
                somebody hunting for a cause the row already knows. */}
            <span>{data.errorMessage || 'The read did not finish, and no reason was recorded.'}</span>
            <Button variant="outline" size="sm" asChild>
              <Link href="/dealer-kit/flyer-readings">Read another flyer</Link>
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {isDone && (
        <>
          <MatchReportSections
            readingId={data.id}
            report={data.report}
            codeCount={data.codeCount}
            promotionLabel={promotionLabel}
            headings={data.headings}
          />

          <SeedPanel
            readingId={data.id}
            filename={data.filename}
            unmatched={data.report.unmatched}
            matchedCount={data.report.matched.length}
            promotionId={promotionId}
            promotionLabel={promotionLabel}
          />
        </>
      )}
    </div>
  );
}
