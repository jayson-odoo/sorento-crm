'use client';

import * as React from 'react';
import { Download, OctagonAlert } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import type {
  ProjectSalesOrderFinding,
  SalesOrderPublishResult,
} from '../../_shared/types/projectSalesOrder.types';

/**
 * Publish, or say plainly why it is refused.
 *
 * Three states, one dialog: refused with the blocking findings listed, a confirmation for
 * an irreversible step, and the outcome, which is the reference the order is known by plus
 * the import file. Warnings without a recorded reason are named in the confirmation rather
 * than hidden, because that reason is the only trace of the decision afterwards.
 */
export function SalesOrderPublishDialog({
  reference,
  blocking,
  unacknowledgedWarnings,
  onDone,
  onPublish,
  onDownloadImportFile,
  submitting,
  downloading,
}: {
  reference: string;
  blocking: ProjectSalesOrderFinding[];
  unacknowledgedWarnings: ProjectSalesOrderFinding[];
  onDone: () => void;
  onPublish: () => Promise<SalesOrderPublishResult>;
  onDownloadImportFile: () => void;
  submitting: boolean;
  downloading?: boolean;
}) {
  const [result, setResult] = React.useState<SalesOrderPublishResult | null>(null);

  if (blocking.length > 0) {
    return (
      <AlertDialog open onOpenChange={(next) => !next && onDone()}>
        <AlertDialogContent className="max-h-[90vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <OctagonAlert className="size-4 text-destructive" aria-hidden />
              Publishing is refused
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2">
                <p>
                  {`${reference} has ${blocking.length} finding${
                    blocking.length === 1 ? '' : 's'
                  } that must be fixed or overridden first.`}
                </p>
                <ul className="space-y-1.5">
                  {blocking.map((finding) => (
                    <li
                      key={finding.id}
                      className="rounded-md border border-destructive/40 bg-destructive/5 px-2 py-1.5 text-sm text-foreground"
                    >
                      {finding.line_no != null ? `Line ${finding.line_no}: ` : ''}
                      {finding.detail}
                    </li>
                  ))}
                </ul>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Back to the findings</AlertDialogCancel>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  if (result) {
    return (
      <AlertDialog open onOpenChange={(next) => !next && onDone()}>
        <AlertDialogContent className="max-h-[90vh] overflow-y-auto">
          <AlertDialogHeader>
            <AlertDialogTitle>Published</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-3">
                <p>
                  {`This sales order is ${result.autocount_doc_no || result.provisional_ref}.`}
                </p>
                {result.import_file_url ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onDownloadImportFile}
                    disabled={downloading}
                  >
                    <Download className="size-4" aria-hidden />
                    Download the import file
                  </Button>
                ) : (
                  <p className="text-sm">
                    No import file came back with this response. Reload the sales order to pick
                    it up.
                  </p>
                )}
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogAction onClick={onDone}>Done</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    );
  }

  return (
    <AlertDialog open onOpenChange={(next) => !next && onDone()}>
      <AlertDialogContent className="max-h-[90vh] overflow-y-auto">
        <AlertDialogHeader>
          <AlertDialogTitle>{`Publish ${reference}?`}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2">
              <p>
                It becomes a committed sales order and produces the AutoCount import file.
                This cannot be undone; a later change goes through an amendment.
              </p>
              {unacknowledgedWarnings.length > 0 && (
                <div className="space-y-1.5">
                  <p>
                    {unacknowledgedWarnings.length === 1
                      ? '1 warning has no reason recorded:'
                      : `${unacknowledgedWarnings.length} warnings have no reason recorded:`}
                  </p>
                  <ul className="space-y-1">
                    {unacknowledgedWarnings.map((finding) => (
                      <li key={finding.id} className="text-sm">
                        {finding.line_no != null ? `Line ${finding.line_no}: ` : ''}
                        {finding.detail}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={submitting}
            onClick={async (event) => {
              event.preventDefault();
              const published = await onPublish();
              setResult(published);
            }}
          >
            {submitting ? 'Publishing…' : 'Publish'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
