'use client';

import { LoaderCircle, TestTube } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { fmtInt } from '../../lib/format';
import { MAX_SIZE_MB, useTwoStepUpload } from '../hooks/useTwoStepUpload';
import {
  applyLevelImport,
  previewLevelImport,
  type LevelImportOutcome,
} from '../services/reorderLevelImportService';
import { CountTile } from './UploadCountTile';

/**
 * The AutoCount reorder level + reorder quantity listing (S13c).
 *
 * AutoCount owns the level; this dialog receives it. The one rule worth a whole panel is
 * the conflict list: a level a person set by hand is never silently overwritten - the file
 * and the buyer disagreeing is put on screen for the buyer to settle, because "last writer
 * wins" between a person and a feed is how a decision quietly reverts.
 *
 * Test then Confirm, with nothing running on file select - the same three presses as every
 * other upload in this system. This channel's Confirm is still SYNCHRONOUS, unlike the five
 * order-book feeds: it writes a level per product on a listing of a few thousand rows, well
 * inside a request, and it has no queued task. So the result is still shown here rather than
 * on a job page, and that difference is deliberate rather than an oversight.
 */

function OutcomePanel({ outcome, applied }: { outcome: LevelImportOutcome; applied: boolean }) {
  if (!outcome.readable) {
    return (
      <Alert variant="destructive" appearance="light">
        <AlertDescription>
          The file is missing {outcome.missing_columns.join(', ').replaceAll('_', ' ')}.
          Nothing {applied ? 'was' : 'will be'} written.
        </AlertDescription>
      </Alert>
    );
  }
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <CountTile label="New levels" value={outcome.created} />
        <CountTile label="Updated" value={outcome.updated} />
        <CountTile label="Unchanged" value={outcome.unchanged} />
        <CountTile label="Kept yours" value={outcome.conflicts} />
      </div>

      {outcome.conflict_rows.length ? (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/5 p-3 text-sm">
          <p className="font-medium">
            {fmtInt(outcome.conflicts)} level{outcome.conflicts === 1 ? '' : 's'} you set by
            hand disagree{outcome.conflicts === 1 ? 's' : ''} with the file, and{' '}
            {applied ? 'were' : 'will be'} kept:
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {outcome.conflict_rows.slice(0, 8).map((c) => (
              <li key={`${c.item_code}:${c.location ?? ''}`}>
                {c.item_code}
                {c.location ? ` at ${c.location}` : ''}: yours {fmtInt(c.held_level)}, file{' '}
                {fmtInt(c.file_level)}
              </li>
            ))}
            {outcome.conflict_rows.length > 8 ? (
              <li>and {outcome.conflict_rows.length - 8} more</li>
            ) : null}
          </ul>
        </div>
      ) : null}

      {outcome.problems.length ? (
        <div className="rounded-lg border p-3 text-sm">
          <p className="font-medium">
            {fmtInt(outcome.problems.length)} row{outcome.problems.length === 1 ? '' : 's'}{' '}
            skipped:
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-muted-foreground">
            {outcome.problems.slice(0, 8).map((p) => (
              <li key={`${p.row}-${p.reason}`}>
                Row {p.row}: {p.reason}
              </li>
            ))}
            {outcome.problems.length > 8 ? <li>and {outcome.problems.length - 8} more</li> : null}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

export function ReorderLevelUploadDialog({
  open,
  onOpenChange,
  onApplied,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onApplied?: (result: LevelImportOutcome) => void;
}) {
  const up = useTwoStepUpload<LevelImportOutcome, LevelImportOutcome>({
    open,
    preview: previewLevelImport,
    apply: applyLevelImport,
    onApplied,
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-xl">
        <DialogHeader>
          <DialogTitle>Upload reorder levels</DialogTitle>
          <DialogDescription>
            The reorder level and reorder quantity listing from AutoCount. Levels you set by
            hand here are kept, never overwritten.
          </DialogDescription>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <FileDropzone
            files={up.file ? [up.file] : []}
            onFilesChange={(next) => up.choose(next[0] ?? null)}
            onReject={up.reject}
            accept={up.accept}
            maxSizeMb={MAX_SIZE_MB}
            disabled={up.previewing || up.applying}
            aria-label="AutoCount reorder level listing"
          />

          {up.error ? (
            <Alert variant="destructive" appearance="light">
              <AlertDescription>{up.error}</AlertDescription>
            </Alert>
          ) : null}

          {up.previewing ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
              Reading the file...
            </div>
          ) : null}

          {up.result ? (
            <OutcomePanel outcome={up.result} applied />
          ) : up.preview ? (
            <OutcomePanel outcome={up.preview} applied={false} />
          ) : null}
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {up.result ? 'Close' : 'Cancel'}
          </Button>
          {!up.result ? (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={() => void up.runTest()}
                disabled={!up.file || up.previewing || up.applying || up.testing}
              >
                {up.testing ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : (
                  <TestTube className="size-4" aria-hidden />
                )}
                Test
              </Button>
              <Button onClick={() => void up.confirm()} disabled={!up.canConfirm}>
                {up.applying ? (
                  <LoaderCircle className="size-4 animate-spin" aria-hidden />
                ) : null}
                Confirm upload
              </Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
