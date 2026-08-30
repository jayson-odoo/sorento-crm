'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { AlertTriangle, Copy, Heading, SearchX, Tag } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import type {
  FlyerReadingStatus,
  MatchReport,
  MatchedCode,
  PageHeading,
  UnmatchedCode,
} from '../../services/flyerReadingService';
import { DimensionReviewSection } from './DimensionReviewSection';
import { SpecProposalSection } from './SpecProposalSection';
import { Empty, Section, printedOn } from './ReportSection';
import { ReportGrid } from './ReportGrid';

/**
 * What the system read, said plainly.
 *
 * This is the honest step, and the reason the slice exists. A designer is about
 * to turn 36 pages of finished artwork into a brochure without retyping 998
 * product codes, and the only question worth answering first is what the reader
 * got WRONG. So nothing here is a reassurance:
 *
 * - Unmatched codes are named as products the brochure will not contain, before
 *   the seed rather than after it.
 * - Sizes can now be applied to the product master, one ticked row at a time
 *   and never as a side effect of reading the flyer (S7.6). That section owns
 *   its own mutation and lives in `DimensionReviewSection`.
 * - Specifications work the same way one step removed: the flyer is READ for
 *   them here and reviewed in Master Data, because a batch spanning two hundred
 *   products is not something to judge on a page about one flyer.
 * - Every section renders even when it is empty, because "no promotion gaps" is
 *   an answer somebody needs, and a section that vanishes on zero looks like a
 *   section that failed to load.
 */

