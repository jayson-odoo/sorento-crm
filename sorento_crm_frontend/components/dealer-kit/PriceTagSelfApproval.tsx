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

/** The note box Escalate opens: what marketing needs to fix, then Send. */
export function EscalateNote({
  onEscalate,
  onCancel,
}: {
  onEscalate: (note: string) => Promise<void>;
  onCancel?: () => void;
}) {
  const [note, setNote] = useState('');
  const [sending, setSending] = useState(false);
  const send = async () => {
    if (!note.trim()) return;
    setSending(true);
    try {
      await onEscalate(note.trim());
    } finally {
      setSending(false);
    }
  };
  return (
    <div className="space-y-2">
      <Textarea
        aria-label="What marketing needs to fix"
        placeholder="What needs fixing?"
        value={note}
        maxLength={2000}
        onChange={(event) => setNote(event.target.value)}
      />
      <div className="flex flex-wrap gap-2">
        <Button size="sm" onClick={() => void send()} disabled={!note.trim() || sending}>
          {sending ? <Loader2 className="size-4 mr-1 animate-spin" /> : null}
          Send to marketing
        </Button>
        {onCancel && (
          <Button size="sm" variant="ghost" onClick={onCancel} disabled={sending}>
            Cancel
          </Button>
        )}
      </div>
    </div>
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

  const footer = (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" size="sm" onClick={onEdit}>
          <PencilLine className="size-4 mr-1" />
          Edit
        </Button>
        <Button
          variant="outline"
          size="sm"
          aria-expanded={noteOpen}
          onClick={() => setNoteOpen((open) => !open)}
        >
          <Send className="size-4 mr-1" />
          Escalate to marketing
        </Button>
      </div>
      {noteOpen && (
        <EscalateNote onEscalate={onEscalate} onCancel={() => setNoteOpen(false)} />
      )}
    </div>
  );

  return (
    <DesignViewer
      docNumber={request.doc_number ?? 'Design'}
      payload={failed ? null : (built?.payload ?? null)}
      loading={loading}
      emptyMessage={failed ? 'Tag unavailable' : 'No tag template yet'}
      emptyHint={
        failed
          ? 'The tag could not be drawn. Escalate it to marketing.'
          : 'None of these items has a published tag template. Escalate it to marketing.'
      }
      footer={footer}
      headerActions={
        <Button size="sm" onClick={() => void approve()} disabled={!built || approving}>
          {approving ? (
            <Loader2 className="size-4 mr-1 animate-spin" />
          ) : (
            <Check className="size-4 mr-1" />
          )}
          Approve
        </Button>
      }
    />
  );
}
