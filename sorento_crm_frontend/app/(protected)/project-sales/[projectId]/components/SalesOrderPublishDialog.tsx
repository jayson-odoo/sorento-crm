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
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type {
  ProjectSalesOrderFinding,
  SalesOrderPublishBody,
  SalesOrderPublishResult,
} from '../../_shared/types/projectSalesOrder.types';

/**
 * Publish, or say plainly why it is refused.
 *
 * Three states, one dialog: refused with the blocking findings listed, a confirmation for
 * an irreversible step, and the outcome, which is the reference the order is known by plus
 * the import file. Warnings without a recorded reason are named in the confirmation rather
 * than hidden, because that reason is the only trace of the decision afterwards.
 *
 * The refusal is not a dead end. Clearing thirty findings one at a time to publish an order
 * the manager has already decided to publish was the constraint, so the same override the
 * per-finding acknowledgement carries is offered here once: a reason, recorded on every
 * finding it waves through. Whether the user may use it is the backend's call, so the
 * control is always shown and its refusal is rendered in place.
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
  onPublish: (body?: SalesOrderPublishBody) => Promise<SalesOrderPublishResult>;
  onDownloadImportFile: () => void;
  submitting: boolean;
  downloading?: boolean;
}) {
  const [result, setResult] = React.useState<SalesOrderPublishResult | null>(null);
  const [acknowledge, setAcknowledge] = React.useState(false);
  const [reason, setReason] = React.useState('');
  const [error, setError] = React.useState<string | null>(null);

  // The server's gate, read off the publish response rather than re-derived here. A
  // response from before `can_export` shipped falls back to the url being there at all,
  // which is what this button used to go on.
  const canDownload = result
    ? (result.can_export ?? Boolean(result.import_file_url))
    : false;

  const publish = async (body?: SalesOrderPublishBody) => {
    setError(null);
    try {
      setResult(await onPublish(body));
    } catch (caught) {
      // The backend's own sentence (extracted in the service): who may override, or that a
      // reason is required. Shown here rather than as a toast, so it sits beside the field
      // it is about.
      setError(caught instanceof Error ? caught.message : 'Failed to publish this sales order');
    }
  };

  if (blocking.length > 0 && !result) {
    const waved = acknowledge && reason.trim().length >= 3;
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

          <div className="space-y-3">
            <label className="flex items-start gap-2 text-sm">
              <Checkbox
                checked={acknowledge}
                onCheckedChange={(next) => setAcknowledge(next === true)}
                aria-label={`Publish despite ${blocking.length} blocking finding${
                  blocking.length === 1 ? '' : 's'
                }`}
                className="mt-0.5"
              />
              <span>
                {`Publish despite ${blocking.length} blocking finding${
                  blocking.length === 1 ? '' : 's'
                }`}
              </span>
            </label>

            {acknowledge && (
              <div className="space-y-1.5">
                <Label htmlFor="so-publish-override-reason">
                  Reason <span className="text-destructive">*</span>
                </Label>
                <Textarea
                  id="so-publish-override-reason"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                  rows={3}
                  placeholder="Who decided to publish past these, and why"
                />
                <p className="text-xs text-muted-foreground">
                  Recorded on every one of these findings.
                </p>
              </div>
            )}

            {error && (
              <p className="rounded-md border border-destructive/40 bg-destructive/5 px-2 py-1.5 text-sm text-destructive">
                {error}
              </p>
            )}
          </div>

          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>Back to the findings</AlertDialogCancel>
            <AlertDialogAction
              disabled={!waved || submitting}
              onClick={async (event) => {
                event.preventDefault();
                await publish({ acknowledge_blocking: true, reason: reason.trim() });
              }}
            >
              {submitting ? 'Publishing…' : 'Publish anyway'}
            </AlertDialogAction>
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
                {result.acknowledged_findings ? (
                  <p>
                    {`${result.acknowledged_findings} blocking finding${
                      result.acknowledged_findings === 1 ? '' : 's'
                    } published anyway, with the reason recorded on each.`}
                  </p>
                ) : null}
                {result.import_file_url ? (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={onDownloadImportFile}
                    disabled={!canDownload || downloading}
                    title={canDownload ? undefined : 'Clear the blocking findings first'}
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
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 px-2 py-1.5 text-sm text-destructive">
            {error}
          </p>
        )}
        <AlertDialogFooter>
          <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={submitting}
            onClick={async (event) => {
              event.preventDefault();
              await publish();
            }}
          >
            {submitting ? 'Publishing…' : 'Publish'}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
