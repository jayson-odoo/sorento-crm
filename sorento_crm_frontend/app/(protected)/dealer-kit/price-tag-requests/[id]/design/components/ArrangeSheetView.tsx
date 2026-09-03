'use client';

/**
 * The Arrange half of the request designer (D51).
 *
 * Where the tags PRINT, once they have been designed. The sheet canvas, the
 * sheet tabs and the imposition controls are the parts of the old
 * `TagSheetDesigner` worth keeping: everything about EDITING a tag now happens
 * in the template editor next door, so a tag here is an object on a page that
 * can be nudged and nothing else.
 *
 * The arrangement itself is computed (`autoArrange`), auto-fit off the tag's
 * own size (S6, D8) - there is no preset to pick, only the page/bleed/gap and
 * a read-only "C x R = N per sheet" line - so this view is normally something
 * to glance at rather than something to do. A tag somebody drags is pinned by
 * the host and survives the next re-arrange.
 */

import { useCallback, useMemo } from 'react';
import type Konva from 'konva';
import { Loader2, Minus, Plus, Printer } from 'lucide-react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import type {
  ImpositionConfig,
  ImpositionPreset,
  LineTagData,
  PlacedTag,
  TagBindingData,
  TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { layerDisplay } from '@/lib/dealer-kit/product-block';
