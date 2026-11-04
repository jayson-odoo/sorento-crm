'use client';

import * as React from 'react';
import dynamic from 'next/dynamic';
import { EyeOff, RotateCcw, Undo2 } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import ScaledSheet, { PX_PER_MM } from '@/components/dealer-kit/ScaledSheet';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type {
  TagBindingData,
  TagLayer,
} from '@/lib/dealer-kit/tag-template-types';
import { normalizeLayers } from '@/lib/dealer-kit/tag-template-types';
import type { EmbeddedController } from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { cn } from '@/lib/utils';

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
    (Object.keys(FIELD_TOKENS) as EditableField[]).find((f) =>
      FIELD_TOKENS[f].test(text),
    ) ?? null
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

// The designer, loaded only when a page goes live (it is a large module).
const TagCanvasEditor = dynamic(
  () =>
    import('@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor').then(
      (m) => ({
        default: m.TagCanvasEditor,
      }),
    ),
  {
    ssr: false,
    loading: () => <Skeleton className="size-full rounded-none" />,
  },
);

const NOOP = () => undefined;

export interface ReaderPageProps {
  page: SpecSheetPage;
  /** Printed page number, null for a left-out page. */
  number: number | null;
  templateLabel: string;
  /** The box, in CSS px at the current zoom. */
  boxWidth: number;
  boxHeight: number;
  scale: number;
  pageMm: { width_mm: number; height_mm: number };
  /** The still picture's payload: set while the page is in the visible window AND its chunk arrived. */
  payload: TagSheetDesignPayload | null;
  sheetIndex: number | undefined;
  /** This page draws the live designer instead of the still picture (at most 3 pages). */
  live: boolean;
  /** Bumped when the host replaced this page's layers from the server, so the canvas starts over. */
  epoch: number;
  /** The layer selected on THIS page, if any. */
  selectedLayerId: string | null;
  /** The host's local copy of this page's layers, if it has one. */
  draftLayers: TagLayer[] | undefined;
  /** Layers the host set (undo, redo): the canvas adopts them. */
  externalLayers: TagLayer[] | undefined;
  /** Whether this is the page being read: its actions show without hovering. */
  current: boolean;
  /** Medium urls for the page being worked on (the strip keeps thumbnails). */
  sharp: {
    images: Record<string, string>;
    assets: Record<string, string>;
  } | null;
  canEdit: boolean;
  /** Other pages, for the Add accessory options. */
  pages: SpecSheetPage[];
  documentId: string;
  sheetId: string;
  /** Stable across renders (the page passes its own key), so the memoised page skips re-rendering. */
  onPatch: (key: string, change: Partial<SpecSheetPage>) => void;
  onSelectLayer: (key: string, layerId: string | null) => void;
  onLayersReport: (key: string, base: TagLayer[], layers: TagLayer[]) => void;
  controllerRefFor: (
    key: string,
  ) => React.MutableRefObject<EmbeddedController | null>;
}

/** The bound row with the open page's medium pictures swapped in (thumbnails elsewhere). */
function boundWithMedium(
  row: Record<string, unknown>,
  medium: Record<string, string>,
) {
  const swap = (image: unknown) => {
    const entry = image as { attachment_id?: string } | null;
    return entry && entry.attachment_id && medium[entry.attachment_id]
      ? { ...entry, url: medium[entry.attachment_id] }
      : image;
  };
  const parts = (
    (row.parts as Record<string, unknown>[] | undefined) ?? []
  ).map((part) => ({
    ...part,
    images: ((part.images as unknown[] | undefined) ?? []).map(swap),
    drawing: swap(part.drawing),
  }));
  return {
    ...row,
    images: ((row.images as unknown[] | undefined) ?? []).map(swap),
    drawing: swap(row.drawing),
    parts,
    own_parts: parts,
  };
}

/**
 * One page of the stack: a fixed-size box and, on hover or when it is the page being read, its
 * actions (Reset to template, Add accessory, Leave out / Put back). The box is a placeholder until
 * the page is near the viewport; then a still `ScaledSheet` / `TagSheetRenderer` picture, or, for
 * the few pages nearest the reader, the live designer canvas (F4). AREA, COMMENT and the marker
 * are clicked and typed on the page itself; bound product fields stay data.
 */
