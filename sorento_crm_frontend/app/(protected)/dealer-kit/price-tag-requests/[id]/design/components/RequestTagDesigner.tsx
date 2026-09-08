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
 * debounced save through `onAutosave`, which writes the request's DRAFT.
 * `onSave` - the manual button, Mark design ready, Print sheet - is a
 * different act on a different route: it snapshots the design into an
 * immutable version, which is what export and proof rendering read (B1).
 * Autosaving through that route wrote a version per second and buried the
 * deliberate saves in noise.
 *
 * `flush()` (the debounce's own pending value, sent now, awaited) covers every
 * moment a ~1s wait is too slow to trust: switching Design/Arrange, switching
 * lines, the manual Save button making sure it is not racing an autosave, and
 * leaving the page - which is this component unmounting (the back link, the
 * sidebar, the browser's own Back) plus `pagehide` for a refresh or a close.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  ChevronLeft,
  Check,
  Copy,
  LayoutTemplate,
  Loader2,
  Eye,
  Maximize2,
  Minimize2,
  Save,
  RefreshCw,
} from 'lucide-react';
import { toast } from '@/lib/toast';
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
  TagTemplateFamily,
} from '@/lib/dealer-kit/tag-template-types';
import { IMPOSITION_PRESETS, familyLabel } from '@/lib/dealer-kit/tag-template-types';
import { lineFamily } from '@/lib/dealer-kit/line-family';
import {
  applyDesignToAllLines,
  applyDesignToSiblings,
  autoArrange,
  defaultTemplateFor,
  normaliseImpositionPreset,
  pinKeyForPlacement,
  pinnedFromDoc,
  resizeAllTags,
  resizeTag,
  starterTemplateFor,
  tagForLine,
  tagSizeBounds,
  tagSizePresets,
  tagsFromDoc,
  type ArrangeItem,
  type PinnedPlacement,
} from '@/lib/dealer-kit/request-tags';
import { formatTagPrice } from '@/lib/dealer-kit/price-badge';
import { TagCanvasEditor } from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import type { ToolbarTrailingAction } from '@/app/(protected)/dealer-kit/tag-templates/components/CanvasToolbar';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { useKitLibrary } from '@/app/(protected)/dealer-kit/tag-templates/components/useTagBindings';
import { TagSizeControl } from '@/app/(protected)/dealer-kit/components/TagSizeControl';
import { useAutosave } from '@/hooks/useAutosave';
import { ArrangeSheetView } from './ArrangeSheetView';
import { TemplatePickDialog } from './TemplatePickDialog';
import { SaveAsTemplateDialog } from './SaveAsTemplateDialog';
import { UpdateTemplateDialog } from './UpdateTemplateDialog';
import {
  resolveRequestLines,
  transitionPriceTagRequest,
  exportTagSheet,
  type PriceTagRequestDetail,
  type PriceTagRequestLine,
} from '../../../../services/priceTagRequestService';
import {
  listPublishedTemplates,
  publishTemplate,
  updateTemplate as updateTagTemplate,
} from '../../../../services/tagTemplateService';
import { FocusShell, FocusToggle } from '../../../../components/FocusMode';
import { AutosaveIndicator } from '../../../../components/AutosaveIndicator';
import {
  useDeleteTagSizePreset,
  useTagSizesQuery,
} from '../../../../tag-sizes/hooks/useTagSizes';
import { SaveAsSizeDialog } from './SaveAsSizeDialog';

let idSeq = 0;
function newTagId(): string {
  idSeq += 1;
  return `tag-${Date.now()}-${idSeq}`;
}

interface Props {
  request: PriceTagRequestDetail;
  initialDoc: TagSheetDoc | null;
  /** The deliberate save: snapshots a new version, toasts, rethrows (B1/B3). */
  onSave: (doc: TagSheetDoc) => Promise<void>;
  /** The autosave: writes the draft, silent, rethrows so the indicator can
   *  report a failure. `keepalive` is set only on the page-teardown flush. */
  onAutosave: (doc: TagSheetDoc, options?: { keepalive?: boolean }) => Promise<void>;
}

