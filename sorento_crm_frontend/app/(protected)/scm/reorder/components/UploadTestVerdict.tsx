import { AlertCircle, AlertTriangle, CheckCircle } from 'lucide-react';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { ScrollArea } from '@/components/ui/scroll-area';
import { fmtInt } from '../../lib/format';

/**
 * The Test verdict, rendered the way every other importer in this system renders it.
 *
 * `import-tracking` and the GRN import have had a Test button for a long time, and this is
 * the shape behind it: green when there is nothing to fix, red for errors that BLOCK, amber
 * for warnings that do not. The SCM uploads were the odd ones out - they showed a diff and
 * left the operator to work out whether it was safe to apply.
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
}

function num(v: unknown): string | null {
  return typeof v === 'number' ? fmtInt(v) : null;
}

export function UploadTestVerdict({ result }: { result: UploadTestResult }) {
  const s = result.summary ?? {};
  const parts = [
    num(s.total_rows) && `Rows: ${num(s.total_rows)}`,
    num(s.would_create) && `Would create: ${num(s.would_create)}`,
    num(s.would_update) && `Would update: ${num(s.would_update)}`,
    num(s.error_count) && `Errors: ${num(s.error_count)}`,
  ].filter(Boolean);

  return (
    <div className="space-y-3" data-slot="upload-test-verdict">
      {parts.length ? (
        <p className="text-2xs text-muted-foreground">{parts.join(' • ')}</p>
      ) : null}

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
              <ScrollArea className="max-h-[220px] w-full rounded border p-2 text-sm">
                <ul className="list-inside list-disc space-y-0.5 pr-2">
                  {result.errors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </ScrollArea>
            </AlertDescription>
          </div>
        </Alert>
      )}

      {result.warnings.length ? (
        <Alert className="border-amber-200 bg-amber-50 text-amber-900">
          <AlertTriangle className="h-4 w-4 text-amber-600" />
          <AlertTitle>Warnings ({result.warnings.length})</AlertTitle>
          <AlertDescription className="p-0">
            <ScrollArea className="max-h-[180px] w-full rounded border p-2 text-sm">
              <ul className="list-inside list-disc space-y-0.5 pr-2">
                {result.warnings.map((w) => (
                  <li key={w}>{w}</li>
                ))}
              </ul>
            </ScrollArea>
          </AlertDescription>
        </Alert>
      ) : null}
    </div>
  );
}

export default UploadTestVerdict;