import { impositionFit } from '@/lib/dealer-kit/request-tags';

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
  onImpositionChange: (imposition: ImpositionConfig) => void;
  onMoveTag: (sheetIndex: number, tag: PlacedTag, x_mm: number, y_mm: number) => void;
  onPrintSheet: (sheetIndex: number) => void;
  printing: boolean;
  /**
   * The size the fit line and grid are computed off: the largest of every
   * line's tag, REQUESTED rather than placed (S6). `doc.sheets` cannot answer
   * this on its own - when the page is too small for the tag at all,
   * `autoArrange` seats zero unpinned copies, so reading the size off what
   * got placed would go blank exactly when AC-S6-3's "0 per sheet" message
   * most needs a size to quote. Null before any line has a tag yet.
   */
  tagDims: { width_mm: number; height_mm: number } | null;
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
  onImpositionChange,
  onMoveTag,
  onPrintSheet,
  printing,
  tagDims,
}: Props) {
  const activeSheet = doc.sheets[activeSheetIndex] ?? doc.sheets[0];
  const scale = DEFAULT_SCALE * zoom;
  const pageW = doc.imposition.page_width_mm;
  const pageH = doc.imposition.page_height_mm;
  const canvasWidthPx = pageW * scale;
  const canvasHeightPx = pageH * scale;

  const totalTags = useMemo(
    () => doc.sheets.reduce((sum, sheet) => sum + sheet.tags.length, 0),
    [doc.sheets],
  );

  const fit = useMemo(() => {
    if (!tagDims) return null;
    return impositionFit(
      doc.imposition.page_width_mm,
      doc.imposition.page_height_mm,
      doc.imposition.bleed_mm,
      doc.imposition.gap_mm,
      tagDims.width_mm,
      tagDims.height_mm,
    );
  }, [doc.imposition, tagDims]);

  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      if (e.target === e.target.getStage()) onSelectTag(null);
    },
    [onSelectTag],
  );

  const handleField = useCallback(
    (field: keyof ImpositionConfig, value: number) => {
      onImpositionChange({
        ...doc.imposition,
        [field]: value,
        preset: 'custom' as ImpositionPreset,
      });
    },
    [doc.imposition, onImpositionChange],
  );

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar */}
      <div className="flex h-10 shrink-0 items-center gap-2 border-b bg-background px-3">
        <span className="text-xs text-muted-foreground">
          {doc.sheets.length} sheet{doc.sheets.length === 1 ? '' : 's'} / {totalTags} tag
          {totalTags === 1 ? '' : 's'}
        </span>
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
            {fit && fit.perSheet === 0 ? (
              // AC-S6-3: the page cannot hold even one tag at its current
              // size - nothing to arrange, so say why instead of drawing an
              // empty page.
              <div className="flex h-full min-h-full flex-col items-center justify-center gap-1.5 p-8 text-center">
                <p className="text-sm font-medium">No tag fits this page</p>
                <p className="max-w-xs text-xs text-muted-foreground">
                  {tagDims!.width_mm} x {tagDims!.height_mm} mm needs more usable space than{' '}
                  {pageW} x {pageH} mm leaves after a {doc.imposition.bleed_mm}mm bleed. Grow the
                  page or shrink the bleed/gap.
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
                          resolvedData={resolved.get(tag.request_line_id) ?? null}
                          assetUrls={assetUrls}
                          onSelect={onSelectTag}
                          onDragEnd={(xPx, yPx) =>
                            onMoveTag(activeSheetIndex, tag, xPx / scale, yPx / scale)
                          }
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

        {/* Imposition */}
        <div className="hidden w-60 shrink-0 border-l bg-background lg:block">
          <div className="space-y-2 px-3 py-3">
            <h3 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              Imposition
            </h3>

            <div className="grid grid-cols-2 gap-1.5">
              <div>
                <Label className="text-[10px] text-muted-foreground">Page W (mm)</Label>
                <Input
                  type="number"
                  className="mt-0.5 h-7 text-xs"
                  value={doc.imposition.page_width_mm}
                  onChange={(e) => handleField('page_width_mm', Number(e.target.value))}
                />
              </div>
              <div>
                <Label className="text-[10px] text-muted-foreground">Page H (mm)</Label>
                <Input
                  type="number"
                  className="mt-0.5 h-7 text-xs"
                  value={doc.imposition.page_height_mm}
                  onChange={(e) => handleField('page_height_mm', Number(e.target.value))}
                />
              </div>
              <div>
                <Label className="text-[10px] text-muted-foreground">Bleed (mm)</Label>
                <Input
                  type="number"
                  className="mt-0.5 h-7 text-xs"
                  value={doc.imposition.bleed_mm}
                  onChange={(e) => handleField('bleed_mm', Number(e.target.value))}
                />
              </div>
              <div>
                <Label className="text-[10px] text-muted-foreground">Gap (mm)</Label>
                <Input
                  type="number"
                  className="mt-0.5 h-7 text-xs"
                  value={doc.imposition.gap_mm}
                  onChange={(e) => handleField('gap_mm', Number(e.target.value))}
                />
              </div>
            </div>

            {/* Auto-fit (S6, D8): nothing to choose, just what the tag's own
                size fits on this page. */}
            <div className="rounded-md bg-muted px-2.5 py-2 text-xs">
              {fit ? (
                <>
                  <p className="font-medium">
                    {fit.cols} x {fit.rows} = {fit.perSheet} per sheet
                  </p>
                  <p className="mt-0.5 text-muted-foreground">
                    {totalTags} tag{totalTags === 1 ? '' : 's'} of {tagDims!.width_mm} x{' '}
                    {tagDims!.height_mm} mm, {doc.sheets.length} sheet
                    {doc.sheets.length === 1 ? '' : 's'}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">Add a tag to see how many fit per sheet.</p>
              )}
            </div>
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
  onDragEnd,
}: {
  tag: PlacedTag;
  scale: number;
  isSelected: boolean;
  resolvedData: LineTagData | null;
  assetUrls: Record<string, string>;
  onSelect: (tagId: string) => void;
  onDragEnd: (xPx: number, yPx: number) => void;
}) {
  const x = tag.x_mm * scale;
  const y = tag.y_mm * scale;
  const w = tag.width_mm * scale;
  const h = tag.height_mm * scale;

  const handleClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      e.cancelBubble = true;
      onSelect(tag.id);
    },
    [onSelect, tag.id],
  );

  const handleDragEnd = useCallback(
    (e: Konva.KonvaEventObject<DragEvent>) => {
      onDragEnd(e.target.x(), e.target.y());
    },
    [onDragEnd],
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
      draggable
      onClick={handleClick}
      onTap={handleClick}
      onDragEnd={handleDragEnd}
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
