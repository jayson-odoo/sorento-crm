'use client';

/**
 * Tag sheet designer: the main layout composing request lines, an A4 canvas,
 * and an inspector/imposition sidebar.
 *
 * LEFT PANEL: request lines with drag handles; placed lines show a checkmark.
 * CENTER: sheet canvas at A4 mm scale with placed tags rendered via
 *   KonvaTagLayer from S3. Sheet tabs at bottom.
 * RIGHT PANEL: selected tag inspector (template, line, resolved data, remove)
 *   plus imposition controls.
 * TOP TOOLBAR: save, mark proof ready, zoom.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import type Konva from 'konva';
import {
  Check,
  ChevronLeft,
  Eye,
  GripVertical,
  Loader2,
  Minus,
  Plus,
  Printer,
  Save,
  Trash2,
  X,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type {
  GroupBinding,
  ImpositionConfig,
  ImpositionPreset,
  LineTagData,
  PlacedTag,
  TagBindingData,
  TagLayer,
  TagSheet,
  TagSheetDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { IMPOSITION_PRESETS } from '@/lib/dealer-kit/tag-template-types';
import { formatTagPrice } from '@/lib/dealer-kit/price-badge';
import { bindTemplateLayers, layerDisplay } from '@/lib/dealer-kit/product-block';
import { useKitLibrary } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import {
  resolveRequestLines,
  transitionPriceTagRequest,
  exportTagSheet,
  type PriceTagRequestDetail,
  type PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import { listTemplates } from '../../../../services/tagTemplateService';
import type { TagTemplate } from '@/lib/dealer-kit/tag-template-types';
import { lineFamily } from '@/lib/dealer-kit/line-family';

// This component is loaded with ssr:false by TagSheetDesignerShell, so direct imports are safe.
import { Stage, Layer as KonvaLayer, Group, Rect, Text } from 'react-konva';
import { KonvaTagLayer } from '@/app/(protected)/dealer-kit/tag-templates/components/KonvaTagLayer';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DEFAULT_SCALE = 2.5; // px per mm at 100% zoom
const ZOOM_STEP = 0.1;
const MIN_ZOOM = 0.25;
const MAX_ZOOM = 3;

let _idSeq = 0;
function uid(prefix: string): string {
  _idSeq += 1;
  return `${prefix}-${Date.now()}-${_idSeq}`;
}

// ---------------------------------------------------------------------------
// Imposition layout helpers
// ---------------------------------------------------------------------------

interface LayoutSlot {
  x_mm: number;
  y_mm: number;
}

function computeImpositionSlots(
  imposition: ImpositionConfig,
  tagW: number,
  tagH: number,
): LayoutSlot[] {
  const { page_width_mm, page_height_mm, bleed_mm, gap_mm, preset } = imposition;
  const usableW = page_width_mm - 2 * bleed_mm;
  const usableH = page_height_mm - 2 * bleed_mm;

  if (preset === 'a4_3up') {
    // 1 column, 3 rows, centered horizontally.
    const startX = bleed_mm + (usableW - tagW) / 2;
    const totalH = 3 * tagH + 2 * gap_mm;
    const startY = bleed_mm + (usableH - totalH) / 2;
    return [
      { x_mm: startX, y_mm: startY },
      { x_mm: startX, y_mm: startY + tagH + gap_mm },
      { x_mm: startX, y_mm: startY + 2 * (tagH + gap_mm) },
    ];
  }

  if (preset === 'a4_2x2') {
    // 2 columns, 2 rows, centered.
    const totalW = 2 * tagW + gap_mm;
    const totalH = 2 * tagH + gap_mm;
    const startX = bleed_mm + (usableW - totalW) / 2;
    const startY = bleed_mm + (usableH - totalH) / 2;
    return [
      { x_mm: startX, y_mm: startY },
      { x_mm: startX + tagW + gap_mm, y_mm: startY },
      { x_mm: startX, y_mm: startY + tagH + gap_mm },
      { x_mm: startX + tagW + gap_mm, y_mm: startY + tagH + gap_mm },
    ];
  }

  // Custom: single tag centered.
  return [
    { x_mm: bleed_mm + (usableW - tagW) / 2, y_mm: bleed_mm + (usableH - tagH) / 2 },
  ];
}

// ---------------------------------------------------------------------------
// Determine product family from line (mock heuristic)
// ---------------------------------------------------------------------------


// ---------------------------------------------------------------------------
// Component props
// ---------------------------------------------------------------------------

interface TagSheetDesignerProps {
  request: PriceTagRequestDetail;
  initialDoc: TagSheetDoc | null;
  onSave: (doc: TagSheetDoc) => Promise<void>;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TagSheetDesigner({
  request,
  initialDoc,
  onSave,
}: TagSheetDesignerProps) {
  const router = useRouter();

  // -- Doc state ---------------------------------------------------------------

  const defaultImposition: ImpositionConfig = {
    preset: 'a4_3up',
    ...IMPOSITION_PRESETS.a4_3up,
  };

  const [doc, setDoc] = useState<TagSheetDoc>(
    initialDoc ?? {
      kind: 'tag_sheet',
      imposition: defaultImposition,
      sheets: [{ id: uid('s'), tags: [] }],
    },
  );

  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [saving, setSaving] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [exportingSheet, setExportingSheet] = useState(false);
  const [templates, setTemplates] = useState<TagTemplate[]>([]);

  // Signed URLs for library artwork placed on a template (badges, icons).
  const library = useKitLibrary();

  const stageRef = useRef<Konva.Stage | null>(null);

  // Load templates on mount.
  useEffect(() => {
    listTemplates().then(setTemplates);
  }, []);

  // -- Derived state -----------------------------------------------------------

  const activeSheet: TagSheet | undefined = doc.sheets[activeSheetIndex];
  const scale = DEFAULT_SCALE * zoom;
  const pageW = doc.imposition.page_width_mm;
  const pageH = doc.imposition.page_height_mm;
  const canvasWidthPx = pageW * scale;
  const canvasHeightPx = pageH * scale;

  // Set of request_line_ids already placed on any sheet.
  const placedLineIds = useMemo(() => {
    const ids = new Set<string>();
    for (const sheet of doc.sheets) {
      for (const tag of sheet.tags) {
        ids.add(tag.request_line_id);
      }
    }
    return ids;
  }, [doc.sheets]);

  // Resolved data, keyed by line id, from the pricing engine.
  //
  // Fetched rather than derived: prices live nowhere in the document (ADR
  // 0008), and the promotion window, the audience gate and the marketing
  // override are all decisions the backend owns.
  const [resolvedRows, setResolvedRows] = useState<LineTagData[]>([]);

  useEffect(() => {
    let live = true;
    resolveRequestLines(request.id)
      .then((rows) => {
        if (live) setResolvedRows(rows);
      })
      .catch((error: unknown) => {
        toast.error(
          error instanceof Error ? error.message : 'Failed to resolve prices',
        );
      });
    return () => {
      live = false;
    };
  }, [request.id]);

  const resolvedDataMap = useMemo(() => {
    const map = new Map<string, LineTagData>();
    for (const row of resolvedRows) map.set(row.line_id, row);
    return map;
  }, [resolvedRows]);

  const selectedTag = useMemo(() => {
    if (!selectedTagId || !activeSheet) return null;
    return activeSheet.tags.find((t) => t.id === selectedTagId) ?? null;
  }, [selectedTagId, activeSheet]);

  const selectedLine = useMemo(() => {
    if (!selectedTag) return null;
    return request.lines.find((l) => l.id === selectedTag.request_line_id) ?? null;
  }, [selectedTag, request.lines]);

  const selectedResolved = useMemo(() => {
    if (!selectedTag) return null;
    return resolvedDataMap.get(selectedTag.request_line_id) ?? null;
  }, [selectedTag, resolvedDataMap]);

  // -- Sheet mutations ---------------------------------------------------------

  const updateDoc = useCallback((updater: (prev: TagSheetDoc) => TagSheetDoc) => {
    setDoc((prev) => updater(prev));
  }, []);

  const updateActiveSheet = useCallback(
    (updater: (sheet: TagSheet) => TagSheet) => {
      updateDoc((prev) => ({
        ...prev,
        sheets: prev.sheets.map((s, i) =>
          i === activeSheetIndex ? updater(s) : s,
        ),
      }));
    },
    [activeSheetIndex, updateDoc],
  );

  const addSheet = useCallback(() => {
    const newSheet: TagSheet = { id: uid('s'), tags: [] };
    updateDoc((prev) => ({
      ...prev,
      sheets: [...prev.sheets, newSheet],
    }));
    setActiveSheetIndex(doc.sheets.length);
    setSelectedTagId(null);
  }, [doc.sheets.length, updateDoc]);

  const removeSheet = useCallback(
    (index: number) => {
      if (doc.sheets.length <= 1) return;
      updateDoc((prev) => ({
        ...prev,
        sheets: prev.sheets.filter((_, i) => i !== index),
      }));
      if (activeSheetIndex >= doc.sheets.length - 1) {
        setActiveSheetIndex(Math.max(0, doc.sheets.length - 2));
      }
      setSelectedTagId(null);
    },
    [doc.sheets.length, activeSheetIndex, updateDoc],
  );

  // -- Drop a line onto the sheet ----------------------------------------------

  const handleDropLine = useCallback(
    async (line: PriceTagRequestLine) => {
      if (placedLineIds.has(line.id)) {
        toast.info('This line is already placed on a sheet.');
        return;
      }

      // Find a matching template by family.
      const family = lineFamily(line, resolvedDataMap.get(line.id)?.code);
      let template = templates.find((t) => t.family === family);
      if (!template) {
        // Fall back to ala_carte or first available.
        template = templates.find((t) => t.family === 'ala_carte') ?? templates[0];
      }
      if (!template) {
        toast.error('No tag template available. Create one first.');
        return;
      }

      const tagW = template.print_size.width_mm;
      const tagH = template.print_size.height_mm;

      // Find the next available slot in the imposition layout.
      const slots = computeImpositionSlots(doc.imposition, tagW, tagH);
      const usedPositions = new Set(
        (activeSheet?.tags ?? []).map((t) => `${t.x_mm},${t.y_mm}`),
      );
      const slot = slots.find(
        (s) => !usedPositions.has(`${s.x_mm},${s.y_mm}`),
      ) ?? slots[0];

      const newTag: PlacedTag = {
        id: uid('t'),
        template_id: template.id,
        request_line_id: line.id,
        x_mm: slot.x_mm,
        y_mm: slot.y_mm,
        width_mm: tagW,
        height_mm: tagH,
        // The template's groups learn which product this tag is about, so the
        // tag carries its binding exactly as one built in the editor does.
        layers: bindTemplateLayers(
          structuredClone(template.doc.layers) as TagLayer[],
          line.line_type === 'product_set'
            ? ({ product_set_id: line.product_set_id ?? undefined } as GroupBinding)
            : ({ product_id: line.product_id ?? undefined } as GroupBinding),
        ),
      };

      updateActiveSheet((sheet) => ({
        ...sheet,
        tags: [...sheet.tags, newTag],
      }));
      setSelectedTagId(newTag.id);
    },
    [
      placedLineIds,
      templates,
      doc.imposition,
      activeSheet,
      updateActiveSheet,
      resolvedDataMap,
    ],
  );

  // -- Tag selection and removal -----------------------------------------------

  const handleSelectTag = useCallback((tagId: string) => {
    setSelectedTagId(tagId);
  }, []);

  const handleStageClick = useCallback(
    (e: Konva.KonvaEventObject<MouseEvent | TouchEvent>) => {
      if (e.target === e.target.getStage()) {
        setSelectedTagId(null);
      }
    },
    [],
  );

  const handleRemoveTag = useCallback(
    (tagId: string) => {
      updateActiveSheet((sheet) => ({
        ...sheet,
        tags: sheet.tags.filter((t) => t.id !== tagId),
      }));
      if (selectedTagId === tagId) setSelectedTagId(null);
    },
    [selectedTagId, updateActiveSheet],
  );

  // -- Tag drag ----------------------------------------------------------------

  const handleTagDragEnd = useCallback(
    (tagId: string, newXPx: number, newYPx: number) => {
      const x_mm = newXPx / scale;
      const y_mm = newYPx / scale;
      updateActiveSheet((sheet) => ({
        ...sheet,
        tags: sheet.tags.map((t) =>
          t.id === tagId ? { ...t, x_mm, y_mm } : t,
        ),
      }));
    },
    [scale, updateActiveSheet],
  );

  // -- Imposition controls -----------------------------------------------------

  const handlePresetChange = useCallback(
    (preset: ImpositionPreset) => {
      const presetConfig = IMPOSITION_PRESETS[preset];
      updateDoc((prev) => ({
        ...prev,
        imposition: { ...presetConfig, preset },
      }));
    },
    [updateDoc],
  );

  const handleImpositionField = useCallback(
    (field: keyof ImpositionConfig, value: number) => {
      updateDoc((prev) => ({
        ...prev,
        imposition: { ...prev.imposition, [field]: value, preset: 'custom' as ImpositionPreset },
      }));
    },
    [updateDoc],
  );

  // -- Zoom --------------------------------------------------------------------

  const handleZoomIn = useCallback(() => {
    setZoom((z) => Math.min(MAX_ZOOM, z + ZOOM_STEP));
  }, []);

  const handleZoomOut = useCallback(() => {
    setZoom((z) => Math.max(MIN_ZOOM, z - ZOOM_STEP));
  }, []);

  // -- Save and transition -----------------------------------------------------

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await onSave(doc);
    } finally {
      setSaving(false);
    }
  }, [doc, onSave]);

  const handleMarkProofReady = useCallback(async () => {
    setTransitioning(true);
    try {
      await onSave(doc);
      await transitionPriceTagRequest(request.id, 'mark_proof_ready');
      toast.success('Proof marked as ready');
      router.push(`/dealer-kit/price-tag-requests/${request.id}`);
    } catch {
      toast.error('Failed to mark proof ready');
    } finally {
      setTransitioning(false);
    }
  }, [doc, onSave, request.id, router]);

  const handleExportSheet = useCallback(
    async (sheetId: string, sheetIndex: number) => {
      setExportingSheet(true);
      try {
        await exportTagSheet(request.id, [sheetId]);
        toast.success(
          `Sheet ${sheetIndex + 1} export queued. Check My Downloads.`,
        );
      } catch {
        toast.error('Failed to export sheet');
      } finally {
        setExportingSheet(false);
      }
    },
    [request.id],
  );

  // -- Render ------------------------------------------------------------------

  return (
    <div className="flex h-full flex-col">
      {/* Top toolbar */}
      <div className="flex h-10 shrink-0 items-center gap-2 border-b bg-background px-3">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() =>
            router.push(`/dealer-kit/price-tag-requests/${request.id}`)
          }
        >
          <ChevronLeft className="size-3.5 mr-1" />
          {request.doc_number}
        </Button>

        <div className="flex-1" />

        {/* Zoom controls */}
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleZoomOut}
          >
            <Minus className="size-3.5" />
          </Button>
          <span className="w-12 text-center text-xs text-muted-foreground">
            {Math.round(zoom * 100)}%
          </span>
          <Button
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={handleZoomIn}
          >
            <Plus className="size-3.5" />
          </Button>
        </div>

        <div className="h-5 w-px bg-border mx-1" />

        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? (
            <Loader2 className="size-3.5 mr-1 animate-spin" />
          ) : (
            <Save className="size-3.5 mr-1" />
          )}
          Save
        </Button>

        {(request.status === 'designing' ||
          request.status === 'changes_requested') && (
          <Button
            size="sm"
            className="h-7 text-xs"
            onClick={handleMarkProofReady}
            disabled={transitioning || saving}
          >
            {transitioning ? (
              <Loader2 className="size-3.5 mr-1 animate-spin" />
            ) : (
              <Eye className="size-3.5 mr-1" />
            )}
            Mark Proof Ready
          </Button>
        )}
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* LEFT PANEL: Request lines */}
        <div className="hidden w-56 shrink-0 border-r bg-background md:flex md:flex-col">
          <div className="px-3 py-2 border-b">
            <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
              Request Lines
            </h3>
          </div>
          <div className="flex-1 overflow-y-auto">
            {request.lines.length === 0 ? (
              <p className="px-3 py-4 text-xs text-muted-foreground text-center">
                No lines in this request.
              </p>
            ) : (
              <div className="divide-y">
                {request.lines.map((line) => {
                  const isPlaced = placedLineIds.has(line.id);
                  // The line row carries ids; the code, the name and the price
                  // come from the resolver, which is the only thing that knows
                  // them (a request line stores no figures - ADR 0008).
                  const row = resolvedDataMap.get(line.id);
                  const code = row?.code ?? '';
                  const name = row?.name ?? '';
                  return (
                    <button
                      key={line.id}
                      type="button"
                      className="w-full text-left px-3 py-2.5 hover:bg-muted/50 transition-colors group"
                      onClick={() => handleDropLine(line)}
                    >
                      <div className="flex items-start gap-2">
                        <GripVertical className="size-3.5 mt-0.5 text-muted-foreground/50 shrink-0 group-hover:text-muted-foreground" />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-1.5">
                            <Badge
                              variant="secondary"
                              className="text-[10px] px-1 py-0 shrink-0"
                            >
                              {line.line_type === 'product' ? 'P' : 'Set'}
                            </Badge>
                            <span
                              className="text-xs font-mono text-muted-foreground truncate"
                              title={code}
                            >
                              {code || 'Resolving...'}
                            </span>
                            {isPlaced && (
                              <Check className="size-3 text-emerald-600 shrink-0" />
                            )}
                          </div>
                          <p className="text-xs mt-0.5 truncate" title={name}>
                            {name}
                          </p>
                          <p className="text-[10px] text-muted-foreground mt-0.5">
                            Qty: {line.quantity}
                            {row && row.show_promo_price && row.sell_price != null
                              ? ` / SP ${formatTagPrice(row.sell_price)}`
                              : row && row.list_price != null
                                ? ` / LP ${formatTagPrice(row.list_price)}`
                                : ''}
                          </p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* CENTER: Canvas workspace */}
        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex-1 overflow-auto bg-muted/30">
            <div className="p-6 inline-block min-w-full min-h-full">
              <div
                className="relative mx-auto shadow-lg"
                style={{ width: canvasWidthPx, height: canvasHeightPx }}
              >
                <Stage
                  ref={stageRef as React.RefObject<Konva.Stage>}
                  width={canvasWidthPx}
                  height={canvasHeightPx}
                  onClick={handleStageClick}
                  onTap={handleStageClick}
                >
                  <KonvaLayer>
                    {/* White page background */}
                    <Rect
                      x={0}
                      y={0}
                      width={canvasWidthPx}
                      height={canvasHeightPx}
                      fill="#ffffff"
                      stroke="#d4d4d8"
                      strokeWidth={1}
                    />

                    {/* Bleed lines */}
                    {doc.imposition.bleed_mm > 0 && (
                      <>
                        <Rect
                          x={doc.imposition.bleed_mm * scale}
                          y={doc.imposition.bleed_mm * scale}
                          width={
                            (pageW - 2 * doc.imposition.bleed_mm) * scale
                          }
                          height={
                            (pageH - 2 * doc.imposition.bleed_mm) * scale
                          }
                          stroke="#e5e7eb"
                          strokeWidth={0.5}
                          dash={[6, 4]}
                          listening={false}
                        />
                      </>
                    )}

                    {/* Tags on the active sheet */}
                    {activeSheet?.tags.map((tag) => (
                      <TagOnCanvas
                        key={tag.id}
                        tag={tag}
                        scale={scale}
                        isSelected={selectedTagId === tag.id}
                        resolvedData={
                          resolvedDataMap.get(tag.request_line_id) ?? null
                        }
                        assetUrls={library.assetUrls}
                        onSelect={handleSelectTag}
                        onDragEnd={handleTagDragEnd}
                      />
                    ))}
                  </KonvaLayer>
                </Stage>
              </div>
            </div>
          </div>

          {/* Sheet tabs */}
          <div className="flex h-9 shrink-0 items-center gap-1 border-t bg-background px-3">
            {doc.sheets.map((sheet, index) => (
              <button
                key={sheet.id}
                type="button"
                className={`flex items-center gap-1 rounded px-2.5 py-1 text-xs transition-colors ${
                  index === activeSheetIndex
                    ? 'bg-primary text-primary-foreground'
                    : 'hover:bg-muted text-muted-foreground'
                }`}
                onClick={() => {
                  setActiveSheetIndex(index);
                  setSelectedTagId(null);
                }}
              >
                Sheet {index + 1}
                {doc.sheets.length > 1 && (
                  <X
                    className="size-3 ml-0.5 hover:text-destructive"
                    onClick={(e) => {
                      e.stopPropagation();
                      removeSheet(index);
                    }}
                  />
                )}
              </button>
            ))}
            <button
              type="button"
              className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted transition-colors"
              onClick={addSheet}
            >
              <Plus className="size-3.5" />
            </button>
            <div className="flex-1" />
            {activeSheet && (
              <button
                type="button"
                className="rounded px-2 py-1 text-xs text-muted-foreground hover:bg-muted flex items-center gap-1"
                disabled={exportingSheet}
                onClick={() =>
                  handleExportSheet(activeSheet.id, activeSheetIndex)
                }
              >
                {exportingSheet ? (
                  <Loader2 className="size-3 animate-spin" />
                ) : (
                  <Printer className="size-3" />
                )}
                Print Sheet {activeSheetIndex + 1}
              </button>
            )}
            <span className="text-xs text-muted-foreground">
              {activeSheet?.tags.length ?? 0} tag
              {(activeSheet?.tags.length ?? 0) !== 1 ? 's' : ''} on this sheet
            </span>
          </div>
        </div>

        {/* RIGHT PANEL: Inspector + Imposition */}
        <div className="hidden w-60 shrink-0 border-l bg-background lg:flex lg:flex-col">
          {selectedTag && selectedLine && selectedResolved ? (
            <SelectedTagInspector
              tag={selectedTag}
              line={selectedLine}
              resolved={selectedResolved}
              templateName={
                templates.find((t) => t.id === selectedTag.template_id)
                  ?.name ?? 'Unknown'
              }
              onRemove={() => handleRemoveTag(selectedTag.id)}
            />
          ) : (
            <div className="px-3 py-4">
              <p className="text-xs text-muted-foreground text-center">
                Click a tag on the canvas to inspect it, or click a line in the
                left panel to place it.
              </p>
            </div>
          )}

          <div className="border-t mt-auto">
            <ImpositionControls
              imposition={doc.imposition}
              onPresetChange={handlePresetChange}
              onFieldChange={handleImpositionField}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TagOnCanvas: renders a placed tag as a Konva group with its layers
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
  onDragEnd: (tagId: string, xPx: number, yPx: number) => void;
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
      const node = e.target;
      onDragEnd(tag.id, node.x(), node.y());
    },
    [onDragEnd, tag.id],
  );

  // Sort layers by z_index.
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
      {/* Tag background */}
      <Rect
        x={0}
        y={0}
        width={w}
        height={h}
        fill="#ffffff"
        stroke={isSelected ? '#3b82f6' : '#d4d4d8'}
        strokeWidth={isSelected ? 2 : 0.5}
      />

      {/* Render template layers inside the tag bounds */}
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
            // tag around them.
            draggable={false}
            listening={false}
          />
        ))}

      {/* Product code label at bottom for identification */}
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