function Figure({
  label,
  value,
  tone = 'plain',
  testId,
}: {
  label: string;
  value: number;
  tone?: 'plain' | 'warn';
  testId: string;
}) {
  return (
    <div className="rounded-lg border border-border px-3 py-2">
      {/* The id sits on the FIGURE, not the card: a reader of this element - a
          test, or anything else - wants the number, and the number beside its
          label reads as a number that is not a number. */}
      <p
        data-testid={testId}
        className={
          tone === 'warn'
            ? 'text-xl font-semibold text-amber-600'
            : 'text-xl font-semibold text-foreground'
        }
      >
        {value}
      </p>
      <p className="mt-0.5 text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

export interface MatchReportSectionsProps {
  /** The reading these candidates came off, for the one section that acts. */
  readingId: string;
  report: MatchReport;
  /** How many codes were printed at all, from the reading rather than the report. */
  codeCount: number;
  /** The promotion the report was computed against, by NAME. Never an id. */
  promotionLabel: string | null;
  /**
   * What the reader called each page. Off the reading, not the report - see the
   * service docblock. Shown WRONG values and all: this section exists so the
   * misreads are visible before the seed rather than found in the builder after
   * it.
   */
  headings: PageHeading[];
  /**
   * Where the READING got to. Optional and `done` by default, because today the
   * only caller renders this whole component once the read has finished and the
   * existing tests pass no such prop - but the spec section below has to be able
   * to say "read the flyer first" rather than offer a button that cannot work.
   */
  readingStatus?: FlyerReadingStatus;
}

export function MatchReportSections({
  readingId,
  report,
  codeCount,
  promotionLabel,
  headings,
  readingStatus = 'done',
}: MatchReportSectionsProps) {
  const duplicateRows = useMemo(
    () =>
      Object.entries(report.duplicates).map(([code, pages]) => ({
        code,
        pages: pages ?? [],
      })),
    [report.duplicates],
  );

  const unmatchedColumns = useMemo<ColumnDef<UnmatchedCode>[]>(
    () => [
      {
        accessorKey: 'code',
        header: 'Printed code',
        cell: ({ row }) => (
          <div className="truncate font-mono text-sm" title={row.original.code}>
            {row.original.code}
          </div>
        ),
        size: 180,
        minSize: 120,
        meta: { headerTitle: 'Printed code' },
      },
      {
        id: 'pages',
        header: 'Printed on',
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">{printedOn(row.original.pages)}</span>
        ),
        size: 130,
        minSize: 100,
        meta: { headerTitle: 'Printed on' },
      },
      {
        id: 'suggestion',
        header: 'Nearest existing code',
        cell: ({ row }) => {
          const suggestion = row.original.suggestion;
          if (!suggestion) {
            return (
              <span className="text-sm text-muted-foreground">
                Nothing close enough to suggest
              </span>
            );
          }
          // Plenty of products are named after their own code, and printing
          // "SRTWC8066 SRTWC8066" reads as a rendering fault rather than as a
          // product whose name is its code.
          const named =
            suggestion.productName.trim() &&
            suggestion.productName.trim() !== suggestion.productCode.trim()
              ? suggestion.productName.trim()
              : null;
          const label = named ? `${suggestion.productCode} - ${named}` : suggestion.productCode;
          return (
            <div className="flex min-w-0 items-center gap-2">
              <span className="truncate text-sm" title={label}>
                <span className="font-mono">{suggestion.productCode}</span>
                {named && <span className="text-muted-foreground"> {named}</span>}
              </span>
              <Badge variant="outline" className="shrink-0 font-normal">
                {Math.round(suggestion.similarity * 100)}% alike
              </Badge>
            </div>
          );
        },
        size: 380,
        minSize: 200,
        meta: { headerTitle: 'Nearest existing code' },
      },
    ],
    [],
  );

  const notPromotedColumns = useMemo<ColumnDef<MatchedCode>[]>(
    () => [
      {
        accessorKey: 'code',
        header: 'Printed code',
        cell: ({ row }) => (
          <div className="truncate font-mono text-sm" title={row.original.code}>
            {row.original.code}
          </div>
        ),
        size: 180,
        minSize: 120,
        meta: { headerTitle: 'Printed code' },
      },
      {
        accessorKey: 'productName',
        header: 'Product',
        cell: ({ row }) => (
          <div className="truncate text-sm" title={row.original.productName}>
            {row.original.productName}
          </div>
        ),
        size: 380,
        minSize: 200,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'pages',
        header: 'Printed on',
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">{printedOn(row.original.pages)}</span>
        ),
        size: 130,
        minSize: 100,
        meta: { headerTitle: 'Printed on' },
      },
    ],
    [],
  );

  const duplicateColumns = useMemo<ColumnDef<{ code: string; pages: number[] }>[]>(
    () => [
      {
        accessorKey: 'code',
        header: 'Printed code',
        cell: ({ row }) => (
          <div className="truncate font-mono text-sm" title={row.original.code}>
            {row.original.code}
          </div>
        ),
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Printed code' },
      },
      {
        id: 'pages',
        header: 'Printed on',
        cell: ({ row }) => (
          <span className="truncate text-sm text-muted-foreground" title={printedOn(row.original.pages)}>
            {printedOn(row.original.pages)}
          </span>
        ),
        size: 240,
        minSize: 120,
        meta: { headerTitle: 'Printed on' },
      },
    ],
    [],
  );

  const headingColumns = useMemo<ColumnDef<PageHeading>[]>(
    () => [
      {
        accessorKey: 'page',
        header: 'Flyer page',
        cell: ({ row }) => (
          <span className="text-sm text-muted-foreground">Page {row.original.page}</span>
        ),
        size: 140,
        minSize: 90,
        meta: { headerTitle: 'Flyer page' },
      },
      {
        id: 'text',
        header: 'Section will be called',
        cell: ({ row }) =>
          row.original.text ? (
            <div className="truncate text-sm text-foreground" title={row.original.text}>
              {row.original.text}
            </div>
          ) : (
            // Not an em dash and not a blank cell: a blank reads as a render
            // that failed, and the reviewer needs to know the seed will fall
            // back to the page number rather than leave the section unnamed.
            <span className="text-sm text-amber-600">
              No heading found - the section will be named after its page
            </span>
          ),
        size: 420,
        minSize: 200,
        meta: { headerTitle: 'Section will be called' },
      },
    ],
    [],
  );

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3" data-dk-fr-section="summary">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Figure testId="dk-fr-figure-printed" label="Codes printed" value={codeCount} />
          <Figure
            testId="dk-fr-figure-matched"
            label="Matched to a product"
            value={report.matched.length}
          />
          <Figure
            testId="dk-fr-figure-unmatched"
            label="Not in the product master"
            value={report.unmatched.length}
            tone={report.unmatched.length > 0 ? 'warn' : 'plain'}
          />
          <Figure
            testId="dk-fr-figure-duplicates"
            label="Printed more than once"
            value={duplicateRows.length}
          />
        </div>

        {report.unmatched.length > 0 && (
          <div
            className="flex items-start gap-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200"
            data-testid="dk-fr-unmatched-warning"
          >
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <p>
              {report.unmatched.length} of {codeCount} printed codes are not in the product
              master. They will <strong>not</strong> be in the brochure. Create the products
              first if the flyer is right, or leave the gap and correct the flyer.
            </p>
          </div>
        )}
      </section>

      <Section
        id="unmatched"
        icon={<SearchX className="size-4" />}
        title="Codes the product master does not have"
        description="These will not be in the brochure. Suggestions are never applied for you."
      >
        <ReportGrid
          data-testid="dk-fr-unmatched-grid"
          columns={unmatchedColumns}
          rows={report.unmatched}
          getRowId={(row) => row.code}
          emptyMessage={
            <Empty title="Every printed code resolved to a product">
              Nothing will be dropped from the brochure.
            </Empty>
          }
        />
      </Section>

      <Section
        id="not-promoted"
        icon={<Tag className="size-4" />}
        title="Printed, but not in this promotion"
        description={
          promotionLabel ? (
            <>
              These products show their list price to every reader, because{' '}
              <strong>{promotionLabel}</strong> has no row for them.
            </>
          ) : (
            'Choose the promotion that prices this flyer to see which printed products it does not carry.'
          )
        }
      >
        <ReportGrid
          data-testid="dk-fr-not-promoted-grid"
          columns={notPromotedColumns}
          rows={report.notPromoted}
          getRowId={(row) => row.code}
          emptyMessage={
            promotionLabel ? (
              <Empty title="This promotion carries every printed product">
                Every product on the flyer resolves an offer price for the audiences the
                promotion covers.
              </Empty>
            ) : (
              <Empty tone="neutral" title="No promotion chosen">
                Pick one above and this list fills with the printed products it does not price.
                With no promotion the brochure shows list prices to everybody, which is a
                finished answer rather than a missing one.
              </Empty>
            )
          }
        />
      </Section>

      {/* The only section that writes anything, so it owns its own mutation,
          its own confirmation and its own result. */}
      <DimensionReviewSection
        readingId={readingId}
        candidates={report.dimensionCandidates}
      />

      {/* Beside the sizes, and for the same reason: both are the flyer telling
          the product master something it may not know. */}
      <SpecProposalSection readingId={readingId} readingStatus={readingStatus} />

      <Section
        id="duplicates"
        icon={<Copy className="size-4" />}
        title="Printed on more than one page"
        description="Seeded once per page, exactly as the flyer prints it."
      >
        <ReportGrid
          data-testid="dk-fr-duplicates-grid"
          columns={duplicateColumns}
          rows={duplicateRows}
          getRowId={(row) => row.code}
          emptyMessage={
            <Empty title="Every code appears on one page only">
              Nothing to check twice.
            </Empty>
          }
        />
      </Section>

      <Section
        id="headings"
        icon={<Heading className="size-4" />}
        title="What each page will be called"
        description="Guessed from the page. Check them against the paper."
      >
        <ReportGrid
          columns={headingColumns}
          rows={headings}
          getRowId={(row) => String(row.page)}
          data-testid="dk-fr-headings"
          emptyMessage={
            <Empty tone="neutral" title="No pages were read">
              This reading has no pages, which means the upload produced nothing to review.
            </Empty>
          }
        />
      </Section>

      {/* Was four bullets and about a hundred words explaining how the
          extractor works - a feature explanation inside the UI, which the
          repo's own cursor rules ban. The WARNING does real work (a reviewer
          should know the draft needs corrections before they seed it), so it
          stays; the lesson on heuristics does not. The detail moved to the
          user guide, where the assistant can serve it on demand. */}
      <Section
        id="known-gaps"
        icon={<AlertTriangle className="size-4" />}
        title="The draft will need corrections"
        description="Known, and expected."
        action={
          <Button variant="outline" size="sm" asChild>
            <Link href="/dealer-kit/brochure-images">Choose brochure photos</Link>
          </Button>
        }
      >
        <p
          className="rounded-lg border border-border px-4 py-3 text-sm text-muted-foreground"
          data-testid="dk-fr-known-gaps"
        >
          Headings are guessed, tiles have no photo until one is chosen, and some printed rows
          split in two. Reading a flyer changes no product: sizes reach the master only for the
          rows you tick.
        </p>
      </Section>
    </div>
  );
}
