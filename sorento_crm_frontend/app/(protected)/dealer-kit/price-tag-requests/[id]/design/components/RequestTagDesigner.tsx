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

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronLeft, Check, LayoutTemplate, Loader2, Eye, Save } from 'lucide-react';
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
import { listTemplates } from '../../../../services/tagTemplateService';

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
  const [templates, setTemplates] = useState<TagTemplate[]>([]);
  const [resolvedRows, setResolvedRows] = useState<LineTagData[] | null>(null);

  /** One tag per line, keyed by line id. The live layers live here. */
  const [tags, setTags] = useState<Record<string, PlacedTag>>(() => {
    const map: Record<string, PlacedTag> = {};
    for (const [lineId, tag] of tagsFromDoc(initialDoc)) map[lineId] = tag;
    return map;
  });
  /**
   * The layers each tag was opened with, keyed by TAG id.
   *
   * The editor reads its document once, on mount, so this has to be a stable
   * object per tag: rebuilding it from the live layers would re-run the
   * editor's open-time work on every keystroke. It doubles as the "has this
   * been edited" comparison the template swap asks.
   */
  const [openedDocs, setOpenedDocs] = useState<Record<string, TagTemplateDoc>>(() => {
    const map: Record<string, TagTemplateDoc> = {};
    for (const [, tag] of tagsFromDoc(initialDoc)) {
      map[tag.id] = {
        layers: tag.layers,
        width_mm: tag.width_mm,
        height_mm: tag.height_mm,
      };
    }
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

  useEffect(() => {
    listTemplates()
      .then(setTemplates)
      .catch(() => toast.error('Failed to load tag templates'));
  }, []);

  useEffect(() => {
    let live = true;
    resolveRequestLines(request.id)
      .then((rows) => {
        if (live) setResolvedRows(rows);
      })
      .catch((error: unknown) => {
        if (live) setResolvedRows([]);
        toast.error(error instanceof Error ? error.message : 'Failed to resolve prices');
      });
    return () => {
      live = false;
    };
  }, [request.id]);

  const resolved = useMemo(() => {
    const map = new Map<string, LineTagData>();
    for (const row of resolvedRows ?? []) map.set(row.line_id, row);
    return map;
  }, [resolvedRows]);

  // -- Tags ------------------------------------------------------------------

  const applyTemplate = useCallback((line: PriceTagRequestLine, template: TagTemplate) => {
    const tag = tagForLine(line, template, newTagId());
    setTags((prev) => ({ ...prev, [line.id]: tag }));
    setOpenedDocs((prev) => ({
      ...prev,
      [tag.id]: {
        layers: tag.layers,
        width_mm: tag.width_mm,
        height_mm: tag.height_mm,
      },
    }));
  }, []);

  // The first line opens by itself: this page exists to design, and a canvas
  // waiting to be told which line is a click nobody needs to make.
  useEffect(() => {
    if (selectedLineId || request.lines.length === 0) return;
    setSelectedLineId(request.lines[0].id);
  }, [selectedLineId, request.lines]);

  // A line with no tag yet is cloned from its family's default template. It
  // waits for BOTH the templates and the resolved lines: the family comes off
  // the resolved code, so cloning early would pick the ala carte fallback for
  // everything.
  useEffect(() => {
    if (!selectedLineId || tags[selectedLineId]) return;
    if (templates.length === 0 || resolvedRows === null) return;
    const line = request.lines.find((l) => l.id === selectedLineId);
    if (!line) return;
    const template = defaultTemplateFor(line, templates, resolved.get(line.id)?.code);
    if (!template) {
      toast.error('There are no tag templates yet. Design one under Tag Templates first.');
      return;
    }
    applyTemplate(line, template);
  }, [
    selectedLineId,
    tags,
    templates,
    resolvedRows,
    resolved,
    request.lines,
    applyTemplate,
  ]);

  const selectedTag = selectedLineId ? tags[selectedLineId] ?? null : null;
  const selectedDoc = selectedTag ? openedDocs[selectedTag.id] ?? null : null;

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

  /** Whether this line's tag has been changed since it was cloned or opened. */
  const isEdited = useCallback(
    (lineId: string) => {
      const tag = tags[lineId];
      const opened = tag ? openedDocs[tag.id] : null;
      if (!tag || !opened) return false;
      return JSON.stringify(tag.layers) !== JSON.stringify(opened.layers);
    },
    [tags, openedDocs],
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
      await transitionPriceTagRequest(request.id, 'mark_proof_ready');
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
          selectedTag && selectedDoc ? (
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
            <div className="flex h-full items-center justify-center px-6 text-center">
              <p className="text-sm text-muted-foreground">
                {request.lines.length === 0
                  ? 'This request has no lines, so there is nothing to design.'
                  : 'Preparing this line...'}
              </p>
            </div>
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
                        className="shrink-0 px-1 py-0 text-[10px]"
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
                    <p className="mt-0.5 truncate text-[10px] text-muted-foreground">
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