// ---------------------------------------------------------------------------
// SelectedTagInspector
// ---------------------------------------------------------------------------

function SelectedTagInspector({
  tag,
  line,
  resolved,
  templateName,
  onRemove,
}: {
  tag: PlacedTag;
  line: PriceTagRequestLine;
  resolved: LineTagData;
  templateName: string;
  onRemove: () => void;
}) {
  return (
    <div className="flex-1 overflow-y-auto">
      <div className="px-3 py-2 border-b">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          Selected Tag
        </h3>
      </div>
      <div className="px-3 py-3 space-y-3 text-xs">
        {/* Template info */}
        <div>
          <Label className="text-[10px] text-muted-foreground">Template</Label>
          <p className="font-medium">{templateName}</p>
        </div>

        {/* Bound line */}
        <div>
          <Label className="text-[10px] text-muted-foreground">
            Request Line
          </Label>
          <p className="font-mono">{resolved.code}</p>
          <p className="text-muted-foreground mt-0.5 truncate" title={resolved.name}>
            {resolved.name}
          </p>
        </div>

        {/* Resolved product data */}
        <div className="border-t pt-2">
          <Label className="text-[10px] text-muted-foreground">
            Resolved Data
          </Label>
          <dl className="mt-1 space-y-1">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Code</dt>
              <dd className="font-mono">{resolved.code}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Name</dt>
              <dd className="text-right truncate max-w-[100px]" title={resolved.name}>
                {resolved.name}
              </dd>
            </div>
            {resolved.list_price != null && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">List Price</dt>
                <dd>{formatTagPrice(resolved.list_price)}</dd>
              </div>
            )}
            {resolved.show_promo_price && resolved.sell_price != null && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Sell Price</dt>
                <dd className="text-green-700 font-medium">
                  {formatTagPrice(resolved.sell_price)}
                </dd>
              </div>
            )}
            {resolved.dimensions && (
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Dimensions</dt>
                <dd className="text-right">{resolved.dimensions}</dd>
              </div>
            )}
            {resolved.included_accessories && (
              <div>
                <dt className="text-muted-foreground">Accessories</dt>
                <dd className="mt-0.5">{resolved.included_accessories}</dd>
              </div>
            )}
            {resolved.set_members && (
              <div>
                <dt className="text-muted-foreground">Set members</dt>
                <dd className="mt-0.5 whitespace-pre-wrap text-[10px]">
                  {resolved.set_members}
                </dd>
              </div>
            )}
          </dl>
        </div>

        {/* Position */}
        <div className="border-t pt-2">
          <Label className="text-[10px] text-muted-foreground">Position</Label>
          <div className="grid grid-cols-2 gap-1 mt-1">
            <div>
              <span className="text-muted-foreground">X:</span>{' '}
              {tag.x_mm.toFixed(1)}mm
            </div>
            <div>
              <span className="text-muted-foreground">Y:</span>{' '}
              {tag.y_mm.toFixed(1)}mm
            </div>
            <div>
              <span className="text-muted-foreground">W:</span>{' '}
              {tag.width_mm.toFixed(1)}mm
            </div>
            <div>
              <span className="text-muted-foreground">H:</span>{' '}
              {tag.height_mm.toFixed(1)}mm
            </div>
          </div>
        </div>

        {/* Layers count */}
        <div className="border-t pt-2">
          <Label className="text-[10px] text-muted-foreground">Layers</Label>
          <p>{tag.layers.length} layer{tag.layers.length !== 1 ? 's' : ''}</p>
        </div>

        {/* Remove button */}
        <div className="border-t pt-2">
          <Button
            variant="destructive"
            size="sm"
            className="w-full h-7 text-xs"
            onClick={onRemove}
          >
            <Trash2 className="size-3 mr-1" />
            Remove Tag
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ImpositionControls
// ---------------------------------------------------------------------------

