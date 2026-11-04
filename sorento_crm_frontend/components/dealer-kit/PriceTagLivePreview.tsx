'use client';

/**
 * The request form's live tag preview (PRICETAG-TEMPLATE-PER-PRODUCT R5).
 *
 * From the first item on: every line's tag drawn with its template (the pick,
 * the product's single link, its first link, else the family default) and the
 * line's real data and price, redrawn as the lines change. Nothing is saved.
 *
 * The server answers the templates and the resolved data
 * (`POST /lookups/tag-preview`, the proof's own resolver); the sheet itself is
 * built here by `buildRequestSheet`, the same builder the salesperson's
 * approve screen uses (PRICETAG-SELF-APPROVAL), and drawn by `DesignViewer`,
 * the proof's own renderer. One tag per line: a preview shows what each tag
 * looks like, not how many copies print.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import DesignViewer from '@/components/dealer-kit/DesignViewer';
import DesignLightbox from '@/components/dealer-kit/DesignLightbox';
import { toast } from '@/lib/toast';
import { buildRequestSheet, buildSingleTagSheet, type TagRequestTag } from '@/lib/dealer-kit/request-tags';
import { designPayloadFromResponse, type TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import { partsPayload, type DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
import type { TagTemplate } from '@/lib/dealer-kit/tag-template-types';
import type {
  PriceMode,
  TagPreviewLineInput,
  TagPreviewResponse,
} from '@/app/(auth)/portal/lib/price-tag-request-service';

/** How long the form has to sit still before the preview asks again. */
export const PREVIEW_DEBOUNCE_MS = 400;

interface Props {
  lines: DraftLine[];
  priceMode: PriceMode;
  lookupTagPreview: (priceMode: PriceMode, lines: TagPreviewLineInput[]) => Promise<TagPreviewResponse>;
  /** The lightbox title; never an id. */
  docNumber?: string;
  /**
   * PRICETAG-SELF-APPROVAL (owner ruling 3 Nov): the items the preview could not
   * draw for want of a template, and whether a drawing exists at all. The form
   * keeps Approve off while either says the tag is not ready.
   */
  onReadyChange?: (state: { missing: string[]; drawn: boolean; failed: boolean }) => void;
  /** PRICETAG-LPSP: draw this one line only (the row's eye icon). */
  lineKey?: string;
  /** One-line mode: the lightbox was closed. */
  onClose?: () => void;
}

/** The lines worth drawing, in the shape the preview route reads. */
export function previewLines(lines: DraftLine[], priceMode?: PriceMode): TagPreviewLineInput[] {
  return lines
    .filter((l) => (l.line_type === 'product' ? !!l.product_id : !!l.product_set_id))
    .map((l) => ({
      key: l.key,
      line_type: l.line_type,
      product_id: l.line_type === 'product' ? l.product_id : null,
      product_set_id: l.line_type === 'product_set' ? l.product_set_id : null,
      combo_id: l.combo_id,
      parts: partsPayload(l.parts),
      promotion_id: l.promotion_id,
      // A typed price only applies to an SP line (the server refuses it otherwise).
      manual_sell_price: (l.price_type ?? priceMode) === 'list' ? null : l.manual_sell_price,
      tag_template_id: l.line_type === 'product' ? (l.tag_template_id ?? null) : null,
      price_type: l.price_type ?? null,
    }));
}

/**
 * The items the preview could not draw: a product with no linked template gets
 * none (no silent fallback, #2101), named by its code so the salesperson knows
 * which line to escalate. Codes come off the resolved rows, the form's own code
 * when a row is missing.
 */
export function linesWithoutTemplate(
  sent: TagPreviewLineInput[],
  response: TagPreviewResponse,
  codeByKey: Record<string, string> = {},
): string[] {
  const rowCode = new Map(response.lines.map((row) => [row.line_id, row.code]));
  return sent
    .filter((line) => !response.templates[line.key])
    .map((line) => rowCode.get(line.key) || codeByKey[line.key] || '')
    .filter(Boolean);
}

/** The response, drawn: one synthetic tag per line, keyed by the line's form key. */
export function previewPayload(
  sent: TagPreviewLineInput[],
  response: TagPreviewResponse,
  /** One-line mode: the tag alone on a page of its own size, upright. */
  single = false,
): TagSheetDesignPayload | null {
  const tags: TagRequestTag[] = sent.map((line) => ({
    id: line.key,
    quantity: 1,
    line: {
      id: line.key,
      line_type: line.line_type,
      product_id: line.product_id,
      product_set_id: line.product_set_id,
      quantity: 1,
      tag_template_id: line.tag_template_id,
    },
  }));
  let seq = 0;
  const templates = response.templates as Record<string, TagTemplate>;
  const newId = () => `preview-${(seq += 1)}`;
  const only = single ? tags[0] : undefined;
  const doc =
    only && templates[only.line.id]
      ? buildSingleTagSheet(only, templates[only.line.id] as TagTemplate, newId)
      : buildRequestSheet(tags, templates, newId);
  if (doc.sheets.every((sheet) => sheet.tags.length === 0)) return null;
  return designPayloadFromResponse({
    doc,
    lines: response.lines,
    assets: response.assets,
    images: response.images,
    fonts: response.fonts,
  });
}

