import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { fmtInt } from '../../lib/format';

/**
 * The Test verdict, rendered the way every other importer in this system renders it.
 *
 * `import-tracking` and the GRN import have had a Test button for a long time, and this is
 * the shape behind it: green when there is nothing to fix, red for errors that BLOCK, amber
 * for warnings that do not. The SCM uploads were the odd ones out - they showed a diff and
 * left the operator to work out whether it was safe to apply.
 *
 * The line between the two is what the reader trusts. RED means the FILE cannot be used;
 * AMBER means it can, and some rows will not be part of it. A skipped row reported in red
 * says "this upload failed" about a file that imports 4,346 of its 4,349 rows perfectly,
 * and a panel that cries wolf is a panel nobody reads.
 *
 * Warnings render whether or not the file is valid, which is the whole point of the split: a
 * perfectly loadable file can still be about to skip 2,000 lines, and the operator has to see
 * that BEFORE they press Confirm rather than discover it in the result.
 */

export interface UploadTestResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
  summary?: Record<string, unknown>;
  /**
   * Extra one-line facts about what the file would do, printed under the counts. For the
   * figures that are neither a count of rows nor a problem: today the shipping-order half
   * of a purchase book, which lands in a different table from the rows around it and has
   * its own new / changed / unchanged split.
   */
  notes?: string[];
}

function num(v: unknown): string | null {
  return typeof v === 'number' ? fmtInt(v) : null;
}

export function UploadTestVerdict({ result }: { result: UploadTestResult }) {
  const s = result.summary ?? {};
  const parts = [
    num(s.total_rows) && `Rows: ${num(s.total_rows)}`,
    // For a channel whose unit is a DOCUMENT rather than a row: one proforma file is
    // routinely five invoices, and "500 rows" never said how many invoices that is.
    num(s.document_count) && `Invoices: ${num(s.document_count)}`,
    num(s.would_create) && `Would create: ${num(s.would_create)}`,
    num(s.would_update) && `Would update: ${num(s.would_update)}`,
    // For the channels whose backend does not split create from update: how many of the rows
    // read would actually land. "500 rows read" alone never said how many of them survive.
    num(s.would_apply) && `Would import: ${num(s.would_apply)}`,
    // What the import would leave out. Its own figure, because "read 4,349, importing 4,346"
    // makes the reader do the subtraction and then doubt the answer.
    num(s.skipped_rows) && `Skipped: ${num(s.skipped_rows)}`,
    num(s.error_count) && `Errors: ${num(s.error_count)}`,
  ].filter(Boolean);

  return (
    <div className="space-y-3" data-slot="upload-test-verdict">
      {parts.length ? (
        <p className="text-2xs text-muted-foreground">{parts.join(' • ')}</p>
      ) : null}

      {(result.notes ?? []).map((note) => (
        <p key={note} className="text-2xs text-muted-foreground">
          {note}
        </p>
      ))}

      {result.valid ? (
        <Alert className="border-green-200 bg-green-50 text-green-900">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertTitle>No errors</AlertTitle>
          <AlertDescription>You can upload this file.</AlertDescription>
        </Alert>
      ) : (
        <Alert variant="destructive" className="flex flex-col items-stretch">
          <AlertCircle className="h-4 w-4 shrink-0" />
          <div className="min-w-0 flex-1 space-y-1">
            <AlertTitle>Errors ({result.errors.length})</AlertTitle>
            <AlertDescription className="p-0">
              {/* A plain scrolling div, not Radix `ScrollArea`: that component renders its
                  own viewport INSIDE this element, and the viewport does not inherit the
                  `max-h`, so the list grew to whatever height it liked and 2,000 rows pushed
                  the dialog's buttons off the screen. */}
              <div className="max-h-[220px] w-full overflow-y-auto rounded border p-2 text-sm">
                <ul className="list-inside list-disc space-y-0.5 pr-2">
                  {result.errors.map((e, i) => (
                    // Index-keyed: the message is not unique (the same missing column can be
                    // reported twice) and duplicate keys collide.
                    <li key={`${i}-${e}`}>{e}</li>
                  ))}
                </ul>
              </div>
            </AlertDescription>
          </div>
        </Alert>
      )}

      {result.warnings.length ? (
        <Alert className="border-amber-200 bg-amber-50 text-amber-900">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertTitle>Warnings ({result.warnings.length})</AlertTitle>
          <AlertDescription className="p-0">
            {/* Same clamp, same reason as the error list above - and this one is the longer
                of the two now that a skipped row is a warning. */}
            <div className="max-h-[220px] w-full overflow-y-auto rounded border p-2 text-sm">
              <ul className="list-inside list-disc space-y-0.5 pr-2">
                {result.warnings.map((w, i) => (
                  <li key={`${i}-${w}`}>{w}</li>
                ))}
              </ul>
            </div>
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

export default UploadTestVerdict;