export const ReaderPage = React.memo(function ReaderPage({
  page,
  number,
  templateLabel,
  boxWidth,
  boxHeight,
  scale,
  pageMm,
  payload,
  sheetIndex,
  live,
  epoch,
  selectedLayerId,
  draftLayers,
  externalLayers,
  current,
  sharp,
  canEdit,
  pages,
  documentId,
  sheetId,
  onPatch,
  onSelectLayer,
  onLayersReport,
  controllerRefFor,
}: ReaderPageProps) {
  const isCover = page.key === COVER;
  const [editing, setEditing] = React.useState<EditableField | null>(null);
  const [draft, setDraft] = React.useState('');
  const [hover, setHover] = React.useState(false);
  // Escape unmounts the input, which can fire its blur: the flag stops that blur from saving.
  const cancelled = React.useRef(false);
  const accessoryId = React.useId();

  const drawn = !page.hidden && payload !== null && sheetIndex !== undefined;
  const tag = drawn ? payload.doc?.sheets[sheetIndex]?.tags[0] : undefined;
  // Read the way the PDF reads them (a layer with no `visible` key is shown), once per payload so
  // the identity the host compares echoes against stays stable.
  const rawLayers = tag?.layers;
  const baseLayers = React.useMemo(
    () => (rawLayers ? normalizeLayers(rawLayers) : undefined),
    [rawLayers],
  );
  const layersNow = draftLayers ?? baseLayers;
  const layersRef = React.useRef(layersNow);
  layersRef.current = layersNow;
  const spots =
    canEdit && layersNow && !isCover
      ? layersNow
          .filter((layer) => layer.visible !== false)
          .map((layer) => ({ layer, field: editableField(layer) }))
          .filter(
            (s): s is { layer: TagLayer; field: EditableField } =>
              s.field !== null,
          )
      : [];
  const px = (mm: number) => mm * PX_PER_MM * scale;

  // The canvas reads its document once, when it mounts; later changes come back through
  // `externalLayers`.
  const liveDoc = React.useMemo(
    () =>
      payload && baseLayers
        ? {
            layers: draftLayers ?? baseLayers,
            width_mm: pageMm.width_mm,
            height_mm: pageMm.height_mm,
          }
        : null,
    // The document is a starting point: only a new payload arriving or a restart replaces it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [payload === null, epoch, pageMm.width_mm, pageMm.height_mm],
  );
  const bound = React.useMemo<TagBindingData | null>(() => {
    const row = payload?.resolvedData?.[page.key] as unknown as
      | Record<string, unknown>
      | undefined;
    if (!row) return null;
    return {
      kind: 'line',
      line: (sharp ? boundWithMedium(row, sharp.images) : row) as never,
    };
  }, [payload, page.key, sharp]);
  const assetUrls = React.useMemo(
    () => ({ ...(payload?.assets ?? {}), ...(sharp?.assets ?? {}) }),
    [payload, sharp],
  );
  const controllerRef = controllerRefFor(page.key);
  const embedded = React.useMemo(
    () => ({
      pxPerMm: scale * PX_PER_MM,
      selectedLayerId,
      onSelect: (layerId: string | null) => onSelectLayer(page.key, layerId),
      layers: externalLayers,
      controllerRef,
      readOnly: !canEdit,
      // A double-click on AREA / COMMENT / marker opens its box; a single click selects it.
      onEditField: (layerId: string) => {
        const layer = layersRef.current?.find((l) => l.id === layerId);
        const field = layer ? editableField(layer) : null;
        if (!field || isCover) return false;
        startRef.current(field);
        return true;
      },
    }),
    [
      scale,
      selectedLayerId,
      onSelectLayer,
      page.key,
      externalLayers,
      controllerRef,
      canEdit,
      isCover,
    ],
  );
  const onLayersChange = React.useCallback(
    (layers: TagLayer[]) => {
      if (liveDoc) onLayersReport(page.key, liveDoc.layers, layers);
    },
    [liveDoc, onLayersReport, page.key],
  );

  const start = (field: EditableField) => {
    cancelled.current = false;
    setDraft(page[field]);
    setEditing(field);
  };
  const startRef = React.useRef(start);
  startRef.current = start;
  const finish = () => {
    if (cancelled.current) return;
    if (editing && draft !== page[editing]) {
      const value = editing === 'area' ? draft.trim().toUpperCase() : draft;
      onPatch(page.key, { [editing]: value } as Partial<SpecSheetPage>);
    }
    setEditing(null);
  };

  // Another page's item with no picks of its own, or one this page already picked.
  const accessoryOptions: SearchableSelectOption[] = [
    ...pages
      .filter(
        (other) =>
          other.key !== COVER &&
          other.key !== page.key &&
          other.picked.length === 0,
      )
      .map((other) => ({
        value: other.key,
        label: `${other.code} ${other.name}`.trim(),
      })),
    ...page.accessories
      .filter((a) => a.source === 'picked' && a.key)
      .map((a) => ({
        value: a.key as string,
        label: `${a.code} ${a.name}`.trim(),
      })),
  ];

  const title = isCover ? 'Cover' : page.code || page.name;
  const showActions = canEdit && (current || hover);

  return (
    <div
      className={`flex shrink-0 flex-col gap-2 ${page.hidden ? 'opacity-60' : ''}`}
      style={{ width: boxWidth }}
      data-page-wrap={page.key}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div
        // A fixed one-line header: the page actions float over its right end, so hovering or
        // selecting a page never re-wraps the header and slides the page out from under the pointer.
        className="relative flex h-8 min-w-0 items-center justify-between gap-2"
      >
        <span
          className="flex min-w-0 items-center gap-1 text-sm"
          data-testid={`spec-sheet-bar-${page.key}`}
        >
          <b className="shrink-0">{number ?? '-'}</b>
          <span className="truncate" title={`${title} - ${templateLabel}`}>
            {title}
            {templateLabel ? ` \u00b7 ${templateLabel}` : ''}
          </span>
          {page.edited && (
            <Badge
              variant="warning"
              appearance="light"
              size="sm"
              className="shrink-0"
            >
              Edited
            </Badge>
          )}
        </span>
        {showActions && (
          <span className="absolute inset-y-0 end-0 flex items-center gap-2 bg-background ps-2">
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
                  onChange={(v: string[]) => onPatch(page.key, { picked: v })}
                  options={accessoryOptions}
                  placeholder="Add accessory"
                />
              </div>
            )}
            {!isCover && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => onPatch(page.key, { hidden: !page.hidden })}
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
        className={`relative overflow-hidden rounded-sm border bg-white shadow-sm ${
          current ? 'border-primary' : 'border-border'
        }`}
        style={{ width: boxWidth, height: boxHeight }}
      >
        {page.hidden ? (
          <div className="flex size-full flex-col items-center justify-center gap-1 bg-muted text-center">
            <h3 className="text-sm font-semibold">
              Left out of the spec sheet
            </h3>
          </div>
        ) : drawn ? (
          <>
            {live && liveDoc ? (
              <div
                className="absolute inset-0"
                data-testid={`spec-page-live-${page.key}`}
              >
                <TagCanvasEditor
                  key={epoch}
                  doc={liveDoc}
                  onChange={NOOP}
                  onLayersChange={onLayersChange}
                  docId={`${sheetId}:${page.key}`}
                  boundData={bound}
                  assetUrls={assetUrls}
                  specSheet
                  embedded={embedded}
                />
              </div>
            ) : (
              <ScaledSheet
                payload={
                  sharp && payload
                    ? {
                        ...payload,
                        images: { ...payload.images, ...sharp.images },
                        assets: assetUrls,
                      }
                    : payload
                }
                sheetIndex={sheetIndex}
                scale={scale}
              />
            )}
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
                  maxLength={
                    field === 'marker' ? 10 : field === 'area' ? 200 : 500
                  }
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
                  className={cn(
                    'rounded-sm outline-dashed outline-1 outline-transparent hover:bg-primary/5 hover:outline-primary focus-visible:outline-primary',
                    // On a live page the pointer goes to the canvas (select, drag; a double-click
                    // opens the box); Tab + Enter still reach the field from the keyboard.
                    live && liveDoc && 'pointer-events-none',
                  )}
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
});
