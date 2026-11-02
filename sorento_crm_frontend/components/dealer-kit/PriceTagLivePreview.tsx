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
import { buildRequestSheet, type TagRequestTag } from '@/lib/dealer-kit/request-tags';
import { designPayloadFromResponse, type TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type { DraftLine } from '@/lib/dealer-kit/price-tag-draft-lines';
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
}

/** The lines worth drawing, in the shape the preview route reads. */
export function previewLines(lines: DraftLine[]): TagPreviewLineInput[] {
  return lines
    .filter((l) => (l.line_type === 'product' ? !!l.product_id : !!l.product_set_id))
    .map((l) => ({
      key: l.key,
      line_type: l.line_type,
      product_id: l.line_type === 'product' ? l.product_id : null,
      product_set_id: l.line_type === 'product_set' ? l.product_set_id : null,
      combo_id: l.combo_id,
      parts: l.parts.map((part) => ({
        product_id: part.product_id,
        role: part.role,
        candidates: part.product_id ? [] : part.candidates.map((c) => c.product_id),
      })),
      promotion_id: l.promotion_id,
      manual_sell_price: l.manual_sell_price,
      tag_template_id: l.line_type === 'product' ? (l.tag_template_id ?? null) : null,
    }));
}

/** The response, drawn: one synthetic tag per line, keyed by the line's form key. */
export function previewPayload(
  sent: TagPreviewLineInput[],
  response: TagPreviewResponse,
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
  const doc = buildRequestSheet(
    tags,
    response.templates as Record<string, TagTemplate>,
    () => `preview-${(seq += 1)}`,
  );
  if (doc.sheets.every((sheet) => sheet.tags.length === 0)) return null;
  return designPayloadFromResponse({
    doc,
    lines: response.lines,
    assets: response.assets,
    images: response.images,
    fonts: response.fonts,
  });
}

export function PriceTagLivePreview({ lines, priceMode, lookupTagPreview, docNumber }: Props) {
  const sent = useMemo(() => previewLines(lines), [lines]);
  // Only what changes the drawing re-asks: a remark or a quantity does not.
  const signature = useMemo(() => JSON.stringify([priceMode, sent]), [priceMode, sent]);
  const [payload, setPayload] = useState<TagSheetDesignPayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const askSeq = useRef(0);
  const sentRef = useRef(sent);
  sentRef.current = sent;

  useEffect(() => {
    if (sentRef.current.length === 0) {
      setPayload(null);
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
          setPayload(previewPayload(lines, response));
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

  if (sent.length === 0) return null;

  return (
    <DesignViewer
      title="Preview"
      docNumber={docNumber || 'Preview'}
      payload={failed ? null : payload}
      loading={loading && payload === null}
      emptyMessage={failed ? 'Preview unavailable' : 'No tag template yet'}
      emptyHint={
        failed
          ? 'The preview could not be drawn. Your request is not affected.'
          : 'Marketing has not published a tag template these items can use.'
      }
    />
  );
}
