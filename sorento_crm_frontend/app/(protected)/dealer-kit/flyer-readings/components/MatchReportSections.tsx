'use client';

import { useMemo, type ReactNode } from 'react';
import Link from 'next/link';
import { AlertTriangle, CheckCircle2, Copy, Ruler, SearchX, Tag } from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

import type {
  DimensionCandidate,
  MatchReport,
  MatchedCode,
  UnmatchedCode,
} from '../../services/flyerReadingService';
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
 * - Sizes are labelled as a report and never as an applied change (PLAN D9).
 * - Every section renders even when it is empty, because "no promotion gaps" is
 *   an answer somebody needs, and a section that vanishes on zero looks like a
 *   section that failed to load.
 */

/** A millimetre figure without a pointless `.0`. */
function mm(value: number | null): string {
  if (value === null || Number.isNaN(value)) return '';
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(1)));
}

function size(
  length: number | null,
  width: number | null,
  height: number | null,
): string | null {
  if (length === null && width === null && height === null) return null;
  return `${mm(length)} x ${mm(width)} x ${mm(height)} mm`;
}

/** "p. 3" / "p. 3, 11". A reviewer is holding the paper. */
function printedOn(pages: number[]): string {
  if (pages.length === 0) return 'Unknown page';
  return `p. ${pages.join(', ')}`;
}

function Section({
  id,
  icon,
  title,
  description,
  action,
  children,
}: {
  id: string;
  icon: ReactNode;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3" data-dk-fr-section={id}>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          <span className="mt-0.5 shrink-0 text-muted-foreground">{icon}</span>
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{description}</p>
          </div>
        </div>
        {action && <div className="shrink-0">{action}</div>}
      </div>
      {children}
    </section>
  );
}

/** The empty state of a section, always with what it means and what to do next. */
function Empty({
  tone = 'good',
  title,
  children,
}: {
  tone?: 'good' | 'neutral';
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="py-8 text-center">
      {tone === 'good' ? (
        <CheckCircle2 className="mx-auto size-6 text-green-600" />
      ) : (
        <SearchX className="mx-auto size-6 text-muted-foreground" />
      )}
      <p className="mt-3 text-sm font-medium text-foreground">{title}</p>
      <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">{children}</p>
    </div>
  );
}

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

const VERDICT_LABEL: Record<string, string> = {
  conflicts: 'Disagrees with the master',
  missing: 'Master has no size',
  agrees: 'Agrees',
};

export interface MatchReportSectionsProps {
  report: MatchReport;
  /** How many codes were printed at all, from the reading rather than the report. */
  codeCount: number;
  /** The promotion the report was computed against, by NAME. Never an id. */
  promotionLabel: string | null;
}

