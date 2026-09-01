'use client';

/**
 * Designing a request's tags IS the template editor (D51).
 *
 * The captain's words: "the design page is different from my template design...
 * they should be the same layout, and how can I pull out the template from the
 * template I have designed." So this page hosts `TagCanvasEditor` - the same
 * toolbar, Layers panel, Inspector and D33-D44 interaction model - with the
 * request's lines as a rail above the Layers panel and the SELECTED line's tag
 * on the artboard.
 *
 * A line's tag is a `PlacedTag` cloned from a template. Editing it never
 * touches the template: the clone is what gets saved into the request's tag
 * sheet document. Switching lines remounts the editor on the other tag, which
 * is why the host keeps every tag's layers current rather than waiting for a
 * Save that would come too late.
 *
 * Arranging the sheets is a consequence rather than a chore: on save every
 * line's tag is laid out in line order, quantity times, and the Arrange half is
 * there to look at it and to drag a copy if somebody wants to.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { useRouter } from 'next/navigation';
import {
  ChevronLeft,
  Check,
  LayoutTemplate,
  Loader2,
  Eye,
  Save,
  RefreshCw,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import type {
  ImpositionConfig,
  LineTagData,
  PlacedTag,
  TagBindingData,
  TagLayer,
  TagSheetDoc,
  TagTemplate,
  TagTemplateDoc,
} from '@/lib/dealer-kit/tag-template-types';
import { IMPOSITION_PRESETS, familyLabel } from '@/lib/dealer-kit/tag-template-types';
import { lineFamily } from '@/lib/dealer-kit/line-family';
import {
  autoArrange,
  defaultTemplateFor,
  pinKeyForPlacement,
  pinnedFromDoc,
  starterTemplateFor,
  tagForLine,
  tagsFromDoc,
  type ArrangeItem,
  type PinnedPlacement,
} from '@/lib/dealer-kit/request-tags';
import { formatTagPrice } from '@/lib/dealer-kit/price-badge';
import { TagCanvasEditor } from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import { useKitLibrary } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import { ArrangeSheetView } from './ArrangeSheetView';
import { TemplatePickDialog } from './TemplatePickDialog';
import {
  resolveRequestLines,
  transitionPriceTagRequest,
  exportTagSheet,
  type PriceTagRequestDetail,
  type PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import { listPublishedTemplates } from '../../../../services/tagTemplateService';
import { FocusShell, FocusToggle } from '../../../../components/FocusMode';

let idSeq = 0;
function newTagId(): string {
  idSeq += 1;
  return `tag-${Date.now()}-${idSeq}`;
}

interface Props {
  request: PriceTagRequestDetail;
  initialDoc: TagSheetDoc | null;
  onSave: (doc: TagSheetDoc) => Promise<void>;
}

export function RequestTagDesigner({ request, initialDoc, onSave }: Props) {
  const router = useRouter();

  const [mode, setMode] = useState<'design' | 'arrange'>('design');
  /** Full screen (D11, AC-S6-1): the same `FocusShell` the room designer uses.
   *  Both Design and Arrange sit inside it - the toggle is one control for
   *  either half, not a per-mode setting. */
  const [focus, setFocus] = useState(false);
  const [templates, setTemplates] = useState<TagTemplate[]>([]);
  const [templatesStatus, setTemplatesStatus] = useState<'loading' | 'loaded' | 'error'>(
    'loading',
  );
  const [resolvedRows, setResolvedRows] = useState<LineTagData[] | null>(null);
  const [pricesStatus, setPricesStatus] = useState<'loading' | 'loaded' | 'error'>('loading');

  /** One tag per line, keyed by line id. The live layers live here. */
  const [tags, setTags] = useState<Record<string, PlacedTag>>(() => {
    const map: Record<string, PlacedTag> = {};
    for (const [lineId, tag] of tagsFromDoc(initialDoc)) map[lineId] = tag;
    return map;
  });
  const [pinned, setPinned] = useState<Record<string, PinnedPlacement>>(() =>
    pinnedFromDoc(initialDoc),
  );
  const [imposition, setImposition] = useState<ImpositionConfig>(
    initialDoc?.imposition ?? { preset: 'a4_3up', ...IMPOSITION_PRESETS.a4_3up },
  );

  const [selectedLineId, setSelectedLineId] = useState<string | null>(null);
  const [activeSheetIndex, setActiveSheetIndex] = useState(0);
  const [arrangeZoom, setArrangeZoom] = useState(1);
  const [selectedTagId, setSelectedTagId] = useState<string | null>(null);

  const [pickerLineId, setPickerLineId] = useState<string | null>(null);
  const [replaceAsk, setReplaceAsk] = useState<{ lineId: string; templateId: string } | null>(
    null,
  );

  const [saving, setSaving] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [printing, setPrinting] = useState(false);

  const library = useKitLibrary();

  // -- Loading ---------------------------------------------------------------

  // A failed fetch gets an explicit, stays-put error state with Retry (AC-S3-3)
  // rather than a toast that vanishes and leaves the canvas silent. Only
  // PUBLISHED templates are eligible for request design (AC-S5-2).
  const loadTemplates = useCallback(() => {
    setTemplatesStatus('loading');
    listPublishedTemplates()
      .then((rows) => {
        setTemplates(rows);
        setTemplatesStatus('loaded');
      })
      .catch(() => setTemplatesStatus('error'));
  }, []);

  useEffect(() => {
    loadTemplates();
  }, [loadTemplates]);

  // Same mechanism as loadTemplates just above: a failed resolve gets an
  // explicit, stays-put error state with Retry, not a toast that vanishes and
  // leaves the canvas open on blank data with no visible cause.
  const loadPrices = useCallback(() => {
    setPricesStatus('loading');
    resolveRequestLines(request.id)
      .then((rows) => {
        setResolvedRows(rows);
        setPricesStatus('loaded');
      })
      .catch(() => setPricesStatus('error'));
  }, [request.id]);

  useEffect(() => {
    loadPrices();
  }, [loadPrices]);

  const resolved = useMemo(() => {
    const map = new Map<string, LineTagData>();
    for (const row of resolvedRows ?? []) map.set(row.line_id, row);
    return map;
  }, [resolvedRows]);

  // -- Tags ------------------------------------------------------------------

  const applyTemplate = useCallback((line: PriceTagRequestLine, template: TagTemplate) => {
    setTags((prev) => ({
      ...prev,
      [line.id]: tagForLine(line, template, newTagId()),
    }));
  }, []);

  // The first line opens by itself: this page exists to design, and a canvas
  // waiting to be told which line is a click nobody needs to make.
  useEffect(() => {
    if (selectedLineId || request.lines.length === 0) return;
    setSelectedLineId(request.lines[0].id);
  }, [selectedLineId, request.lines]);

  // A line with no tag yet is cloned from its family's default template. It
  // waits for BOTH the templates and the prices to settle (loaded OR error -
  // an error state has its own Retry, not a silent stall): the family comes
  // off the resolved code, so cloning early would pick the ala carte fallback
  // for everything.
  //
  // Zero PUBLISHED templates is not an error: the line starts from a
  // product-block (or, for a set line, a set block) starter bound to its own
  // item instead of dead-ending on "Preparing this line..." forever
  // (D6/D13, #476).
  useEffect(() => {
    if (!selectedLineId || tags[selectedLineId]) return;
    if (templatesStatus === 'loading' || templatesStatus === 'error') return;
    if (pricesStatus === 'loading' || pricesStatus === 'error') return;
    const line = request.lines.find((l) => l.id === selectedLineId);
    if (!line) return;
    const lineData = resolved.get(line.id);
    const template =
      defaultTemplateFor(line, templates, lineData?.code) ??
      starterTemplateFor(line, lineData, newTagId);
    applyTemplate(line, template);
  }, [
    selectedLineId,
    tags,
    templates,
    templatesStatus,
    pricesStatus,
    resolved,
    request.lines,
    applyTemplate,
  ]);

  const selectedTag = selectedLineId ? tags[selectedLineId] ?? null : null;

  /**
   * The document the canvas opens on, rebuilt only when the TAG changes.
   *
   * The editor reads its document once, on mount, and keeps the layers in its
   * own state from then on. So this has to be the tag's layers AS THEY STAND
   * when the canvas mounts on it - a fresh object per keystroke would be
   * ignored, and a snapshot taken when the tag was first created would throw
   * every edit away the moment somebody looked at another line and came back.
   * That is exactly what it did until this was measured on the lane.
   */
  const docRef = useRef<{ tagId: string; doc: TagTemplateDoc } | null>(null);
  if (selectedTag && docRef.current?.tagId !== selectedTag.id) {
    docRef.current = {
      tagId: selectedTag.id,
      doc: {
        layers: selectedTag.layers,
        width_mm: selectedTag.width_mm,
        height_mm: selectedTag.height_mm,
      },
    };
  }
  const selectedDoc = selectedTag ? docRef.current?.doc ?? null : null;

  /** What the canvas draws against: the LINE, with its marketing override. */
  const boundData: TagBindingData | null = useMemo(() => {
    if (!selectedLineId) return null;
    const row = resolved.get(selectedLineId);
    return row ? { kind: 'line', line: row } : null;
  }, [selectedLineId, resolved]);

  const handleLayersChange = useCallback(
    (layers: TagLayer[]) => {
      const lineId = selectedLineId;
      if (!lineId) return;
      setTags((prev) => {
        const tag = prev[lineId];
        if (!tag || tag.layers === layers) return prev;
        return { ...prev, [lineId]: { ...tag, layers } };
      });
    },
    [selectedLineId],
  );

  /**
   * Whether re-cloning this line's tag would lose work.
   *
   * Measured against the tag's own TEMPLATE rather than against what it was
   * opened with, so a design that was saved a week ago still counts as work.
   */
  const isEdited = useCallback(
    (lineId: string) => {
      const tag = tags[lineId];
      const line = request.lines.find((l) => l.id === lineId);
      const template = templates.find((t) => t.id === tag?.template_id);
      if (!tag || !line) return false;
      // A template that is no longer there cannot be compared against, so ask.
      if (!template) return true;
      const pristine = tagForLine(line, template, tag.id).layers;
      return JSON.stringify(tag.layers) !== JSON.stringify(pristine);
    },
    [tags, templates, request.lines],
  );

  const chooseTemplate = useCallback(
    (lineId: string, templateId: string) => {
      const line = request.lines.find((l) => l.id === lineId);
      const template = templates.find((t) => t.id === templateId);
      if (!line || !template) return;
      applyTemplate(line, template);
      setPickerLineId(null);
      setReplaceAsk(null);
      setSelectedLineId(lineId);
    },
    [request.lines, templates, applyTemplate],
  );

  const handleTemplateChosen = useCallback(
    (templateId: string) => {
      const lineId = pickerLineId;
      if (!lineId) return;
      // Re-cloning throws the edits away, so it asks first (D51).
      if (isEdited(lineId)) {
        setPickerLineId(null);
        setReplaceAsk({ lineId, templateId });
        return;
      }
      chooseTemplate(lineId, templateId);
    },
    [pickerLineId, isEdited, chooseTemplate],
  );

  // -- The document ----------------------------------------------------------

  const arrangeItems: ArrangeItem[] = useMemo(
    () =>
      request.lines
        .map((line) => ({ tag: tags[line.id], quantity: line.quantity }))
        .filter((item): item is ArrangeItem => Boolean(item.tag)),
    [request.lines, tags],
  );

  const doc: TagSheetDoc = useMemo(
    () => ({
      kind: 'tag_sheet',
      imposition,
      sheets: autoArrange(arrangeItems, imposition, pinned),
    }),
    [arrangeItems, imposition, pinned],
  );

  const handleMoveTag = useCallback(
    (sheetIndex: number, tag: PlacedTag, x_mm: number, y_mm: number) => {
      setPinned((prev) => ({
        ...prev,
        [pinKeyForPlacement(tag)]: { sheet: sheetIndex, x_mm, y_mm },
      }));
    },
    [],
  );

  const save = useCallback(async () => {
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
      // A STATUS, not an action name: see the note on the detail page.
      await transitionPriceTagRequest(request.id, 'proof_ready');
      toast.success('Proof marked as ready');
      router.push(`/dealer-kit/price-tag-requests/${request.id}`);
    } catch {
      toast.error('Failed to mark the proof ready');
    } finally {
      setTransitioning(false);
    }
  }, [doc, onSave, request.id, router]);

  const handlePrintSheet = useCallback(
    async (sheetIndex: number) => {
      const sheet = doc.sheets[sheetIndex];
      if (!sheet) return;
      setPrinting(true);
      try {
        // Saved first: the worker prints what the document says, and an unsaved
        // arrangement would print the previous one.
        await onSave(doc);
        await exportTagSheet(request.id, [sheet.id]);
        toast.success(`Sheet ${sheetIndex + 1} export queued. Check My Downloads.`);
      } catch {
        toast.error('Failed to export the sheet');
      } finally {
        setPrinting(false);
      }
    },
    [doc, onSave, request.id],
  );

  const canMarkProofReady =
    request.status === 'designing' || request.status === 'changes_requested';

  // -- Render ----------------------------------------------------------------

  const rail = (
    <LinesRail
      lines={request.lines}
      resolved={resolved}
      tags={tags}
      selectedLineId={selectedLineId}
      onSelect={setSelectedLineId}
      onUseTemplate={setPickerLineId}
    />
  );

  return (
    <FocusShell active={focus} onExit={() => setFocus(false)}>
    <div className="flex h-full flex-col">
      {/* Request bar: what this is, which half is showing, and the two actions
          that leave the page in a different state. */}
      <div className="flex h-10 shrink-0 items-center gap-2 border-b bg-background px-3">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={() => router.push(`/dealer-kit/price-tag-requests/${request.id}`)}
        >
          <ChevronLeft className="mr-1 size-3.5" />
          {request.doc_number}
        </Button>

        <div className="ml-2 flex items-center rounded-md border p-0.5">
          {(['design', 'arrange'] as const).map((value) => (
            <button
              key={value}
              type="button"
              className={cn(
                'rounded px-2.5 py-1 text-xs capitalize transition-colors',
                mode === value
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted',
              )}
              onClick={() => setMode(value)}
            >
              {value === 'design' ? 'Design' : 'Arrange'}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <FocusToggle active={focus} onToggle={setFocus} label="tags" />

        <Button
          variant="outline"
          size="sm"
          className="h-7 text-xs"
          onClick={save}
          disabled={saving || transitioning}
        >
          {saving ? (
            <Loader2 className="mr-1 size-3.5 animate-spin" />
          ) : (
            <Save className="mr-1 size-3.5" />
          )}
          Save
        </Button>

        {canMarkProofReady && (
          <Button
            variant="primary"
            size="sm"
            className="h-7 text-xs"
            onClick={handleMarkProofReady}
            disabled={saving || transitioning}
          >
            {transitioning ? (
              <Loader2 className="mr-1 size-3.5 animate-spin" />
            ) : (
              <Eye className="mr-1 size-3.5" />
            )}
            Mark proof ready
          </Button>
        )}
      </div>

      <div className="flex-1 overflow-hidden">
        {mode === 'design' ? (
          request.lines.length === 0 ? (
            <CanvasMessage text="This request has no lines, so there is nothing to design." />
          ) : templatesStatus === 'loading' ? (
            <CanvasMessage text="Loading templates..." />
          ) : templatesStatus === 'error' ? (
            <CanvasMessage text="Failed to load tag templates.">
              <Button variant="outline" size="sm" onClick={loadTemplates}>
                <RefreshCw className="mr-1.5 size-3.5" />
                Retry
              </Button>
            </CanvasMessage>
          ) : pricesStatus === 'loading' ? (
            <CanvasMessage text="Resolving prices..." />
          ) : pricesStatus === 'error' ? (
            <CanvasMessage text="Failed to resolve prices.">
              <Button variant="outline" size="sm" onClick={loadPrices}>
                <RefreshCw className="mr-1.5 size-3.5" />
                Retry
              </Button>
            </CanvasMessage>
          ) : selectedTag && selectedDoc ? (
            <TagCanvasEditor
              key={selectedTag.id}
              doc={selectedDoc}
              onChange={() => void save()}
              promotionId={request.promotion_id}
              boundData={boundData}
              leftRail={rail}
              onLayersChange={handleLayersChange}
              onUseTemplate={() =>
                selectedLineId && setPickerLineId(selectedLineId)
              }
              hideSaveBar
            />
          ) : (
            <CanvasMessage text="Preparing this line..." />
          )
        ) : (
          <ArrangeSheetView
            doc={doc}
            activeSheetIndex={Math.min(activeSheetIndex, doc.sheets.length - 1)}
            onActiveSheetChange={setActiveSheetIndex}
            zoom={arrangeZoom}
            onZoomChange={setArrangeZoom}
            selectedTagId={selectedTagId}
            onSelectTag={setSelectedTagId}
            resolved={resolved}
            assetUrls={library.assetUrls}
            onImpositionChange={setImposition}
            onMoveTag={handleMoveTag}
            onPrintSheet={handlePrintSheet}
            printing={printing}
          />
        )}
      </div>

      <TemplatePickDialog
        open={pickerLineId !== null}
        templates={templates}
        currentTemplateId={
          pickerLineId ? tags[pickerLineId]?.template_id ?? null : null
        }
        preferredFamily={
          pickerLineId
            ? lineFamily(
                request.lines.find((l) => l.id === pickerLineId) ?? {
                  line_type: 'product' as const,
                },
                resolved.get(pickerLineId)?.code,
              )
            : null
        }
        onCancel={() => setPickerLineId(null)}
        onConfirm={handleTemplateChosen}
      />

      <AlertDialog
        open={replaceAsk !== null}
        onOpenChange={(open) => !open && setReplaceAsk(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Replace this tag with the template?</AlertDialogTitle>
            <AlertDialogDescription>
              This tag has been edited. Using another template starts it again from
              that template and the edits are lost.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() =>
                replaceAsk && chooseTemplate(replaceAsk.lineId, replaceAsk.templateId)
              }
            >
              Replace
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
    </FocusShell>
  );
}

// ---------------------------------------------------------------------------
// The canvas's own placeholder states (loading / resolving / error) - the
// design page must always say what it is waiting for rather than sitting on
// a bare, permanent "Preparing this line..." (#476).
// ---------------------------------------------------------------------------

function CanvasMessage({
  text,
  children,
}: {
  text: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 px-6 text-center">
      <p className="text-sm text-muted-foreground">{text}</p>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// The lines rail
// ---------------------------------------------------------------------------

function LinesRail({
  lines,
  resolved,
  tags,
  selectedLineId,
  onSelect,
  onUseTemplate,
}: {
  lines: PriceTagRequestLine[];
  resolved: Map<string, LineTagData>;
  tags: Record<string, PlacedTag>;
  selectedLineId: string | null;
  onSelect: (lineId: string) => void;
  onUseTemplate: (lineId: string) => void;
}) {
  return (
    <div className="flex max-h-[45%] shrink-0 flex-col border-b border-r">
      <div className="flex h-10 shrink-0 items-center border-b px-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Lines
        </span>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {lines.length === 0 ? (
          <p className="px-3 py-4 text-center text-xs text-muted-foreground">
            This request has no lines.
          </p>
        ) : (
          <div className="divide-y">
            {lines.map((line) => {
              const row = resolved.get(line.id);
              const code = row?.code ?? '';
              const name = row?.name ?? '';
              const designed = Boolean(tags[line.id]);
              const family = familyLabel(lineFamily(line, code));
              return (
                <div
                  key={line.id}
                  className={cn(
                    'relative',
                    selectedLineId === line.id && 'bg-accent',
                  )}
                >
                  <button
                    type="button"
                    className="w-full px-3 py-2 pr-8 text-left transition-colors hover:bg-muted/50"
                    onClick={() => onSelect(line.id)}
                  >
                    <div className="flex items-center gap-1.5">
                      <Badge
                        variant="secondary"
                        className="shrink-0 px-1 py-0 text-2xs"
                      >
                        {line.line_type === 'product' ? 'P' : 'Set'}
                      </Badge>
                      <span
                        className="truncate font-mono text-xs text-muted-foreground"
                        title={code}
                      >
                        {code || 'Resolving...'}
                      </span>
                      {designed && (
                        <Check className="size-3 shrink-0 text-emerald-600" />
                      )}
                    </div>
                    <p className="mt-0.5 truncate text-xs" title={name}>
                      {name}
                    </p>
                    <p className="mt-0.5 truncate text-2xs text-muted-foreground">
                      Qty {line.quantity} / {family}
                      {row && row.show_promo_price && row.sell_price != null
                        ? ` / SP ${formatTagPrice(row.sell_price)}`
                        : row && row.list_price != null
                          ? ` / LP ${formatTagPrice(row.list_price)}`
                          : ''}
                    </p>
                  </button>
                  <button
                    type="button"
                    className="absolute right-1 top-1.5 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                    title="Use template..."
                    aria-label={`Use template for ${code || 'this line'}`}
                    onClick={() => onUseTemplate(line.id)}
                  >
                    <LayoutTemplate className="size-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
