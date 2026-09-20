'use client';

/**
 * The Arrange half of the request designer (D51).
 *
 * Where the tags PRINT, once they have been designed. The sheet canvas and
 * the sheet tabs are what is left of the old `TagSheetDesigner` - everything
 * about EDITING a tag now happens in the template editor next door, and
 * since S7 there is nothing to CONFIGURE here either: `autoArrange` groups
 * every copy by size and packs each group's own sheets at zero gap inside a
 * fixed 5mm margin, turning a size 90deg when that seats more (or following
 * a grid configured on the template/size, S7). This view is a place to look,
 * not a thing to do - no page/bleed/gap fields, no drag.
 */

import { useCallback, useMemo } from 'react';
import type Konva from 'konva';
import { Loader2, Minus, Plus, Printer } from 'lucide-react';
import type {
  LineTagData,
  PlacedTag,
  TagBindingData,
  TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import type { SheetPlacement } from '@/lib/dealer-kit/request-tags';

// Rendered inside a component the shell loads with ssr:false, so the direct
// react-konva imports are safe.
import { Stage, Layer as KonvaLayer, Group, Rect, Text } from 'react-konva';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';

/** Pixels per mm at 100% zoom. */
const DEFAULT_SCALE = 2.5;
const ZOOM_STEP = 0.1;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;

interface Props {
  doc: TagSheetDoc;
  activeSheetIndex: number;
  onActiveSheetChange: (index: number) => void;
  zoom: number;
  onZoomChange: (zoom: number) => void;
  selectedTagId: string | null;
  onSelectTag: (tagId: string | null) => void;
  /** Resolved line data, keyed by request line id. */
  resolved: Map<string, LineTagData>;
  assetUrls: Record<string, string>;
  onPrintSheet: (sheetIndex: number) => void;
  printing: boolean;
  /** One entry per `doc.sheets` entry, same index (S7, AC-S7-6): what that
   *  sheet's size group resolved to - never stored in the doc. */
  placement: SheetPlacement[];
  /** Template name by id, for the per-sheet line (S7, AC-S7-6). */
  templateNameById: Record<string, string>;
}

export function ArrangeSheetView({
  doc,
  activeSheetIndex,
  onActiveSheetChange,
  zoom,
  onZoomChange,
  selectedTagId,
  onSelectTag,
  resolved,
  assetUrls,
  onPrintSheet,
  printing,
  placement,
  templateNameById,
}: Props) {
  const activeSheet = doc.sheets[activeSheetIndex] ?? doc.sheets[0];
  const activePlacement = placement[activeSheetIndex] ?? null;
  const scale = DEFAULT_SCALE * zoom;
  const pageW = doc.imposition.page_width_mm;
  const pageH = doc.imposition.page_height_mm;
  const canvasWidthPx = pageW * scale;
  const canvasHeightPx = pageH * scale;

  const totalTags = useMemo(
    () => doc.sheets.reduce((sum, sheet) => sum + sheet.tags.length, 0),
    [doc.sheets],
  );

  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      if (e.target === e.target.getStage()) onSelectTag(null);
    },
    [onSelectTag],
  );

  // AC-S7-10: a size that fits the page in neither rotation still gets one
  // overflowing sheet per copy - say so, rather than draw a grid that implies
  // there was ever a choice of how many fit.
  const noFit = activePlacement !== null && activePlacement.capacity === 0;

  const sheetLabel = activePlacement
    ? `${templateNameById[activePlacement.template_id] ?? 'Tag'} - ${activePlacement.cols} x ${activePlacement.rows}, ${activeSheet?.tags.length ?? 0} of ${activePlacement.capacity}`
    : null;

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex h-10 shrink-0 items-center gap-2 border-b bg-background px-3">
        <span className="text-xs text-muted-foreground">
          {doc.sheets.length} sheet{doc.sheets.length === 1 ? '' : 's'} / {totalTags} tag
          {totalTags === 1 ? '' : 's'}
        </span>
        {sheetLabel && (
          <span className="truncate text-xs text-foreground" title={sheetLabel}>
            {sheetLabel}
          </span>
        )}
        <div className="flex-1" />
        <button
          type="button"
          className="rounded p-1 text-muted-foreground hover:bg-accent"
          aria-label="Zoom out"
          onClick={() => onZoomChange(Math.max(MIN_ZOOM, zoom - ZOOM_STEP))}
        >
          <Minus className="size-3.5" />
        </button>
        <span className="w-12 text-center text-xs tabular-nums text-muted-foreground">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          className="rounded p-1 text-muted-foreground hover:bg-accent"
          aria-label="Zoom in"
          onClick={() => onZoomChange(Math.min(MAX_ZOOM, zoom + ZOOM_STEP))}
        >
          <Plus className="size-3.5" />
        </button>
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Sheet canvas */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-auto bg-muted/30">
            {noFit ? (
              // AC-S7-10: the page cannot hold even one copy of this size at
              // its current size in either rotation - nothing to arrange, so
              // say why instead of drawing an empty page.
              <div className="flex h-full min-h-full flex-col items-center justify-center gap-1.5 p-8 text-center">
                <p className="text-sm font-medium">No tag fits this page</p>
                <p className="max-w-xs text-xs text-muted-foreground">
                  {activePlacement!.width_mm} x {activePlacement!.height_mm} mm needs more usable
                  space than {pageW} x {pageH} mm leaves after the printable margin. Shrink the tag
                  to fit.
                </p>
              </div>
            ) : (
              <div className="inline-block min-h-full min-w-full p-6">
                <div
                  className="relative mx-auto shadow-lg"
                  style={{ width: canvasWidthPx, height: canvasHeightPx }}
                >
                  <Stage
                    width={canvasWidthPx}
                    height={canvasHeightPx}
                    onClick={handleStageClick}
                    onTap={handleStageClick}
                  >
                    <KonvaLayer>
                      <Rect
                        x={0}
                        y={0}
                        width={canvasWidthPx}
                        height={canvasHeightPx}
                        fill="#ffffff"
                        stroke="#d4d4d8"
                        strokeWidth={1}
                      />

                      {doc.imposition.bleed_mm > 0 && (
                        <Rect
                          x={doc.imposition.bleed_mm * scale}
                          y={doc.imposition.bleed_mm * scale}
                          width={(pageW - 2 * doc.imposition.bleed_mm) * scale}
                          height={(pageH - 2 * doc.imposition.bleed_mm) * scale}
                          stroke="#e5e7eb"
                          strokeWidth={0.5}
                          dash={[6, 4]}
                          listening={false}
                        />
                      )}

                      {(activeSheet?.tags ?? []).map((tag) => (
                        <TagOnCanvas
                          key={tag.id}
                          tag={tag}
                          scale={scale}
                          isSelected={selectedTagId === tag.id}
                          resolvedData={resolved.get(tag.request_tag_id) ?? null}
                          assetUrls={assetUrls}
                          onSelect={onSelectTag}
                        />
                      ))}
                    </KonvaLayer>
                  </Stage>
                </div>
              </div>
            )}
          </div>

          {/* Sheet tabs */}
          <div className="flex h-9 shrink-0 items-center gap-1 border-t bg-background px-3">
            {doc.sheets.map((sheet, index) => (
              <button
                key={sheet.id}
                type="button"
                className={`rounded px-2.5 py-1 text-xs transition-colors ${
                  index === activeSheetIndex
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:bg-muted'
                }`}
                onClick={() => {
                  onActiveSheetChange(index);
                  onSelectTag(null);
                }}
              >
                Sheet {index + 1}
              </button>
            ))}
            <div className="flex-1" />
            {activeSheet && (
              <button
                type="button"
                className="flex items-center gap-1 rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted"
                disabled={printing}
                onClick={() => onPrintSheet(activeSheetIndex)}
              >
                {printing ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Printer className="size-3" />
                )}
                Print sheet {activeSheetIndex + 1}
              </button>
            )}
            <span className="text-xs text-muted-foreground">
              {activeSheet?.tags.length ?? 0} on this sheet
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// One placed tag on the sheet
// ---------------------------------------------------------------------------

