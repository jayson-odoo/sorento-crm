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
 *
 * Autosave (D22, S8): every committed change - a layer edit, an arranged
 * pin - re-runs the `doc` memo below, and an effect on THAT schedules a
 * debounced save through the same `onSave` the manual Save button calls.
 * `flush()` (the debounce's own pending value, sent now) covers the three
 * moments a ~1s wait is too slow to trust: switching Design/Arrange,
 * switching lines, and leaving the page (`beforeunload` and the back link).
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
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
  resizeAllTags,
  resizeTag,
  resolveTagSize,
  starterTemplateFor,
  tagForLine,
  tagSizeBounds,
  tagSizePresets,
  tagsFromDoc,
  type ArrangeItem,
  type PinnedPlacement,
  type TagSizePreset,
} from '@/lib/dealer-kit/request-tags';
import { formatTagPrice } from '@/lib/dealer-kit/price-badge';
import { TagCanvasEditor } from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import { useKitLibrary } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import { useAutosave } from '@/hooks/useAutosave';
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
import { AutosaveIndicator } from '../../../../components/AutosaveIndicator';

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
  const pathname = usePathname();
  const searchParams = useSearchParams();

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
  /**
   * The size "Apply to all lines" (D24, S9) last set, persisted in the doc
   * (S9 review B2) so it also applies to a line that has not been opened
   * yet: without this, `applyTemplate` below would clone a not-yet-opened
   * line at its TEMPLATE's own print size, silently undoing what Apply to
   * all just did the moment somebody opened line 3.
   */
  const [defaultTagSize, setDefaultTagSize] = useState<{
    width_mm: number;
    height_mm: number;
  } | null>(initialDoc?.default_tag_size ?? null);

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

  // A request-level default (S9 review B2) wins over the template's own
  // print size the moment a line clones one - "Apply to all lines" is
  // supposed to mean every line, including one nobody has opened yet.
  const applyTemplate = useCallback(
    (line: PriceTagRequestLine, template: TagTemplate) => {
      setTags((prev) => {
        let tag = tagForLine(line, template, newTagId());
        if (defaultTagSize) {
          tag = resizeTag(tag, defaultTagSize.width_mm, defaultTagSize.height_mm);
        }
        return { ...prev, [line.id]: tag };
      });
    },
    [defaultTagSize],
  );

  // The first line opens by itself: this page exists to design, and a canvas
  // waiting to be told which line is a click nobody needs to make. A row's own
  // Design action on the detail page's Lines tab (S10) preselects THAT line via
  // `?line=<lineId>` instead - honoured only on the initial pick, same as the
  // fallback it replaces.
  useEffect(() => {
    if (selectedLineId || request.lines.length === 0) return;
    const requestedLineId = searchParams.get('line');
    const preselected =
      requestedLineId && request.lines.some((line) => line.id === requestedLineId)
        ? requestedLineId
        : request.lines[0].id;
    setSelectedLineId(preselected);
    // The link did its job the moment it picked a line - a refresh from here
    // on should land on whatever line is actually open (Design/Arrange can
    // move it), not snap back to the one the URL named. `pathname` alone has
    // no query string, so this is a plain drop of `?line=`.
    if (requestedLineId) router.replace(pathname, { scroll: false });
  }, [selectedLineId, request.lines, searchParams, router, pathname]);

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
   * The LAYERS the canvas opens on, rebuilt only when the tag's IDENTITY
   * changes (its id - a template swap or a line switch). The editor reads
   * its document once, on mount, and keeps the layers in its own state from
   * then on, so this has to be the tag's layers AS THEY STAND when the
   * canvas mounts on it - a fresh object per keystroke would be ignored, and
   * a snapshot taken when the tag was first created would throw every edit
   * away the moment somebody looked at another line and came back. That is
   * exactly what it did until this was measured on the lane.
   *
   * Width/height are deliberately NOT part of this identity (S9 review B1):
   * a resize must reach the on-screen artboard WITHOUT remounting the
   * editor, because the editor reads `doc.width_mm`/`height_mm` straight off
   * its `doc` PROP on every render (only `layers` is frozen into local
   * state) - `selectedDoc` below always takes the tag's CURRENT size, and a
   * key on tag id alone means resizing never unmounts a focused input in
   * the Tag Size control (B1's actual bug: keying on size remounted
   * `TagSizeControl`, and with it whatever input the designer was mid-typing
   * into).
   */
  const docRef = useRef<{ key: string; layers: TagLayer[] } | null>(null);
  // The editor is unmounted whenever Arrange is showing (the mode ternary
  // below), so a snapshot taken before that switch is stale by the time
  // Design remounts it - dropping the ref here forces a rebuild off the
  // live `tags` state instead of replaying the layers as they stood before
  // the switch and losing whatever Arrange-side or since-mount edits
  // happened in between.
  if (mode !== 'design') docRef.current = null;
  if (selectedTag && docRef.current?.key !== selectedTag.id) {
    docRef.current = { key: selectedTag.id, layers: selectedTag.layers };
  }
  const selectedDoc: TagTemplateDoc | null =
    selectedTag && docRef.current
      ? {
          layers: docRef.current.layers,
          width_mm: selectedTag.width_mm,
          height_mm: selectedTag.height_mm,
        }
      : null;

  /** What the canvas draws against: the LINE, with its marketing override. */
  const boundData: TagBindingData | null = useMemo(() => {
    if (!selectedLineId) return null;
    const row = resolved.get(selectedLineId);
    return row ? { kind: 'line', line: row } : null;
  }, [selectedLineId, resolved]);

  // -- Tag size control (D24, S9) ---------------------------------------------

  const sizePresets = useMemo(() => tagSizePresets(templates), [templates]);

  const handleResizeTag = useCallback(
    (width_mm: number, height_mm: number) => {
      const lineId = selectedLineId;
      if (!lineId) return;
      setTags((prev) => {
        const tag = prev[lineId];
        if (!tag) return prev;
        return { ...prev, [lineId]: resizeTag(tag, width_mm, height_mm) };
      });
    },
    [selectedLineId],
  );

  // Resizes every ALREADY-CLONED tag now, and remembers the size as the
  // request's default (S9 review B2) so a line opened later clones at this
  // size too, via `applyTemplate` above - not the template's own print size.
  const handleResizeAllTags = useCallback((width_mm: number, height_mm: number) => {
    setTags((prev) => resizeAllTags(prev, width_mm, height_mm));
    setDefaultTagSize({ width_mm, height_mm });
  }, []);

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
      default_tag_size: defaultTagSize,
    }),
    [arrangeItems, imposition, pinned, defaultTagSize],
  );

  // -- Autosave (D22, S8) ------------------------------------------------------

  const autosave = useAutosave<TagSheetDoc>(onSave);

  // Every REAL change to `doc` schedules a debounced save - a layer edit
  // (through `tags`), an arranged pin, an imposition change. The very first
  // firing is the initial `doc` itself (whatever `initialDoc` seeded, or the
  // empty starting point), not an edit, so it is skipped rather than
  // autosaving data that is already exactly what the server has.
  //
  // Guards on the VALUE, not a boolean "have I run yet" flag: dev's
  // StrictMode fires a fresh mount's effects twice (mount, cleanup, mount
  // again) to catch effects that are not idempotent, and a boolean flag
  // would already read "yes" on that second firing, autosaving the
  // unchanged initial doc a second time. Comparing against the last `doc`
  // this effect actually saw covers both: an unmoved re-fire is the same
  // reference and is skipped either way.
  const lastSeenDocRef = useRef<TagSheetDoc | undefined>(undefined);
  useEffect(() => {
    if (lastSeenDocRef.current === doc) return;
    const isInitial = lastSeenDocRef.current === undefined;
    lastSeenDocRef.current = doc;
    if (isInitial) return;
    autosave.schedule(doc);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc, autosave.schedule]);

  // beforeunload covers a refresh, a close and a jump out of the app - the
  // debounce armed by the last edit otherwise never gets to run.
  useEffect(() => {
    const handler = () => {
      void autosave.flush();
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autosave.flush]);

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

  /** Switching a line never LOSES a committed change (AC-S8-3) - flush the
   *  autosave's own pending value before the switch, rather than leaving it
   *  to the ~1s debounce that might not have fired yet. */
  const handleSelectLine = useCallback(
    (lineId: string) => {
      if (lineId !== selectedLineId) void autosave.flush();
      setSelectedLineId(lineId);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedLineId, autosave.flush],
  );

  /** Same idea for Design <-> Arrange (AC-S8-3). */
  const handleModeChange = useCallback(
    (value: 'design' | 'arrange') => {
      if (value !== mode) void autosave.flush();
      setMode(value);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [mode, autosave.flush],
  );

  const handleBack = useCallback(() => {
    void autosave.flush();
    router.push(`/dealer-kit/price-tag-requests/${request.id}`);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autosave.flush, router, request.id]);

  // -- Render ----------------------------------------------------------------

  const rail = (
    <>
      <LinesRail
        lines={request.lines}
        resolved={resolved}
        tags={tags}
        selectedLineId={selectedLineId}
        onSelect={handleSelectLine}
        onUseTemplate={setPickerLineId}
      />
      <TagSizeControl
        tag={selectedTag}
        presets={sizePresets}
        imposition={imposition}
        onResize={handleResizeTag}
        onResizeAll={handleResizeAllTags}
      />
    </>
  );

  return (
    <FocusShell active={focus} onExit={() => setFocus(false)}>
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {/* Request bar: what this is, which half is showing, and the two actions
          that leave the page in a different state.
          `flex-wrap` (S6): at 375px the back button, mode toggle, Full
          screen, Save and (for a designing request) Mark proof ready do not
          fit one row - the same fix the template page's own action row
          carries. `min-h-10` rather than a fixed `h-10` so the row can
          actually grow into a second line instead of clipping it. */}
      <div className="flex min-h-10 shrink-0 flex-wrap items-center gap-2 border-b bg-background px-3 py-1.5">
        <Button
          variant="ghost"
          size="sm"
          className="h-7 px-2 text-xs"
          onClick={handleBack}
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
              onClick={() => handleModeChange(value)}
            >
              {value === 'design' ? 'Design' : 'Arrange'}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <AutosaveIndicator
          status={autosave.status}
          savedAt={autosave.savedAt}
          onRetry={autosave.retry}
        />

        <FocusToggle
          active={focus}
          onToggle={setFocus}
          label="tags"
          className="h-7 text-xs"
          iconClassName="size-3.5"
        />

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

// ---------------------------------------------------------------------------
// Tag size control (D24, S9): W x H mm for the SELECTED line's tag
// ---------------------------------------------------------------------------

/** Key one preset is looked up under. */
function sizeKey(width_mm: number, height_mm: number): string {
  return `${width_mm}x${height_mm}`;
}

/**
 * Never a real option in the SELECT - a size nobody picked from the list has
 * nothing to select TO (S9 review nit). `value` is set to this whenever the
 * tag's current size matches no preset, so the trigger falls through to
 * `placeholder="Custom"` the same way every other unselected SearchableSelect
 * shows its placeholder: muted, and un-clickable in the list.
 */
const CUSTOM_SIZE_VALUE = '__custom__';

function TagSizeControl({
  tag,
  presets,
  imposition,
  onResize,
  onResizeAll,
}: {
  tag: PlacedTag | null;
  presets: TagSizePreset[];
  imposition: ImpositionConfig;
  onResize: (width_mm: number, height_mm: number) => void;
  onResizeAll: (width_mm: number, height_mm: number) => void;
}) {
  // Held as TEXT and committed on blur/Enter, not on every keystroke (S9
  // review B1): the control used to call `onResize` per keystroke, which
  // changed `tags` -> changed a doc key the canvas was mounted on -> remounted
  // the whole editor (this control's own DOM included) after the first
  // digit, so "95" typed as fast as anyone can type landed as "9". `null`
  // means "nothing typed right now" - the field shows the tag's live value,
  // which is what lets a preset pick or an Apply-to-all elsewhere update the
  // boxes without an effect fighting whatever is mid-typed in them.
  const [wDraft, setWDraft] = useState<string | null>(null);
  const [hDraft, setHDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!tag) {
    return (
      <div className="shrink-0 border-b border-r p-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Tag Size
        </span>
        <p className="mt-1 text-2xs text-muted-foreground">
          Select a line to set its tag size.
        </p>
      </div>
    );
  }

  const bounds = tagSizeBounds(imposition);

  const commit = (axis: 'w' | 'h') => {
    const draft = axis === 'w' ? wDraft : hDraft;
    const setDraft = axis === 'w' ? setWDraft : setHDraft;
    if (draft === null) return;
    const n = parseFloat(draft);
    if (Number.isNaN(n)) {
      setDraft(null);
      setError(null);
      return;
    }
    const candidateW = axis === 'w' ? n : tag.width_mm;
    const candidateH = axis === 'h' ? n : tag.height_mm;
    const result = resolveTagSize(candidateW, candidateH, bounds);
    if (!result.ok) {
      // Keep the typed value on screen next to the reason - reverting it
      // silently would read as the edit never happened (S9 review S3).
      setError(result.reason);
      return;
    }
    setError(null);
    onResize(result.width_mm, result.height_mm);
    setDraft(null);
  };

  const onEnter = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') e.currentTarget.blur();
  };

  const options: SearchableSelectOption[] = presets.map((p) => ({
    value: sizeKey(p.width_mm, p.height_mm),
    label: p.label,
  }));
  const matchingPreset = presets.find(
    (p) => p.width_mm === tag.width_mm && p.height_mm === tag.height_mm,
  );

  return (
    <div className="flex shrink-0 flex-col gap-2 border-b border-r p-3">
      <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
        Tag Size
      </span>
      <SearchableSelect
        value={matchingPreset ? sizeKey(matchingPreset.width_mm, matchingPreset.height_mm) : CUSTOM_SIZE_VALUE}
        onChange={(value) => {
          const preset = presets.find((p) => sizeKey(p.width_mm, p.height_mm) === value);
          if (!preset) return;
          const result = resolveTagSize(preset.width_mm, preset.height_mm, bounds);
          if (!result.ok) {
            setError(result.reason);
            return;
          }
          setError(null);
          onResize(result.width_mm, result.height_mm);
        }}
        options={options}
        placeholder="Custom"
      />
      <div className="grid grid-cols-2 gap-2">
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">W (mm)</Label>
          <Input
            type="number"
            className="h-7 px-2 text-xs"
            aria-label="Tag width (mm)"
            value={wDraft ?? tag.width_mm}
            step={0.5}
            onChange={(e) => setWDraft(e.target.value)}
            onBlur={() => commit('w')}
            onKeyDown={onEnter}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs text-muted-foreground">H (mm)</Label>
          <Input
            type="number"
            className="h-7 px-2 text-xs"
            aria-label="Tag height (mm)"
            value={hDraft ?? tag.height_mm}
            step={0.5}
            onChange={(e) => setHDraft(e.target.value)}
            onBlur={() => commit('h')}
            onKeyDown={onEnter}
          />
        </div>
      </div>
      {error && <p className="text-2xs text-destructive">{error}</p>}
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="h-7 text-xs"
        onClick={() => onResizeAll(tag.width_mm, tag.height_mm)}
      >
        Apply to all lines
      </Button>
    </div>
  );
}