export function MatchReportSections({
  report,
  codeCount,
  promotionLabel,
}: MatchReportSectionsProps) {
  const duplicateRows = useMemo(
    () =>
      Object.entries(report.duplicates).map(([code, pages]) => ({
        code,
        pages: pages ?? [],
      })),
    [report.duplicates],
  );

  // Conflicts first. They are the entries that mean either a reprint or a wrong
  // box arriving at a customer, and burying them on page four of a table sorted
  // by code is the same as not reporting them.
  const dimensionRows = useMemo(() => {
    const rank = { conflicts: 0, missing: 1, agrees: 2 } as Record<string, number>;
    return [...report.dimensionCandidates].sort(
      (left, right) => (rank[left.verdict] ?? 9) - (rank[right.verdict] ?? 9),
    );
  }, [report.dimensionCandidates]);

  const conflicts = dimensionRows.filter((row) => row.verdict === 'conflicts').length;

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
              <Badge variant="outline" appearance="ghost" className="shrink-0 font-normal">
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

  const dimensionColumns = useMemo<ColumnDef<DimensionCandidate>[]>(
    () => [
      {
        accessorKey: 'code',
        header: 'Printed code',
        cell: ({ row }) => (
          <div className="truncate font-mono text-sm" title={row.original.code}>
            {row.original.code}
          </div>
        ),
        size: 170,
        minSize: 120,
        meta: { headerTitle: 'Printed code' },
      },
      {
        id: 'printed',
        header: 'On the flyer',
        cell: ({ row }) => {
          const value = size(
            row.original.printedLengthMm,
            row.original.printedWidthMm,
            row.original.printedHeightMm,
          );
          return (
            <span className="truncate text-sm" title={value ?? ''}>
              {value}
            </span>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'On the flyer' },
      },
      {
        id: 'current',
        header: 'In the master',
        cell: ({ row }) => {
          const value = size(
            row.original.currentLengthMm,
            row.original.currentWidthMm,
            row.original.currentHeightMm,
          );
          return value ? (
            <span className="truncate text-sm" title={value}>
              {value}
            </span>
          ) : (
            <span className="text-sm text-muted-foreground">Not recorded</span>
          );
        },
        size: 200,
        minSize: 140,
        meta: { headerTitle: 'In the master' },
      },
      {
        id: 'verdict',
        header: 'Verdict',
        cell: ({ row }) => (
          <Badge
            variant={row.original.verdict === 'conflicts' ? 'warning' : 'outline'}
            appearance="ghost"
            className="font-normal"
          >
            {VERDICT_LABEL[row.original.verdict] ?? row.original.verdict}
          </Badge>
        ),
        size: 190,
        minSize: 140,
        meta: { headerTitle: 'Verdict' },
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
        description="Each one is a product printed on the flyer that the brochure will not contain. The nearest existing code is a guess and is never applied for you."
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

      <Section
        id="dimensions"
        icon={<Ruler className="size-4" />}
        title="Sizes printed on the flyer"
        description={
          conflicts > 0
            ? `${conflicts} of ${dimensionRows.length} disagree with what the master holds. Nothing here is written to the product master by this screen.`
            : 'Reported only. Nothing here is written to the product master by this screen.'
        }
      >
        <ReportGrid
          data-testid="dk-fr-dimensions-grid"
          columns={dimensionColumns}
          rows={dimensionRows}
          getRowId={(row) => row.code}
          emptyMessage={
            <Empty tone="neutral" title="No card on this flyer printed a size">
              Sizes are read from the L x W x H line under a product code.
            </Empty>
          }
        />
      </Section>

      <Section
        id="duplicates"
        icon={<Copy className="size-4" />}
        title="Printed on more than one page"
        description="One product, printed twice. Each is seeded once per page it appears on, exactly as the flyer prints it."
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
        id="known-gaps"
        icon={<AlertTriangle className="size-4" />}
        title="What the draft will not have right"
        description="Known, and deliberate. Correcting these is the work the seed leaves you."
        action={
          <Button variant="outline" size="sm" asChild>
            <Link href="/dealer-kit/brochure-images">Choose brochure photos</Link>
          </Button>
        }
      >
        <ul
          className="flex list-disc flex-col gap-2 rounded-lg border border-border px-6 py-4 text-sm text-muted-foreground"
          data-testid="dk-fr-known-gaps"
        >
          <li>
            <strong className="text-foreground">Headings are guessed.</strong> The reader takes
            the largest piece of text near the top of each page, which is wrong wherever the
            heading is part of the artwork. Check every section heading against the paper.
          </li>
          <li>
            <strong className="text-foreground">Product photos are blank.</strong> No product has
            a brochure photo chosen yet, so tiles come through without a picture. That is the
            current state of the data, not a failed seed.
          </li>
          <li>
            <strong className="text-foreground">Sizes are not applied.</strong> The table above
            is a report. Changing the product master is a separate, deliberate act.
          </li>
          <li>
            <strong className="text-foreground">Some printed rows split.</strong> A row whose
            cards sit slightly off the same baseline comes through as two grids.
          </li>
        </ul>
      </Section>
    </div>
  );
}
