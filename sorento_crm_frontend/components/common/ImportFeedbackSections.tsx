'use client';

import { useState } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';

/**
 * What an import Test found, rendered the same way in every import dialog.
 *
 * The SCM uploads, the GRN/SPO imports and the customer importer each grew their own version
 * of this - a bespoke amber panel here, a chip list there - and the four disagreed about the
 * one thing that matters: whether a warning means rows are being dropped. This is the single
 * rendering, and the disagreement is designed out of it.
 *
 * **The skip claim comes from `skippedCount`, never from a list length.** `warnings` mixes
 * row problems, unrecognised columns, unrecognised reference values and aggregate notes, and
 * only some of those skip anything. Counting them all told an operator "3 rows need a look,
 * those rows are skipped" about a clean 900-row file that happened to carry three
 * unrecognised columns. So the count is passed in from whatever the backend actually
 * reported as skipped, and a caller that has no such figure gets a heading that claims
 * nothing ("Rows that need a look").
 *
 * Sections render only when they have something to say: this is a report, not a form, so an
 * empty "0 warnings" panel is noise rather than an empty state.
 */

/** A row the reader could not use, or used with a caveat. */
export interface ImportRejectedRow {
  /** The spreadsheet's own row number. Null when the fact is not about one row. */
  row?: number | null;
  reason: string;
  value?: string | null;
}

/** One line inside a notice section: a lead, the text, and an optional code chip. */
export interface ImportNoticeItem {
  key: string;
  /** Rendered in the foreground colour - a row number, a document, an agent code. */
  lead?: string;
  text: string;
  /** Rendered as a monospace chip: the value the message is about. */
  code?: string;
}

/** A named list beside the standard ones. Used for facts that are neither a warning nor a
    rejected row - "these agents carry no demand class" being the case it was built for. */
export interface ImportNoticeSection {
  key: string;
  title: string;
  items: ImportNoticeItem[];
  hint?: string;
}

export interface ImportFeedbackSectionsProps {
  /** Blocking: nothing would be imported. */
  errors?: string[];
  /** Non-blocking. Never worded as a skip - see the note above. */
  warnings?: string[];
  unrecognisedColumns?: string[];
  rejectedRows?: ImportRejectedRow[];
  /**
   * How many rows the backend says are skipped. Pass it whenever the backend reports one;
   * leave it undefined when the listed rows are NOT all skips, and the heading will not
   * claim they are.
   */
  skippedCount?: number;
  notices?: ImportNoticeSection[];
  /** Rows shown before the show-all toggle. */
  previewLimit?: number;
}

const DEFAULT_PREVIEW_LIMIT = 8;

function plural(n: number, one: string, many: string): string {
  return n === 1 ? one : many;
}

function Panel({
  title,
  tone = 'default',
  children,
}: {
  title: string;
  tone?: 'default' | 'warning';
  children: React.ReactNode;
}) {
  return (
    <div
      data-slot="import-feedback-panel"
      className={
        tone === 'warning'
          ? 'rounded-lg border border-amber-500/40 bg-amber-500/5 p-3'
          : 'rounded-lg border border-border p-3'
      }
    >
      <h4 className="text-xs font-semibold">{title}</h4>
      {children}
    </div>
  );
}

export function ImportFeedbackSections({
  errors = [],
  warnings = [],
  unrecognisedColumns = [],
  rejectedRows = [],
  skippedCount,
  notices = [],
  previewLimit = DEFAULT_PREVIEW_LIMIT,
}: ImportFeedbackSectionsProps) {
  const [showAllRows, setShowAllRows] = useState(false);

  const hasNotices = notices.some((section) => section.items.length > 0);
  if (
    !errors.length &&
    !warnings.length &&
    !unrecognisedColumns.length &&
    !rejectedRows.length &&
    !hasNotices
  ) {
    return null;
  }

  const shownRows = showAllRows ? rejectedRows : rejectedRows.slice(0, previewLimit);
  const rowsTitle =
    skippedCount == null
      ? `Rows that need a look (${rejectedRows.length.toLocaleString()})`
      : `${skippedCount.toLocaleString()} ${plural(skippedCount, 'row', 'rows')} skipped`;

  return (
    <div data-slot="import-feedback" className="space-y-3">
      {errors.length ? (
        <Alert variant="destructive" appearance="light">
          <AlertDescription>
            <p className="font-medium">Nothing would be imported.</p>
            <ul className="mt-1 list-disc space-y-0.5 ps-4">
              {errors.map((error, index) => (
                <li key={`${index}-${error}`}>{error}</li>
              ))}
            </ul>
          </AlertDescription>
        </Alert>
      ) : null}

      {warnings.length ? (
        <Panel
          tone="warning"
          title={`${warnings.length.toLocaleString()} ${plural(warnings.length, 'warning', 'warnings')}`}
        >
          <ul className="mt-1.5 list-disc space-y-0.5 ps-4 text-2xs text-muted-foreground">
            {warnings.map((warning, index) => (
              <li key={`${index}-${warning}`}>{warning}</li>
            ))}
          </ul>
        </Panel>
      ) : null}

      {unrecognisedColumns.length ? (
        <Panel
          title={`Columns we did not recognise (${unrecognisedColumns.length.toLocaleString()})`}
        >
          <div className="mt-1.5 flex flex-wrap gap-1">
            {unrecognisedColumns.map((column) => (
              <span
                key={column}
                className="rounded bg-muted px-1.5 py-0.5 text-2xs text-muted-foreground"
              >
                {column}
              </span>
            ))}
          </div>
        </Panel>
      ) : null}

      {rejectedRows.length ? (
        <Panel title={rowsTitle}>
          <ul className="mt-1.5 space-y-1">
            {shownRows.map((row, index) => (
              <li
                key={`${row.row ?? 'none'}-${index}-${row.reason}`}
                className="flex flex-wrap items-baseline gap-x-1.5 text-2xs text-muted-foreground"
              >
                {row.row == null ? null : (
                  <span className="font-medium text-foreground">Row {row.row}</span>
                )}
                <span>{row.reason}</span>
                {row.value ? (
                  <span className="rounded bg-muted px-1 py-0.5 font-mono">{row.value}</span>
                ) : null}
              </li>
            ))}
          </ul>
          {rejectedRows.length > previewLimit ? (
            <button
              type="button"
              className="mt-1.5 text-2xs underline"
              onClick={() => setShowAllRows(!showAllRows)}
            >
              {showAllRows ? 'Show less' : `Show all ${rejectedRows.length.toLocaleString()}`}
            </button>
          ) : null}
        </Panel>
      ) : null}

      {notices.map((section) =>
        section.items.length ? (
          <Panel
            key={section.key}
            title={`${section.title} (${section.items.length.toLocaleString()})`}
          >
            <ul className="mt-1.5 space-y-1">
              {section.items.map((item) => (
                <li
                  key={item.key}
                  className="flex flex-wrap items-baseline gap-x-1.5 text-2xs text-muted-foreground"
                >
                  {item.lead ? (
                    <span className="font-medium text-foreground">{item.lead}</span>
                  ) : null}
                  {item.code ? (
                    <span className="rounded bg-muted px-1 py-0.5 font-mono">{item.code}</span>
                  ) : null}
                  <span>{item.text}</span>
                </li>
              ))}
            </ul>
            {section.hint ? (
              <p className="mt-1.5 text-2xs text-muted-foreground">{section.hint}</p>
            ) : null}
          </Panel>
        ) : null,
      )}
    </div>
  );
}

export default ImportFeedbackSections;