export function PriceTagLivePreview({
  lines,
  priceMode,
  lookupTagPreview,
  docNumber,
  onReadyChange,
  lineKey,
  onClose,
}: Props) {
  const sent = useMemo(
    () =>
      previewLines(
        lineKey === undefined ? lines : lines.filter((l) => l.key === lineKey),
        priceMode,
      ),
    [lines, lineKey, priceMode],
  );
  // Only what changes the drawing re-asks: a remark or a quantity does not.
  const signature = useMemo(() => JSON.stringify([priceMode, sent]), [priceMode, sent]);
  const [payload, setPayload] = useState<TagSheetDesignPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const [missing, setMissing] = useState<string[]>([]);
  // One-line mode: what the resolved tag prints (SP only when it has a selling figure to show).
  const [printsSp, setPrintsSp] = useState(false);
  const codeByKey = useMemo(
    () => Object.fromEntries(lines.map((line) => [line.key, line.code])),
    [lines],
  );
  const codeByKeyRef = useRef(codeByKey);
  codeByKeyRef.current = codeByKey;
  const askSeq = useRef(0);
  const sentRef = useRef(sent);
  sentRef.current = sent;
  const lineKeyRef = useRef(lineKey);
  lineKeyRef.current = lineKey;

  useEffect(() => {
    if (sentRef.current.length === 0) {
      setPayload(null);
      setMissing([]);
      setFailed(false);
      setLoading(false);
      return;
    }
    const ask = (askSeq.current += 1);
    setLoading(true);
    const timer = setTimeout(() => {
      const lines = sentRef.current;
      lookupTagPreview(priceMode, lines)
        .then((response) => {
          if (ask !== askSeq.current) return; // a newer edit is on its way
          setPayload(previewPayload(lines, response, lineKeyRef.current !== undefined));
          const row = response.lines.find((r) => r.line_id === lineKeyRef.current);
          setPrintsSp(!!row && !!row.show_promo_price && row.sell_price != null);
          setMissing(linesWithoutTemplate(lines, response, codeByKeyRef.current));
          setFailed(false);
        })
        .catch(() => {
          if (ask !== askSeq.current) return;
          setFailed(true);
        })
        .finally(() => {
          if (ask === askSeq.current) setLoading(false);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `signature` stands for `sent` + `priceMode`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature, lookupTagPreview]);

  const drawn = !failed && !loading && payload !== null;
  const missingKey = missing.join('|');
  useEffect(() => {
    onReadyChange?.({ missing, drawn: sent.length > 0 && drawn, failed });
    // `missingKey` stands for `missing`: a fresh array with the same codes is no change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [missingKey, drawn, failed, sent.length, onReadyChange]);

  // One line (the row's eye icon): the DesignViewer's own lightbox, straight away - no card, no
  // nested modal. Its header reads the line's code and LP/SP.
  const oneLine = lineKey !== undefined ? lines.find((l) => l.key === lineKey) : undefined;
  const settled = !loading && (failed || payload !== null || sentRef.current.length === 0);
  useEffect(() => {
    if (lineKey === undefined || !settled) return;
    if (failed || payload === null || missing.length > 0) {
      toast.error(failed ? 'The tag preview could not be drawn.' : 'No tag template yet.');
      onClose?.();
    }
    // Fires once per settled answer.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [settled, failed, payload, missing.length]);

  if (sent.length === 0) return null;

  if (lineKey !== undefined) {
    if (!oneLine || failed || payload === null || missing.length > 0) return null;
    return (
      <DesignLightbox
        open
        onOpenChange={(next) => {
          if (!next) onClose?.();
        }}
        title={`${oneLine.code || docNumber || 'Preview'} - ${printsSp ? 'SP' : 'LP'}`}
        payload={payload}
      />
    );
  }

  // Shown under the drawn tags; with nothing drawn at all the empty state says it.
  const missingNote =
    !failed && payload && missing.length > 0 ? (
      <p className="text-sm text-muted-foreground" data-testid="preview-missing">
        No tag template yet for {missing.join(', ')}.
      </p>
    ) : null;

  return (
    <DesignViewer
      title="Preview"
      footer={missingNote}
      docNumber={docNumber || 'Preview'}
      payload={failed ? null : payload}
      loading={loading && payload === null}
      emptyMessage={failed ? 'Preview unavailable' : 'No tag template yet'}
      emptyHint={
        failed
          ? 'The preview could not be drawn.'
          : 'Marketing has not linked a tag template to these items yet.'
      }
    />
  );
}