function ImpositionControls({
  imposition,
  onPresetChange,
  onFieldChange,
}: {
  imposition: ImpositionConfig;
  onPresetChange: (preset: ImpositionPreset) => void;
  onFieldChange: (field: keyof ImpositionConfig, value: number) => void;
}) {
  return (
    <div className="px-3 py-3 space-y-2">
      <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
        Imposition
      </h3>

      <div>
        <Label className="text-[10px] text-muted-foreground">Preset</Label>
        <SearchableSelect
          value={imposition.preset}
          onChange={(v) => onPresetChange((v || 'custom') as ImpositionPreset)}
          options={[
            { value: 'a4_3up', label: 'A4 3-up' },
            { value: 'a4_2x2', label: 'A4 2x2' },
            { value: 'custom', label: 'Custom' },
          ]}
          placeholder="Select preset"
          className="mt-0.5"
        />
      </div>

      <div className="grid grid-cols-2 gap-1.5">
        <div>
          <Label className="text-[10px] text-muted-foreground">
            Width (mm)
          </Label>
          <Input
            type="number"
            className="h-7 text-xs mt-0.5"
            value={imposition.page_width_mm}
            onChange={(e) =>
              onFieldChange('page_width_mm', Number(e.target.value))
            }
          />
        </div>
        <div>
          <Label className="text-[10px] text-muted-foreground">
            Height (mm)
          </Label>
          <Input
            type="number"
            className="h-7 text-xs mt-0.5"
            value={imposition.page_height_mm}
            onChange={(e) =>
              onFieldChange('page_height_mm', Number(e.target.value))
            }
          />
        </div>
        <div>
          <Label className="text-[10px] text-muted-foreground">
            Bleed (mm)
          </Label>
          <Input
            type="number"
            className="h-7 text-xs mt-0.5"
            value={imposition.bleed_mm}
            onChange={(e) =>
              onFieldChange('bleed_mm', Number(e.target.value))
            }
          />
        </div>
        <div>
          <Label className="text-[10px] text-muted-foreground">Gap (mm)</Label>
          <Input
            type="number"
            className="h-7 text-xs mt-0.5"
            value={imposition.gap_mm}
            onChange={(e) =>
              onFieldChange('gap_mm', Number(e.target.value))
            }
          />
        </div>
      </div>
    </div>
  );
}