export function RequestTagDesigner({
  request,
  initialDoc,
  onSave,
  onAutosave,
}: Props) {
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
  // A pre-S6 doc's `a4_3up`/`a4_2x2` preset migrates to 'auto' on load (S3,
  // AC-S6-4) - the layout has been identical since S6, this just gets the
  // saved value to catch up so the next autosave writes 'auto' instead of
  // perpetuating history.
  const [imposition, setImposition] = useState<ImpositionConfig>(
    initialDoc?.imposition
      ? normaliseImpositionPreset(initialDoc.imposition)
      : { preset: 'auto', ...IMPOSITION_PRESETS.auto },
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
  /** "Save as template" (S4, D1): the currently designed tag, published in one go. */
  const [saveTemplateOpen, setSaveTemplateOpen] = useState(false);
  /** "Update <template>" (S6, D6): republish the source template from this line's design. */
  const [updateTemplateOpen, setUpdateTemplateOpen] = useState(false);
  const [updatingTemplate, setUpdatingTemplate] = useState(false);

  /**
   * The one bulk apply worth undoing (S5, AC-S5-3): "Apply this design to all
   * lines", or the template picker's "Apply to all lines" checkbox, or a
   * single-line template replace (D11 - the confirm dialog that used to guard
   * an edited tag is gone; this is the safety net instead). A ref, not state:
   * nothing on screen reads it directly, the toast's own "Undo" action and the
   * Cmd/Ctrl+Z handler below are the only two callers, and it is deliberately
   * ONE slot rather than a stack - the next tags edit of any kind retires it,
   * the same way a single `Ctrl+Z` only ever means "undo the last thing".
   */
  const bulkUndoRef = useRef<Record<string, PlacedTag> | null>(null);

  const [saving, setSaving] = useState(false);
  const [transitioning, setTransitioning] = useState(false);
  const [printing, setPrinting] = useState(false);

  const library = useKitLibrary();

  // -- Loading ---------------------------------------------------------------

  // A failed fetch gets an explicit, stays-put error state with Retry (AC-S3-3)
  // rather than a toast that vanishes and leaves the canvas silent. Only
  // PUBLISHED templates are eligible for request design (AC-S5-2).
  //
  // The loading and error states gate the canvas, so only the FIRST read may
  // use them (R2, #726). A later re-read - after "Save as new template", after
  // S6's Update - refreshes the list in place: swapping the canvas out for
  // "Loading templates..." mid-session unmounts the editor, and a canvas that
  // comes back is a canvas that has lost its selection, its zoom and its undo
  // history, and that re-seeds its layers from the `doc` prop. A refresh that
  // fails keeps the list already on screen rather than replacing a working
  // canvas with a Retry button.
  const templatesLoadedOnceRef = useRef(false);
  const loadTemplates = useCallback(() => {
    if (!templatesLoadedOnceRef.current) setTemplatesStatus('loading');
    listPublishedTemplates()
      .then((rows) => {
        templatesLoadedOnceRef.current = true;
        setTemplates(rows);
        setTemplatesStatus('loaded');
      })
      .catch(() => {
        if (!templatesLoadedOnceRef.current) setTemplatesStatus('error');
      });
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

  // Re-resolve line data when the designer regains focus (S2, AC-S2-1/2/3): a
  // barcode (or any other field) edited on the product in another tab must
  // reach an open Barcode layer without a reload. Silent on purpose - this
  // swaps `resolvedRows` on success and does nothing else, so a working canvas
  // never flashes the loading state and a failed background call never
  // replaces it with an error; `loadPrices` above already owns both of those
  // for the real, user-visible load.
  //
  // `focus` and `visibilitychange` -> `visible` fire together on most browsers
  // (switching back to this tab), so a 1s guard collapses the pair into one
  // resolve call rather than two.
  const lastRefreshRef = useRef(0);
  const refreshPricesSilently = useCallback(() => {
    const now = Date.now();
    if (now - lastRefreshRef.current < 1000) return;
    lastRefreshRef.current = now;
    resolveRequestLines(request.id)
      .then((rows) => setResolvedRows(rows))
      .catch(() => {
        // A background refresh that fails leaves the canvas showing whatever
        // it already had - the next focus/visibility change tries again.
      });
  }, [request.id]);

  useEffect(() => {
    const onFocus = () => refreshPricesSilently();
    const onVisibilityChange = () => {
      if (document.visibilityState === 'visible') refreshPricesSilently();
    };
    window.addEventListener('focus', onFocus);
    document.addEventListener('visibilitychange', onVisibilityChange);
    return () => {
      window.removeEventListener('focus', onFocus);
      document.removeEventListener('visibilitychange', onVisibilityChange);
    };
  }, [refreshPricesSilently]);

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
  //
  // This clone is NOT a user change (S3), so it only moves the autosave's
  // baseline - see the autosave effect below for why. `autoCloneRef` is how it
  // says so: set immediately before the state update whose `doc` the autosave
  // effect will then see.
  const autoCloneRef = useRef(false);
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
    autoCloneRef.current = true;
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
   * The document the canvas opens on: ALWAYS the tag as `tags` holds it right
   * now, never a snapshot (R2, #726).
   *
   * The editor reads `doc.layers` once, on mount, into its own state, and
   * ignores the prop from then on - so what this hands over only matters at
   * the moment the canvas mounts, and at that moment the only right answer is
   * the tag's LIVE layers. This used to be a ref frozen at the tag's id, on
   * the assumption that "mounts" and "the tag id changes" were the same
   * event. They are not: the ternary below swaps the editor out for a
   * message whenever Arrange is showing, or the templates or the prices are
   * loading, or either errored, and swaps it back in afterwards - same tag,
   * same id, a real unmount and remount. The frozen ref then handed the
   * canvas the layers as they stood when the line was FIRST selected, the
   * canvas came back holding them, and its own `onLayersChange` wrote them
   * over the live ones, so the next autosave persisted a design the user had
   * already moved on from. Measured on the lane: drag a barcode, Update
   * template, and the refetch that follows the publish put the barcode back
   * where it started (the ref carried an explicit exception for the Arrange
   * switch, which is why only the loading paths still bit).
   *
   * Width/height were never part of that identity (S9 review B1) and still
   * are not: the editor reads `doc.width_mm`/`height_mm` straight off the
   * prop on every render, so a resize reaches the artboard WITHOUT a remount,
   * and the key on tag id alone means it never unmounts a focused input in
   * the Tag Size control.
   */
  const selectedDoc: TagTemplateDoc | null = selectedTag
    ? {
        layers: selectedTag.layers,
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

  // -- Tag size control (D24, S9; lifted to a shared component, S1) -----------

  const sizePresets = useMemo(() => tagSizePresets(templates), [templates]);
  const savedSizesQuery = useTagSizesQuery();
  const deleteSavedSize = useDeleteTagSizePreset();
  const [saveSizeOpen, setSaveSizeOpen] = useState(false);
  const tagSizeBoundsForRequest = useMemo(() => tagSizeBounds(imposition), [imposition]);

  const handleResizeTag = useCallback(
    (width_mm: number, height_mm: number) => {
      const lineId = selectedLineId;
      if (!lineId) return;
      bulkUndoRef.current = null;
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
    bulkUndoRef.current = null;
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
        bulkUndoRef.current = null;
        return { ...prev, [lineId]: { ...tag, layers } };
      });
    },
    [selectedLineId],
  );

  /**
   * Undoes the one pending bulk apply (S5, AC-S5-3): the toast's own "Undo"
   * action and the Cmd/Ctrl+Z handler below are the only two callers. A
   * second press once the slot is empty is a no-op, same as pressing Undo
   * on a toast that already dismissed itself.
   */
  const undoBulkApply = useCallback(() => {
    const snapshot = bulkUndoRef.current;
    if (!snapshot) return;
    bulkUndoRef.current = null;
    setTags(snapshot);
  }, []);

  /**
   * A single line's tag is replaced with `template`, immediately - the
   * "Replace this tag with the template?" confirm is gone (D11, AC-S5-7);
   * Undo is the safety net instead, same toast + Cmd/Ctrl+Z as the two bulk
   * paths below.
   */
  const chooseTemplate = useCallback(
    (lineId: string, templateId: string) => {
      const line = request.lines.find((l) => l.id === lineId);
      const template = templates.find((t) => t.id === templateId);
      if (!line || !template) return;
      bulkUndoRef.current = tags;
      applyTemplate(line, template);
      toast.success('Template applied', {
        action: { label: 'Undo', onClick: undoBulkApply },
      });
      setPickerLineId(null);
      setSelectedLineId(lineId);
    },
    [request.lines, templates, tags, applyTemplate, undoBulkApply],
  );

  /**
   * The picker's "Apply to all lines" checkbox (AC-S5-4): every line gets a
   * PRISTINE clone of the chosen template via `tagForLine` - the same clone a
   * line gets when it is opened for the first time, not the design that is
   * currently on `focusLineId`'s canvas. That is the whole difference from
   * `handleApplyDesignToAll` below: this spreads a TEMPLATE, that spreads a
   * DESIGN.
   */
  const chooseTemplateForAllLines = useCallback(
    (templateId: string, focusLineId: string) => {
      const template = templates.find((t) => t.id === templateId);
      if (!template) return;
      bulkUndoRef.current = tags;
      const next: Record<string, PlacedTag> = { ...tags };
      for (const line of request.lines) {
        let tag = tagForLine(line, template, newTagId());
        if (defaultTagSize) {
          tag = resizeTag(tag, defaultTagSize.width_mm, defaultTagSize.height_mm);
        }
        next[line.id] = tag;
      }
      setTags(next);
      toast.success(`Applied to ${request.lines.length} line${request.lines.length === 1 ? '' : 's'}`, {
        action: { label: 'Undo', onClick: undoBulkApply },
      });
      setPickerLineId(null);
      setSelectedLineId(focusLineId);
    },
    [templates, tags, request.lines, defaultTagSize, undoBulkApply],
  );

  const handleTemplateChosen = useCallback(
    (templateId: string, applyToAll: boolean) => {
      const lineId = pickerLineId;
      if (!lineId) return;
      if (applyToAll) {
        chooseTemplateForAllLines(templateId, lineId);
      } else {
        chooseTemplate(lineId, templateId);
      }
    },
    [pickerLineId, chooseTemplate, chooseTemplateForAllLines],
  );

  /**
   * The Lines rail's "Apply this design to all lines" (AC-S5-1/2/3): the
   * SELECTED line's tag, edits included, cloned onto every other line -
   * `applyDesignToAllLines` does the rebinding and the fresh ids, this is
   * only the undo snapshot + toast plumbing shared with the two paths above.
   */
  const handleApplyDesignToAll = useCallback(() => {
    if (!selectedLineId || !tags[selectedLineId]) return;
    const count = request.lines.length - 1;
    if (count <= 0) return;
    bulkUndoRef.current = tags;
    setTags(applyDesignToAllLines(tags, request.lines, selectedLineId, newTagId));
    toast.success(`Applied to ${count} line${count === 1 ? '' : 's'}`, {
      action: { label: 'Undo', onClick: undoBulkApply },
    });
  }, [selectedLineId, tags, request.lines, undoBulkApply]);

  // Cmd/Ctrl+Z restores the one pending bulk apply (AC-S5-3) - only while
  // there is one: with nothing armed, the key falls through untouched to
  // whatever else on the page wants it (the canvas's own layer-history
  // undo). Captured on `window`'s CAPTURE phase, ahead of that handler,
  // so this can `stopPropagation()` and be the only one of the two that
  // fires - the alternative, both firing, would undo a canvas edit AND
  // restore every other line's tag off one keystroke.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const isInput =
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLTextAreaElement ||
        e.target instanceof HTMLSelectElement;
      if (isInput) return;
      if (!bulkUndoRef.current) return;
      const modifier = e.ctrlKey || e.metaKey;
      if (!modifier || e.key.toLowerCase() !== 'z' || e.shiftKey) return;
      e.preventDefault();
      e.stopPropagation();
      undoBulkApply();
    };
    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, [undoBulkApply]);

  // -- The document ----------------------------------------------------------

  const arrangeItems: ArrangeItem[] = useMemo(
    () =>
      request.lines
        .map((line) => ({ tag: tags[line.id], quantity: line.quantity }))
        .filter((item): item is ArrangeItem => Boolean(item.tag)),
    [request.lines, tags],
  );

  // The size Arrange's fit line and empty state are computed off (S6): the
  // largest tag REQUESTED across every line, not what `autoArrange` managed
  // to place - a page too small for the tag places nothing, and that is
  // exactly when the "0 per sheet" message most needs a size to quote.
  const tagDims = useMemo(() => {
    if (arrangeItems.length === 0) return null;
    return {
      width_mm: Math.max(...arrangeItems.map((item) => item.tag.width_mm)),
      height_mm: Math.max(...arrangeItems.map((item) => item.tag.height_mm)),
    };
  }, [arrangeItems]);

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

  // Set the moment the page is going away, and read by the save below so ONLY
  // the teardown request is sent `keepalive` (a keepalive body is capped at
  // 64KB, which a busy tag sheet exceeds - see the service).
  const teardownRef = useRef(false);
  const { status, savedAt, schedule, flush, retry } = useAutosave<TagSheetDoc>(
    useCallback(
      (next: TagSheetDoc) => onAutosave(next, { keepalive: teardownRef.current }),
      [onAutosave],
    ),
  );

  // Every REAL change to `doc` schedules a debounced save - a layer edit
  // (through `tags`), an arranged pin, an imposition change. Two changes are
  // NOT edits and must persist nothing:
  //
  //  * the very first `doc` (whatever `initialDoc` seeded, or the empty
  //    starting point) - already exactly what the server has;
  //  * the starter/template CLONE the effect above performs for a line that
  //    has no tag yet (S3). That is the page deciding what to draw, not the
  //    user deciding anything, so merely OPENING a request with undesigned
  //    lines - or clicking down the rail to look at them - used to write a
  //    design for every one of them. The clone announces itself through
  //    `autoCloneRef` and only moves the baseline. Choosing a template from
  //    the picker goes through `chooseTemplate`, never through here, so a real
  //    choice still saves.
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
    const isAutoClone = autoCloneRef.current;
    autoCloneRef.current = false;
    lastSeenDocRef.current = doc;
    if (isInitial || isAutoClone) return;
    schedule(doc);
  }, [doc, schedule]);

  // Leaving the page, both ways it can happen (S1/S2).
  //
  // A route change inside the app - the back link, a sidebar click, the
  // browser's own Back - unmounts this component, so the cleanup below is
  // where that edit gets its last chance. `pagehide` covers what no React
  // lifecycle sees: a refresh, a closed tab, a jump to another site. It
  // replaces `beforeunload`, which fires too early to be the whole story and
  // is throttled or skipped outright on mobile Safari, where a backgrounded
  // tab is discarded without one.
  //
  // Both set `teardownRef` first so the request goes out `keepalive` and
  // survives the document it was made from.
  useEffect(() => {
    // A mounted page is not tearing down. StrictMode's mount/cleanup/mount
    // pass would otherwise leave the flag set for the whole session, and
    // every ordinary autosave after it would go out keepalive - which fails
    // outright once the document passes 64KB.
    teardownRef.current = false;
    const handler = () => {
      teardownRef.current = true;
      void flush();
    };
    window.addEventListener('pagehide', handler);
    return () => {
      window.removeEventListener('pagehide', handler);
      handler();
    };
  }, [flush]);

  const handleMoveTag = useCallback(
    (sheetIndex: number, tag: PlacedTag, x_mm: number, y_mm: number) => {
      setPinned((prev) => ({
        ...prev,
        [pinKeyForPlacement(tag)]: { sheet: sheetIndex, x_mm, y_mm },
      }));
    },
    [],
  );

  /**
   * The deliberate save: one version, and never racing the autosave (S4).
   *
   * `flush()` first - it cancels the armed debounce and waits for anything on
   * the wire, so a draft write cannot land AFTER this version snapshot and
   * resurrect a draft the snapshot just cleared. With nothing pending it is a
   * no-op, which is the ordinary case: this stays one request.
   *
   * The toast lives in the host's `onSave` (B3), and so does the error one -
   * which is also why the rejection is swallowed here rather than reported
   * twice.
   */
  const saveNow = useCallback(async () => {
    await flush();
    await onSave(doc);
  }, [flush, doc, onSave]);

  const save = useCallback(async () => {
    setSaving(true);
    try {
      await saveNow();
    } catch {
      // Already reported by `onSave`.
    } finally {
      setSaving(false);
    }
  }, [saveNow]);

  const handleMarkProofReady = useCallback(async () => {
    setTransitioning(true);
    try {
      // A failed save now ABORTS rather than marking a proof ready off a
      // design the server never received (B3: `onSave` rethrows).
      await saveNow();
      // A STATUS, not an action name: see the note on the detail page.
      await transitionPriceTagRequest(request.id, 'proof_ready');
      toast.success('Design marked as ready');
      router.push(`/dealer-kit/price-tag-requests/${request.id}`);
    } catch {
      toast.error('Failed to mark the design ready');
    } finally {
      setTransitioning(false);
    }
  }, [saveNow, request.id, router]);

  const handlePrintSheet = useCallback(
    async (sheetIndex: number) => {
      const sheet = doc.sheets[sheetIndex];
      if (!sheet) return;
      setPrinting(true);
      try {
        // Saved first: the worker prints the latest VERSION, and an unsaved
        // arrangement would print the previous one.
        await saveNow();
        await exportTagSheet(request.id, [sheet.id]);
        toast.success(`Sheet ${sheetIndex + 1} export queued. Check My Downloads.`);
      } catch {
        toast.error('Failed to export the sheet');
      } finally {
        setPrinting(false);
      }
    },
    [doc.sheets, saveNow, request.id],
  );

  const canMarkProofReady =
    request.status === 'designing' || request.status === 'changes_requested';

  /** Switching a line never LOSES a committed change (AC-S8-3) - flush the
   *  autosave's own pending value before the switch, rather than leaving it
   *  to the ~1s debounce that might not have fired yet. */
  const handleSelectLine = useCallback(
    (lineId: string) => {
      if (lineId !== selectedLineId) void flush();
      setSelectedLineId(lineId);
    },
    [selectedLineId, flush],
  );

  /** Same idea for Design <-> Arrange (AC-S8-3). */
  const handleModeChange = useCallback(
    (value: 'design' | 'arrange') => {
      if (value !== mode) void flush();
      setMode(value);
    },
    [mode, flush],
  );

  // The unmount cleanup flushes too, so this is only about being EARLY: the
  // save leaves before the route change rather than after it.
  const handleBack = useCallback(() => {
    void flush();
    router.push(`/dealer-kit/price-tag-requests/${request.id}`);
  }, [flush, router, request.id]);

  // -- Save as template (S4, D1) -----------------------------------------------

  const selectedLine = selectedLineId
    ? request.lines.find((l) => l.id === selectedLineId) ?? null
    : null;
  const selectedLineCode = selectedLineId ? resolved.get(selectedLineId)?.code ?? '' : '';
  const saveTemplateDefaultName = selectedLineCode ? `${selectedLineCode} tag` : 'New tag';
  const saveTemplateDefaultFamily = (
    selectedLine ? lineFamily(selectedLine, selectedLineCode) : 'ala_carte'
  ) as TagTemplateFamily;

  const handleTemplateCreated = useCallback(
    (created: TagTemplate) => {
      // A real refetch, not a local splice: the picker's source is the
      // backend's own published list (AC-S4-8), and this is what keeps it
      // agreeing with what a reload would show.
      loadTemplates();
      toast.success(`Template "${created.name}" published`, {
        action: {
          label: 'Open',
          onClick: () => router.push(`/dealer-kit/tag-templates/${created.id}`),
        },
      });
    },
    [router, loadTemplates],
  );

  // -- Update template (S6, D6) -------------------------------------------------

  // Only PUBLISHED templates are eligible - `templates` is already
  // `listPublishedTemplates()`'s own result, so a template someone deleted
  // or never published resolves to null and the Template menu offers only
  // "Save as new template" (AC-S6-1).
  const updateEligibleTemplate = selectedTag
    ? templates.find((t) => t.id === selectedTag.template_id) ?? null
    : null;
  const updateSiblingCount =
    selectedTag && updateEligibleTemplate
      ? request.lines.filter(
          (l) =>
            l.id !== selectedLineId && tags[l.id]?.template_id === updateEligibleTemplate.id,
        ).length
      : 0;
  const updateNextVersionNo = (updateEligibleTemplate?.published_version_no ?? 0) + 1;

  const handleUpdateTemplate = useCallback(
    async (applyToSiblings: boolean) => {
      if (!selectedTag || !selectedLineId || !updateEligibleTemplate) return;
      setUpdatingTemplate(true);
      try {
        // Existing PUT (S1's updateTemplate carries print_size too now) then
        // the existing publish route - no new backend for this slice. Bound
        // layers lose their `text_override` here too - same rule
        // `templateFromTag` applies for "Save as new template": a value
        // typed for THIS line (a price, a name) is not the shared template's
        // to keep, only the slot binding is.
        await updateTagTemplate(updateEligibleTemplate.id, {
          layers: selectedTag.layers.map((layer) => ({
            ...layer,
            text_override: layer.slot_binding ? null : layer.text_override,
          })),
          width_mm: selectedTag.width_mm,
          height_mm: selectedTag.height_mm,
        });
        const published = await publishTemplate(
          updateEligibleTemplate.id,
          `Updated from ${request.doc_number}`,
        );
        if (applyToSiblings && updateSiblingCount > 0) {
          bulkUndoRef.current = tags;
          setTags(
            applyDesignToSiblings(
              tags,
              request.lines,
              selectedLineId,
              updateEligibleTemplate.id,
              newTagId,
            ),
          );
          toast.success(
            `Updated "${updateEligibleTemplate.name}" (v${published.published_version_no}) and applied to ${updateSiblingCount} other line${updateSiblingCount === 1 ? '' : 's'}`,
            { action: { label: 'Undo', onClick: undoBulkApply } },
          );
        } else {
          toast.success(
            `Updated "${updateEligibleTemplate.name}" (v${published.published_version_no})`,
          );
        }
        // Refetches the published list (AC-S6-3): the Template menu, the
        // size presets and the "Use template..." picker all read from it.
        loadTemplates();
        setUpdateTemplateOpen(false);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Could not update the template');
      } finally {
        setUpdatingTemplate(false);
      }
    },
    [
      selectedTag,
      selectedLineId,
      updateEligibleTemplate,
      updateSiblingCount,
      tags,
      request.lines,
      request.doc_number,
      loadTemplates,
      undoBulkApply,
    ],
  );

  // -- Render ----------------------------------------------------------------

  // The canvas toolbar's own right-end group (S7): Full screen, the
  // Template dropdown (S6) and Save. Only reaches the screen in design
  // mode - it is handed to TagCanvasEditor, which only mounts there;
  // arrange mode keeps its own Full screen + Save in the request bar
  // below, since ArrangeSheetView has no canvas toolbar of its own to
  // move them into (AC-S7-5 holds for free the same way).
  const toolbarTrailing: ToolbarTrailingAction[] = [
    {
      id: 'full-screen',
      icon: focus ? Minimize2 : Maximize2,
      label: focus ? 'Exit full screen' : 'Full screen',
      onClick: () => setFocus(!focus),
      active: focus,
    },
    {
      id: 'template',
      kind: 'menu',
      icon: LayoutTemplate,
      label: 'Template',
      disabled: !selectedTag,
      items: (
        <>
          {updateEligibleTemplate && (
            <DropdownMenuItem onSelect={() => setUpdateTemplateOpen(true)}>
              Update &quot;{updateEligibleTemplate.name}&quot;
            </DropdownMenuItem>
          )}
          <DropdownMenuItem onSelect={() => setSaveTemplateOpen(true)}>
            Save as new template
          </DropdownMenuItem>
        </>
      ),
    },
    {
      id: 'save',
      icon: saving ? Loader2 : Save,
      iconClassName: saving ? 'animate-spin' : undefined,
      label: saving ? 'Saving...' : 'Save',
      onClick: save,
      disabled: saving || transitioning,
    },
  ];

  const rail = (
    <>
      <LinesRail
        lines={request.lines}
        resolved={resolved}
        pricesStatus={pricesStatus}
        tags={tags}
        selectedLineId={selectedLineId}
        onSelect={handleSelectLine}
        onUseTemplate={setPickerLineId}
        canApplyToAll={Boolean(selectedTag) && request.lines.length > 1}
        onApplyToAll={handleApplyDesignToAll}
      />
      {selectedTag ? (
        <TagSizeControl
          width_mm={selectedTag.width_mm}
          height_mm={selectedTag.height_mm}
          presets={sizePresets}
          savedSizes={savedSizesQuery.data}
          bounds={tagSizeBoundsForRequest}
          onResize={handleResizeTag}
          onResizeAll={handleResizeAllTags}
          onDeleteSavedSize={(id, name) => deleteSavedSize.run({ id, subject: name })}
          deletingSavedSizeId={deleteSavedSize.isPending ? deleteSavedSize.targetId : null}
          onSaveAsSize={() => setSaveSizeOpen(true)}
        />
      ) : (
        <div className="shrink-0 border-b border-r p-3">
          <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Tag Size
          </span>
          <p className="mt-1 text-2xs text-muted-foreground">
            Select a line to set its tag size.
          </p>
        </div>
      )}
      {selectedTag && (
        <SaveAsSizeDialog
          open={saveSizeOpen}
          onOpenChange={setSaveSizeOpen}
          width_mm={selectedTag.width_mm}
          height_mm={selectedTag.height_mm}
        />
      )}
    </>
  );

  return (
    <FocusShell active={focus} onExit={() => setFocus(false)}>
    <div className="flex h-full min-h-0 flex-1 flex-col">
      {/* Request bar: what this is, which half is showing, the Saved
          indicator and - in design mode - the ONE action, Mark design ready
          (S7, AC-S7-1). Full screen, the Template dropdown and Save moved
          into the canvas toolbar's own trailing group below; arrange mode
          keeps its own Full screen + Save here, since ArrangeSheetView has
          no canvas toolbar of its own to move them into.
          `flex-wrap`: at 375px the back button, mode toggle and (arrange
          mode, or a designing request) the remaining actions do not fit one
          row - `min-h-10` rather than a fixed `h-10` so the row can
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

        <AutosaveIndicator status={status} savedAt={savedAt} onRetry={retry} />

        {mode === 'arrange' && (
          <>
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
          </>
        )}

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
            Mark design ready
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
              docId={selectedTag.id}
              toolbarTrailing={toolbarTrailing}
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
            tagDims={tagDims}
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

      <SaveAsTemplateDialog
        open={saveTemplateOpen}
        onOpenChange={setSaveTemplateOpen}
        tag={selectedTag}
        defaultName={saveTemplateDefaultName}
        defaultFamily={saveTemplateDefaultFamily}
        onCreated={handleTemplateCreated}
      />

      {updateEligibleTemplate && (
        <UpdateTemplateDialog
          open={updateTemplateOpen}
          onOpenChange={setUpdateTemplateOpen}
          templateName={updateEligibleTemplate.name}
          nextVersionNo={updateNextVersionNo}
          siblingCount={updateSiblingCount}
          saving={updatingTemplate}
          onConfirm={handleUpdateTemplate}
        />
      )}
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
  pricesStatus,
  tags,
  selectedLineId,
  onSelect,
  onUseTemplate,
  canApplyToAll,
  onApplyToAll,
}: {
  lines: PriceTagRequestLine[];
  resolved: Map<string, LineTagData>;
  pricesStatus: 'loading' | 'loaded' | 'error';
  tags: Record<string, PlacedTag>;
  selectedLineId: string | null;
  onSelect: (lineId: string) => void;
  onUseTemplate: (lineId: string) => void;
  /** Something is selected AND there is more than one line to spread it to (AC-S5-1). */
  canApplyToAll: boolean;
  onApplyToAll: () => void;
}) {
  return (
    <div className="flex max-h-[45%] shrink-0 flex-col border-b border-r">
      <div className="flex h-10 shrink-0 items-center justify-between gap-1 border-b px-3">
        <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Lines
        </span>
        <button
          type="button"
          className="flex shrink-0 items-center gap-1 rounded p-1 text-2xs text-muted-foreground hover:bg-accent hover:text-foreground disabled:pointer-events-none disabled:opacity-40"
          title="Apply this design to all lines"
          disabled={!canApplyToAll}
          onClick={onApplyToAll}
        >
          <Copy className="size-3" />
          Apply to all
        </button>
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
              // Prices resolution finished and this line still has no row: its
              // product could not be resolved in this request's company (a
              // cross-company reference, or a genuinely deleted product) - not
              // "still loading". See `457_ptag_line_xco_repair`.
              const notFound = pricesStatus === 'loaded' && !row;
              const code = row?.code ?? '';
              const name = row?.name ?? '';
              // Sorento's product name IS its code (S2): a name that only
              // repeats the code is redundant on the rail as it is on the tag.
              const showName =
                name !== '' && name.trim().toLowerCase() !== code.trim().toLowerCase();
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
                        {code || (notFound ? 'Not found' : 'Resolving...')}
                      </span>
                      {designed && (
                        <Check className="size-3 shrink-0 text-emerald-600" />
                      )}
                    </div>
                    {notFound ? (
                      <Badge
                        variant="destructive"
                        appearance="light"
                        className="mt-1 px-1.5 py-0 text-2xs font-normal"
                      >
                        Product not found in this company
                      </Badge>
                    ) : (
                      <>
                        {showName && (
                          <p className="mt-0.5 truncate text-xs" title={name}>
                            {name}
                          </p>
                        )}
                        <p className="mt-0.5 truncate text-2xs text-muted-foreground">
                          Qty {line.quantity} / {family}
                          {row && row.show_promo_price && row.sell_price != null
                            ? ` / SP ${formatTagPrice(row.sell_price)}`
                            : row && row.list_price != null
                              ? ` / LP ${formatTagPrice(row.list_price)}`
                              : ''}
                        </p>
                      </>
                    )}
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

