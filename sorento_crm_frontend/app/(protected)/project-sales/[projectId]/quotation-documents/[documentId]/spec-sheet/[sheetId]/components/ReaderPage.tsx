'use client';

import * as React from 'react';
import Link from 'next/link';
import { EyeOff, Pencil, RotateCcw, Undo2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import ScaledSheet, { PX_PER_MM } from '@/components/dealer-kit/ScaledSheet';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';
import { useDeferredAction } from '@/hooks/useDeferredAction';

import {
  specSheetDetailKey,
  specSheetListKey,
  specSheetPreviewPrefix,
} from '../../../../../../_shared/hooks/useSpecSheet';
import type { SpecSheetPage } from '../../../../../../_shared/services/specSheetService';

export const COVER = 'cover';

/** Which page field a text layer prints, if it is one a page may type over. */
type EditableField = 'area' | 'comment' | 'marker';
const FIELD_TOKENS: Record<EditableField, RegExp> = {
  area: /\{\{\s*line\.area\s*\}\}/,
  comment: /\{\{\s*line\.comment\s*\}\}/,
  marker: /\{\{\s*line\.marker\s*\}\}/,
};
const FIELD_LABELS: Record<EditableField, string> = {
  area: 'Area',
  comment: 'Comment',
  marker: 'Marker',
};

function editableField(layer: TagLayer): EditableField | null {
  if (layer.props.kind !== 'text') return null;
  const text = layer.text_override ?? layer.props.text ?? '';
  return (
    (Object.keys(FIELD_TOKENS) as EditableField[]).find((f) => FIELD_TOKENS[f].test(text)) ?? null
  );
}

export function ResetPageButton({
  documentId,
  sheetId,
  pageKey,
  code,
  onReset,
}: {
  documentId: string;
  sheetId: string;
  pageKey: string;
  code: string;
  /** Said once the server has applied it. */
  onReset?: () => void;
}) {
  const reset = useDeferredAction({
    actionKey: 'quotation_spec_sheet.reset_page',
    entityType: 'quotation_spec_sheet',
    entityId: sheetId,
    verb: 'Resetting',
    subject: code || 'page',
    surface: 'inline',
    successMessage: 'Page reset to the template',
    payload: { page_key: pageKey },
    invalidateKeys: [
      specSheetDetailKey(documentId, sheetId),
      specSheetPreviewPrefix(documentId, sheetId),
      specSheetListKey(documentId),
    ],
    countdownClassName: 'min-w-0',
    onCommitted: onReset,
  });
  return (
    reset.countdown ?? (
      <Button
        size="sm"
        variant="outline"
        disabled={reset.isPending || reset.isBlocked}
        onClick={() => reset.start()}
      >
        <Undo2 className="size-4" aria-hidden />
        Reset to template
      </Button>
    )
  );
}

export interface ReaderPageProps {
  page: SpecSheetPage;
  /** Printed page number, null for a left-out page. */
  number: number | null;
  templateLabel: string;
  /** The box, in CSS px at the current zoom. */
  boxWidth: number;
  boxHeight: number;
  scale: number;
  /** The page is in the visible window AND its preview has arrived. */
  payload: TagSheetDesignPayload | null;
  sheetIndex: number | undefined;
  canEdit: boolean;
  editDisabledReason?: string;
  editHref: string;
  /** Other pages, for the Add accessory options. */
  pages: SpecSheetPage[];
  documentId: string;
  sheetId: string;
  onPatch: (change: Partial<SpecSheetPage>) => void;
}

/**
 * One page of the stack: its bar (Edit page, Reset to template, Add accessory, Leave out / Put
 * back) and a fixed-size box. The box is a placeholder until the page is near the viewport; only
 * then does `ScaledSheet` / `TagSheetRenderer` mount inside it. AREA, COMMENT and the marker are
 * clicked and typed on the page itself, as they were in the single-page tab.
 */
export function ReaderPage({
  page,
  number,
  templateLabel,
  boxWidth,
  boxHeight,
  scale,
  payload,
  sheetIndex,
  canEdit,
  editDisabledReason,
  editHref,
  pages,
  documentId,
  sheetId,
  onPatch,
}: ReaderPageProps) {
  const isCover = page.key === COVER;
  const [editing, setEditing] = React.useState<EditableField | null>(null);
  const [draft, setDraft] = React.useState('');
  // Escape unmounts the input, which can fire its blur: the flag stops that blur from saving.
  const cancelled = React.useRef(false);
  const accessoryId = React.useId();

  const drawn = !page.hidden && payload !== null && sheetIndex !== undefined;
  const tag = drawn ? payload.doc?.sheets[sheetIndex]?.tags[0] : undefined;
  const spots =
    canEdit && tag && !isCover
      ? tag.layers
          .filter((layer) => layer.visible !== false)
          .map((layer) => ({ layer, field: editableField(layer) }))
          .filter((s): s is { layer: TagLayer; field: EditableField } => s.field !== null)
      : [];
  const px = (mm: number) => mm * PX_PER_MM * scale;

  const start = (field: EditableField) => {
    cancelled.current = false;
    setDraft(page[field]);
    setEditing(field);
  };
  const finish = () => {
    if (cancelled.current) return;
    if (editing && draft !== page[editing]) {
      const value = editing === 'area' ? draft.trim().toUpperCase() : draft;
      onPatch({ [editing]: value } as Partial<SpecSheetPage>);
    }
    setEditing(null);
  };

  // Another page's item with no picks of its own, or one this page already picked.
  const accessoryOptions: SearchableSelectOption[] = [
    ...pages
      .filter((other) => other.key !== COVER && other.key !== page.key && other.picked.length === 0)
      .map((other) => ({ value: other.key, label: `${other.code} ${other.name}`.trim() })),
    ...page.accessories
      .filter((a) => a.source === 'picked' && a.key)
      .map((a) => ({ value: a.key as string, label: `${a.code} ${a.name}`.trim() })),
  ];

  const title = isCover ? 'Cover' : page.code || page.name;

  return (
    <div
      className={`flex shrink-0 flex-col gap-2 ${page.hidden ? 'opacity-60' : ''}`}
      style={{ width: boxWidth }}
      data-page-wrap={page.key}
    >
      <div className="flex min-w-0 flex-wrap items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1 text-sm" data-testid={`spec-sheet-bar-${page.key}`}>
          <b className="shrink-0">{number ?? '-'}</b>
          <span className="truncate" title={`${title} - ${templateLabel}`}>
            {title}
            {templateLabel ? ` · ${templateLabel}` : ''}
          </span>
          {page.edited && (
            <Badge variant="warning" appearance="light" size="sm" className="shrink-0">
              Edited
            </Badge>
          )}
        </span>
        {canEdit && (
          <span className="flex flex-wrap items-center gap-2">
            {!page.hidden &&
              (editDisabledReason ? (
                <span title={editDisabledReason} className="inline-flex">
                  <Button size="sm" variant="outline" disabled>
                    <Pencil className="size-4" aria-hidden />
                    Edit page
                  </Button>
                </span>
              ) : (
                <Button size="sm" variant="outline" asChild>
                  <Link href={editHref}>
                    <Pencil className="size-4" aria-hidden />
                    Edit page
                  </Link>
                </Button>
              ))}
            {page.edited && (
              <ResetPageButton
                documentId={documentId}
                sheetId={sheetId}
                pageKey={page.key}
                code={isCover ? 'Cover' : page.code}
              />
            )}
            {!isCover && !page.hidden && (
              <div className="w-48 min-w-0">
                <Label htmlFor={accessoryId} className="sr-only">
                  Add accessory
                </Label>
                <SearchableMultiSelect
                  id={accessoryId}
                  size="sm"
                  value={page.picked}
                  onChange={(v: string[]) => onPatch({ picked: v })}
                  options={accessoryOptions}
                  placeholder="Add accessory"
                />
              </div>
            )}
            {!isCover && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onPatch({ hidden: !page.hidden })}
                data-testid={`spec-sheet-leave-out-${page.key}`}
              >
                {page.hidden ? (
                  <RotateCcw className="size-4" aria-hidden />
                ) : (
                  <EyeOff className="size-4" aria-hidden />
                )}
                {page.hidden ? 'Put back' : 'Leave out'}
              </Button>
            )}
          </span>
        )}
      </div>

      <div
        // The observed box: one fixed-size placeholder per page.
        data-testid={`spec-page-${page.key}`}
        data-page-key={page.key}
        className="relative overflow-hidden rounded-sm border border-border bg-white shadow-sm"
        style={{ width: boxWidth, height: boxHeight }}
      >
        {page.hidden ? (
          <div className="flex size-full flex-col items-center justify-center gap-1 bg-muted text-center">
            <h3 className="text-sm font-semibold">Left out of the spec sheet</h3>
          </div>
        ) : drawn ? (
          <>
            <ScaledSheet payload={payload} sheetIndex={sheetIndex} scale={scale} />
            {spots.map(({ layer, field }) => {
              const style: React.CSSProperties = {
                position: 'absolute',
                left: px(layer.x_mm),
                top: px(layer.y_mm),
                width: px(layer.width_mm),
                height: Math.max(px(layer.height_mm), 20),
              };
              return editing === field ? (
                <Input
                  key={layer.id}
                  autoFocus
                  aria-label={FIELD_LABELS[field]}
                  value={draft}
                  maxLength={field === 'marker' ? 10 : field === 'area' ? 200 : 500}
                  onChange={(e) => setDraft(e.target.value)}
                  onBlur={finish}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') finish();
                    if (e.key === 'Escape') {
                      cancelled.current = true;
                      setEditing(null);
                    }
                  }}
                  style={style}
                  className="h-auto rounded-sm bg-background px-1 py-0 text-xs"
                />
              ) : (
                <button
                  key={layer.id}
                  type="button"
                  aria-label={`Edit ${FIELD_LABELS[field]}`}
                  title={`Edit ${FIELD_LABELS[field]}`}
                  onClick={() => start(field)}
                  style={style}
                  className="rounded-sm outline-dashed outline-1 outline-transparent hover:bg-primary/5 hover:outline-primary focus-visible:outline-primary"
                />
              );
            })}
          </>
        ) : (
          <Skeleton className="size-full rounded-none" />
        )}
      </div>
    </div>
  );
}
