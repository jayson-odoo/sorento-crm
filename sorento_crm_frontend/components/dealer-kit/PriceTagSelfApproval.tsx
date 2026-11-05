'use client';

/**
 * The salesperson's own proof (PRICETAG-SELF-APPROVAL R2/R3/R6).
 *
 * The tag sheet is built here from the request's REAL tags (one placement per
 * `price_tag_request_tags` row, on the line's template) with `buildRequestSheet`,
 * the same builder the request form's live preview uses, and drawn by
 * `DesignViewer`, the proof's own renderer. Approve sends exactly that sheet, so
 * the PDF prints what was on screen. Escalate sends the request to marketing with
 * a note; Edit opens the revise composer.
 */

import { useCallback, useEffect, useState } from 'react';
import { Check, Loader2, PencilLine, Send } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { DatePicker, parseDateInput } from '@/components/ui/date-picker';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { formatLocalDateToYyyyMmDd } from '@/lib/helpers';
import DesignViewer from '@/components/dealer-kit/DesignViewer';
import { buildRequestSheet, type TagRequestTag } from '@/lib/dealer-kit/request-tags';
import {
  designPayloadFromResponse,
  type TagSheetDesignPayload,
} from '@/lib/dealer-kit/design-payload';
import type { TagSheetDoc, TagTemplate } from '@/lib/dealer-kit/tag-template-types';
import type {
  PriceTagRequestLine,
  TagPreviewResponse,
} from '@/app/(auth)/portal/lib/price-tag-request-service';

export interface SelfApprovalRequest {
  id: string;
  doc_number?: string | null;
  lines: PriceTagRequestLine[];
}

interface Props {
  request: SelfApprovalRequest;
  /** `POST /lookups/tag-preview {request_id}`: templates per line id + resolved data. */
  loadPreview: (requestId: string) => Promise<TagPreviewResponse>;
  onApprove: (doc: TagSheetDoc) => Promise<void>;
  onEdit: () => void;
  onEscalate: (note: string) => Promise<void>;
}

/** Every tag the request prints, with the line it belongs to. */
export function requestTags(lines: PriceTagRequestLine[]): TagRequestTag[] {
  return lines.flatMap((line) =>
    (line.tags ?? []).map((tag) => ({
      id: tag.id,
      quantity: tag.quantity,
      line: {
        id: line.id,
        line_type: line.line_type,
        product_id: line.product_id,
        product_set_id: line.product_set_id,
        quantity: line.quantity,
      },
    })),
  );
}

/** The sheet to approve and the payload that draws it; null when nothing can be drawn. */
export function buildSelfProof(
  lines: PriceTagRequestLine[],
  response: TagPreviewResponse,
): { doc: TagSheetDoc; payload: TagSheetDesignPayload } | null {
  let seq = 0;
  const doc = buildRequestSheet(
    requestTags(lines),
    response.templates as Record<string, TagTemplate>,
    () => `placed-${(seq += 1)}`,
  );
  if (doc.sheets.every((sheet) => sheet.tags.length === 0)) return null;
  const payload = designPayloadFromResponse({
    doc,
    lines: response.lines,
    assets: response.assets,
    images: response.images,
    fonts: response.fonts,
  });
  return payload ? { doc, payload } : null;
}

/** The codes of the lines that print a tag but have no template to draw it with. */
export function linesWithoutTemplate(
  lines: PriceTagRequestLine[],
  response: TagPreviewResponse,
): string[] {
  return [
    ...new Set(
      lines
        .filter((line) => (line.tags ?? []).length > 0 && !response.templates[line.id])
        .map((line) => line.code),
    ),
  ];
}

/** Today as `yyyy-mm-dd` (local), the earliest Need by marketing cannot meet. */
function todayKey(): string {
  return formatLocalDateToYyyyMmDd(new Date());
}

/**
 * The lightbox Escalate opens (owner hand test 5 Nov, #2138): what marketing
 * needs to fix, and on the draft form also the date he needs the tags by.
 * `needBy` given (even '') shows the date field, prefilled from the draft.
 */