function TagOnCanvas({
  tag,
  scale,
  isSelected,
  resolvedData,
  assetUrls,
  onSelect,
}: {
  tag: PlacedTag;
  scale: number;
  isSelected: boolean;
  resolvedData: LineTagData | null;
  assetUrls: Record<string, string>;
  onSelect: (tagId: string) => void;
}) {
  const x = tag.x_mm * scale;
  const y = tag.y_mm * scale;
  // The tag's own NATURAL (unrotated) footprint - what its layers are laid
  // out against - not the placed box (S7): rotation is a transform of this
  // whole group, the same as `TagSheetRenderer` on the print page.
  const w = tag.width_mm * scale;
  const h = tag.height_mm * scale;
  const rotated = tag.rotation === 90;

  const handleClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      e.cancelBubble = true;
      onSelect(tag.id);
    },
    [onSelect, tag.id],
  );

  const sortedLayers = useMemo(
    () => [...tag.layers].sort((a, b) => a.z_index - b.z_index),
    [tag.layers],
  );

  // The tag's layers resolve against the LINE, so a marketing override on it
  // shows here exactly as it will print.
  const bindingData: TagBindingData | null = resolvedData
    ? { kind: 'line', line: resolvedData }
    : null;

  return (
    <Group
      x={x}
      y={y}
      width={w}
      height={h}
      rotation={rotated ? 90 : 0}
      offsetX={0}
      offsetY={rotated ? h : 0}
      onClick={handleClick}
      onTap={handleClick}
      clipFunc={(ctx: Konva.Context) => {
        ctx.rect(0, 0, w, h);
      }}
    >
      <Rect
        x={0}
        y={0}
        width={w}
        height={h}
        fill="#ffffff"
        stroke={isSelected ? '#3b82f6' : '#d4d4d8'}
        strokeWidth={isSelected ? 2 : 0.5}
      />

      {sortedLayers
        .filter((l) => l.visible)
        .map((layer) => (
          <KonvaTagLayer
            key={layer.id}
            layer={layer}
            scale={scale}
            display={layerDisplay(layer, bindingData, assetUrls)}
            // A placed tag is ONE object on the sheet: its layers are read-only
            // here, so they neither drag nor swallow the click that selects the
            // tag around them. Editing happens in the Design half.
            draggable={false}
            listening={false}
          />
        ))}

      {resolvedData && (
        <Text
          x={2}
          y={h - 12 * (scale / DEFAULT_SCALE)}
          width={w - 4}
          height={12 * (scale / DEFAULT_SCALE)}
          text={resolvedData.code}
          fontSize={8 * (scale / DEFAULT_SCALE)}
          fill="#666666"
          align="center"
          fontFamily="DM Sans"
        />
      )}
    </Group>
  );
}