export function EscalateDialog({
  open,
  onOpenChange,
  onEscalate,
  needBy,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onEscalate: (note: string, neededBy: string | null) => Promise<void>;
  needBy?: string;
}) {
  const [note, setNote] = useState('');
  const [date, setDate] = useState('');
  const [sending, setSending] = useState(false);
  useEffect(() => {
    if (!open) return;
    setNote('');
    setDate(needBy ?? '');
  }, [open, needBy]);
  const withDate = needBy !== undefined;
  const dateTooEarly = withDate && date !== '' && date <= todayKey();
  const send = async () => {
    if (!note.trim() || dateTooEarly) return;
    setSending(true);
    try {
      await onEscalate(note.trim(), withDate ? date || null : null);
      onOpenChange(false);
    } finally {
      setSending(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={(next) => (sending ? undefined : onOpenChange(next))}>
      <DialogContent aria-describedby={undefined} className="max-w-[calc(100%-2rem)] sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Escalate to marketing</DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="escalate-note">What needs fixing?</Label>
            <Textarea
              id="escalate-note"
              aria-label="What marketing needs to fix"
              value={note}
              maxLength={2000}
              rows={4}
              onChange={(event) => setNote(event.target.value)}
            />
          </div>
          {withDate && (
            <div className="space-y-1.5">
              <Label htmlFor="escalate-need-by">Need by</Label>
              <DatePicker
                id="escalate-need-by"
                value={date ? parseDateInput(date) : undefined}
                onChange={(next) => setDate(next ? formatLocalDateToYyyyMmDd(next) : '')}
              />
              {dateTooEarly && (
                <p className="text-xs text-destructive">Pick a date after today.</p>
              )}
            </div>
          )}
        </DialogBody>
        <DialogFooter className="gap-2 sm:gap-0">
          <Button
            variant="outline"
            className="w-full sm:w-auto"
            onClick={() => onOpenChange(false)}
            disabled={sending}
          >
            Cancel
          </Button>
          <Button
            className="w-full sm:w-auto"
            onClick={() => void send()}
            disabled={!note.trim() || dateTooEarly || sending}
          >
            {sending ? <Loader2 className="size-4 mr-1 animate-spin" /> : <Send className="size-4 mr-1" />}
            Send to marketing
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function PriceTagSelfApproval({
  request,
  loadPreview,
  onApprove,
  onEdit,
  onEscalate,
}: Props) {
  const [built, setBuilt] = useState<ReturnType<typeof buildSelfProof>>(null);
  // A line with no template is left off the sheet, and the server refuses the
  // approval (NO_TEMPLATE), so it is named here and Approve stays off.
  const [missing, setMissing] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [approving, setApproving] = useState(false);
  const [noteOpen, setNoteOpen] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true);
    loadPreview(request.id)
      .then((response) => {
        if (!live) return;
        setBuilt(buildSelfProof(request.lines, response));
        setMissing(linesWithoutTemplate(request.lines, response));
        setFailed(false);
      })
      .catch(() => {
        if (live) setFailed(true);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [request.id, request.lines, loadPreview]);

  const approve = useCallback(async () => {
    if (!built) return;
    setApproving(true);
    try {
      await onApprove(built.doc);
    } finally {
      setApproving(false);
    }
  }, [built, onApprove]);

  const missingText =
    missing.length > 0
      ? `No tag template yet for ${missing.join(', ')}. Escalate it to marketing.`
      : null;

  const footer = (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={onEdit}>
          <PencilLine className="size-4 mr-1" />
          Edit
        </Button>
        <Button variant="outline" size="sm" onClick={() => setNoteOpen(true)}>
          <Send className="size-4 mr-1" />
          Escalate to marketing
        </Button>
      </div>
      <EscalateDialog
        open={noteOpen}
        onOpenChange={setNoteOpen}
        onEscalate={(note) => onEscalate(note)}
      />
    </div>
  );

  // Why Approve is off, said where the button is (crew pass: the reason used to
  // sit under the sheet, below the fold at 1280).
  const approveBlockedReason = missingText ?? (failed ? 'The tag could not be drawn.' : null);

  return (
    <div className="space-y-2">
      {missingText && built && (
        <p role="status" className="text-sm text-muted-foreground">
          {missingText}
        </p>
      )}
      <DesignViewer
        docNumber={request.doc_number ?? 'Design'}
        payload={failed ? null : (built?.payload ?? null)}
        loading={loading}
        emptyMessage={failed ? 'Tag unavailable' : 'No tag template yet'}
        emptyHint={
          failed
            ? 'The tag could not be drawn. Escalate it to marketing.'
            : (missingText ?? 'Escalate it to marketing.')
        }
        footer={footer}
        headerActions={
          // A disabled button fires no hover, so the reason sits on its wrapper.
          <span title={approveBlockedReason ?? undefined} className="inline-flex">
            <Button
              size="sm"
              onClick={() => void approve()}
              disabled={!built || missing.length > 0 || approving}
            >
              {approving ? (
                <Loader2 className="size-4 mr-1 animate-spin" />
              ) : (
                <Check className="size-4 mr-1" />
              )}
              Approve
            </Button>
          </span>
        }
      />
    </div>
  );
}
