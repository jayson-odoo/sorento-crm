'use client';

import * as React from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  ChevronDown,
  ChevronUp,
  FileDown,
  Minus,
  Plus,
  Redo2,
  Trash2,
  Undo2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Skeleton } from '@/components/ui/skeleton';
import RecordNavigation from '@/components/common/RecordNavigation';
import { PageHeader } from '@/components/common/PageHeader';
import { projectCrumbs } from '../../../../../../_shared/lib/crumbs';
import DetailActions from '@/components/common/DetailActions';
import BackToList from '@/components/common/BackToList';
import type { RecordAction } from '@/components/common/recordActions';
import { PX_PER_MM } from '@/components/dealer-kit/ScaledSheet';
import { clampZoom, ZOOM_STEP } from '@/components/common/pdf-viewer/zoom';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useIsMobile } from '@/hooks/use-mobile';
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle,
} from '@/components/ui/drawer';
import type { EmbeddedController } from '@/app/(protected)/dealer-kit/tag-templates/components/TagCanvasEditor';
import {
  CollapsiblePanel,
  FocusShell,
  FocusToggle,
} from '@/app/(protected)/dealer-kit/components/FocusMode';
import type {
  TagLayer,
  TagLayerProps,
} from '@/lib/dealer-kit/tag-template-types';

import {
  specSheetListKey,
  useSpecSheetDetail,
  useSpecSheetMutations,
  useSpecSheetPageImages,
  useSpecSheetPreviews,
} from '../../../../../../_shared/hooks/useSpecSheet';
import type {
  ApplyAllChanges,
  SpecSheetPage,
  SpecSheetRow,
} from '../../../../../../_shared/services/specSheetService';
import { CreateSpecSheetDialog } from '../../../components/CreateSpecSheetDialog';
import { FormatBar } from './FormatBar';
import { PageRail, type RailPicture } from './PageRail';
import { ReaderInspector, type ApplyMode } from './ReaderInspector';
import { applicableChanges, movedKeys } from './selectionTools';
import { useSheetEditing } from './useSheetEditing';
import { COVER, ReaderPage } from './ReaderPage';

/** Scroll the page stack (only the stack, never the window) so that page's top sits at its top. */
function scrollStackTo(stack: HTMLElement | null, key: string) {
  if (!stack) return;
  const el = Array.from(
    stack.querySelectorAll<HTMLElement>('[data-page-wrap]'),
  ).find((node) => node.getAttribute('data-page-wrap') === key);
  if (!el) return;
  const top =
    el.getBoundingClientRect().top -
    stack.getBoundingClientRect().top +
    stack.scrollTop;
  stack.scrollTo?.({ top: Math.max(0, top - 8) });
}

/** How long "Every page" waits for the user to pause before it sends what was changed. */
export const APPLY_ALL_MS = 600;

/** Pages per preview call. The window snaps to these chunks, so a scroll that stays inside one
 *  costs nothing and a scroll back is a cache hit. Well under the server's 12-key limit. */
const CHUNK_SIZE = 6;
/** The most pages drawn at once, however far the viewport is zoomed out. */
const DRAWN_MAX = 12;
/** The window starts one viewport above and below what is on screen. */
const WINDOW_MARGIN = '100% 0px';
/** The page being read must stay put this long before its sharper pictures are asked for. */
const SETTLE_MS = 250;
/** Pages that draw the live designer at once; the others stay still pictures. */
const LIVE_MAX = 3;
/** Side padding of the stack, px. */
const STACK_PAD = 16;
/** Scale before the stack has been measured. */
const FALLBACK_SCALE = 0.4;

/** What the server keeps for a page. An AREA equal to its Section heading is not "typed". */
function rowOf(page: SpecSheetPage): SpecSheetRow {
  return {
    key: page.key,
    area: page.area === page.area_default ? '' : page.area,
    comment: page.comment,
    marker: page.marker,
    hidden: page.hidden,
    accessories: page.picked,
  };
}

/**
 * The spec sheet read like a PDF: every page stacked top to bottom at the template size, a rail of
 * page labels, page N of M, zoom and fit width.
 *
 * Performance rules (owner, 3 Nov): one list-free detail call on open; one fixed-size box per page
 * sized from `page_size`; an IntersectionObserver decides the visible window; ONE preview call per
 * window (thumbnail images, at most 12 keys); only the pages in the window mount a renderer, the
 * rest unmount. The rail draws no renderer at all.
 */
export function SpecSheetReader({
  projectId,
  documentId,
  sheetId,
}: {
  projectId: string;
  documentId: string;
  sheetId: string;
}) {
  const router = useRouter();
  const isMobile = useIsMobile();
  const detailQuery = useSpecSheetDetail(projectId, documentId, sheetId);
  const { update, exportPdf } = useSpecSheetMutations(projectId, documentId);
  const detail = detailQuery.data;
  // A cover or page template deleted before deleting was blocked: nothing can be drawn or exported
  // until the templates are picked again.
  const missing = detail?.templates_missing ?? [];
  const blockedBy = missing.filter((m) => m === 'cover' || m === 'page');
  const blocked = blockedBy.length > 0;
  const [picking, setPicking] = React.useState(false);
  // Full screen and the two folding side panels: the same FocusShell / FocusToggle /
  // CollapsiblePanel the price tag designer, room designer and page builder use.
  const [focus, setFocus] = React.useState(false);
  const exitFocus = React.useCallback(() => setFocus(false), []);
  const [railCollapsed, setRailCollapsed] = React.useState(false);
  const [inspectorCollapsed, setInspectorCollapsed] = React.useState(false);

  const listHref = `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet`;
  const sheetHref = (id: string) => `${listHref}/${id}`;

  // Local copy of the pages while a write is in flight, so a drag or a toggle lands at once.
  const [override, setOverride] = React.useState<SpecSheetPage[] | null>(null);
  const detailPages = detail?.pages;
  const pages = React.useMemo(
    () => override ?? detailPages ?? [],
    [override, detailPages],
  );

  // Page numbers count printed pages only; the cover is page 1.
  const numbers = React.useMemo(() => {
    const map = new Map<string, number>();
    let printed = 0;
    for (const page of pages)
      if (page.key === COVER || !page.hidden) map.set(page.key, ++printed);
    return map;
  }, [pages]);
  const printedCount = numbers.size;

  // ---- editing: selection, per-page autosave and undo (F4) -----------------------------------

  const searchParams = useSearchParams();
  const editing = useSheetEditing(projectId, documentId, sheetId);
  const { applyAll } = useSpecSheetMutations(projectId, documentId);
  const [selection, setSelection] = React.useState<{
    pageKey: string;
    layerId: string;
  } | null>(null);
  const [applyMode, setApplyMode] = React.useState<ApplyMode>('page');
  // Bumped when the server replaced other pages' layers (Apply to every page): live canvases restart.
  // Per page, so the page the apply started from keeps its canvas (its selection, undo and any
  // edit still on its way) and only the pages the server changed start over.
  const [restarts, setRestarts] = React.useState<Record<string, number>>({});
  const controllers = React.useRef(
    new Map<string, React.MutableRefObject<EmbeddedController | null>>(),
  );
  const controllerRefFor = React.useCallback((key: string) => {
    let ref = controllers.current.get(key);
    if (!ref) {
      ref = { current: null };
      controllers.current.set(key, ref);
    }
    return ref;
  }, []);
  const onSelectLayer = React.useCallback(
    (key: string, layerId: string | null) => {
      setSelection((prev) =>
        layerId === null
          ? prev?.pageKey === key
            ? null
            : prev
          : { pageKey: key, layerId },
      );
    },
    [],
  );
  const { report } = editing;
  // Phone: picking a layer leaves the canvas free to drag; the inspector sheet opens on demand and
  // the layer's page is brought to the top so the sheet never covers it.
  const [sheetOpen, setSheetOpen] = React.useState(false);
  const selectedPageKey = selection?.pageKey ?? null;
  React.useEffect(() => {
    if (!selection) setSheetOpen(false);
  }, [selection]);
  const openSheet = () => {
    setSheetOpen(true);
    // This scroll is the reader's, not a page pick: the counter follows the position again.
    pinned.current = null;
    const stack = scroller.current;
    if (!selectedPageKey || !stack) return;
    // The stack to the top of the screen (on a phone it starts below where the sheet opens), then
    // the selected layer to the top of the stack: it stays in view above the sheet.
    stack.scrollIntoView?.({ block: 'start' });
    const box = stack.querySelector<HTMLElement>(
      `[data-page-key="${CSS.escape(selectedPageKey)}"]`,
    );
    if (!box) return;
    const layerTop = (selectedLayer?.y_mm ?? 0) * PX_PER_MM * scale;
    stack.scrollTo?.({
      top: Math.max(
        0,
        box.getBoundingClientRect().top -
          stack.getBoundingClientRect().top +
          stack.scrollTop +
          layerTop -
          16,
      ),
    });
  };

  // The local copy stays until the LAST write in flight settles; clearing it on the first would
  // flash the older server copy between two quick edits.
  const inflight = React.useRef(0);
  const commit = (next: SpecSheetPage[]) => {
    setOverride(next);
    inflight.current += 1;
    update
      .mutateAsync({
        sheetId,
        body: { rows: next.filter((p) => p.key !== COVER).map(rowOf) },
      })
      .catch(() => undefined)
      .finally(() => {
        inflight.current -= 1;
        if (inflight.current === 0) setOverride(null);
      });
  };
  // Stable for the memoised pages: it reads the latest pages / commit through refs, so a page
  // change elsewhere in the stack does not re-render every page (and its Add accessory picker).
  const pagesRef = React.useRef(pages);
  pagesRef.current = pages;
  const commitRef = React.useRef(commit);
  commitRef.current = commit;
  const patch = React.useCallback(
    (key: string, change: Partial<SpecSheetPage>) =>
      commitRef.current(
        pagesRef.current.map((page) =>
          page.key === key ? { ...page, ...change } : page,
        ),
      ),
    [],
  );

  // ---- the stack: measured width, zoom, the visible window ---------------------------------

  const scroller = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);
  const [zoom, setZoom] = React.useState<number | null>(null);
  // The thumbnails in the rail's own view; their chunks load through the same queries.
  const [railVisible, setRailVisible] = React.useState<ReadonlySet<string>>(
    new Set(),
  );
  const [currentKey, setCurrentKey] = React.useState<string | null>(null);

  // The scroller only exists once the sheet has loaded.
  const loaded = detail !== undefined;
  React.useEffect(() => {
    const node = scroller.current;
    if (!node) return;
    const measure = () => setWidth(node.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, [loaded, blocked]);

  const naturalW = (detail?.page_size.width_mm ?? 0) * PX_PER_MM;
  const naturalH = (detail?.page_size.height_mm ?? 0) * PX_PER_MM;
  const fitScale =
    naturalW > 0 && width > 0
      ? Math.max(0.1, (width - STACK_PAD * 2) / naturalW)
      : FALLBACK_SCALE;
  const scale = zoom ?? fitScale;
  const boxWidth = Math.round(naturalW * scale);
  const boxHeight = Math.round(naturalH * scale);

  // Pages near the viewport (the observer's margin included), in a state that only changes when
  // the set does.
  const [visible, setVisible] = React.useState<ReadonlySet<string>>(new Set());
  const visibleRef = React.useRef<Set<string>>(new Set());

  const publishVisible = React.useCallback(() => {
    const next = visibleRef.current;
    setVisible((prev) =>
      prev.size === next.size && [...next].every((k) => prev.has(k))
        ? prev
        : new Set(next),
    );
  }, []);

  const pageKeys = pages.map((p) => p.key).join('|');
  React.useEffect(() => {
    const root = scroller.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          const key = entry.target.getAttribute('data-page-key');
          if (!key) continue;
          if (entry.isIntersecting) visibleRef.current.add(key);
          else visibleRef.current.delete(key);
        }
        publishVisible();
      },
      { root, rootMargin: WINDOW_MARGIN },
    );
    root
      .querySelectorAll('[data-page-key]')
      .forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [pageKeys, publishVisible, blocked]);

  // The window: the chunks (fixed groups of CHUNK_SIZE pages in print order) holding any visible
  // page, normally one or two. One preview query per chunk.
  const chunks = React.useMemo(() => {
    const all: string[][] = [];
    for (let at = 0; at < pages.length; at += CHUNK_SIZE) {
      all.push(pages.slice(at, at + CHUNK_SIZE).map((p) => p.key));
    }
    return all;
  }, [pages]);
  const windowChunks = React.useMemo(
    () =>
      chunks.filter((keys) =>
        keys.some((k) => visible.has(k) || railVisible.has(k)),
      ),
    [chunks, visible, railVisible],
  );
  const previews = useSpecSheetPreviews(
    projectId,
    documentId,
    sheetId,
    windowChunks,
  );

  // key -> the payload that holds its sheet, for every page whose chunk has arrived. One payload
  // object per fetched answer, so a page's props stay the same between renders.
  const payloads = React.useRef(new WeakMap<object, TagSheetDesignPayload>());
  const loadedPictures = new Map<string, RailPicture>();
  for (const result of previews) {
    const data = result.data;
    if (!data) continue;
    let payload = payloads.current.get(data);
    if (!payload) {
      payload = {
        ...data,
        page_id: '',
        source: 'version',
      } as TagSheetDesignPayload;
      payloads.current.set(data, payload);
    }
    const shared = payload;
    (data.doc?.sheets ?? []).forEach((sheet, index) => {
      const key = sheet.tags[0]?.request_tag_id;
      if (key) loadedPictures.set(key, { payload: shared, index });
    });
  }
  // The stack draws the pages near the viewport that have arrived, left-out pages never.
  const hiddenKeys = new Set(pages.filter((p) => p.hidden).map((p) => p.key));
  const drawn = new Map<string, RailPicture>();
  for (const page of pages) {
    const picture = loadedPictures.get(page.key);
    if (
      picture &&
      visible.has(page.key) &&
      !hiddenKeys.has(page.key) &&
      drawn.size < DRAWN_MAX
    ) {
      drawn.set(page.key, picture);
    }
  }
  // The first few of those are live designers (the page being worked on first); only an editor
  // gets them, a reader keeps pictures.
  const liveKeys = new Set<string>();
  if (detail?.can_edit) {
    const order = [...drawn.keys()];
    if (selection && drawn.has(selection.pageKey))
      liveKeys.add(selection.pageKey);
    for (const key of order) {
      if (liveKeys.size >= LIVE_MAX) break;
      liveKeys.add(key);
    }
  }
  const railPictureOf = React.useCallback(
    (key: string) => loadedPictures.get(key) ?? null,
    // loadedPictures is rebuilt each render from `previews`; the callback follows it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [previews],
  );

  // ---- current page (page N of M) -----------------------------------------------------------

  const frame = React.useRef(0);
  // A page picked in the rail (or by the pager) stays the current page through the scroll that
  // brings it in, even when it cannot reach the top (the last page). The user's own scrolling
  // (wheel, touch, keys, the scrollbar) hands the counter back to the scroll position.
  const pinned = React.useRef<string | null>(null);
  // A zoom moves every page: the counter follows the position again.
  const zoomTo = (next: number | null) => {
    pinned.current = null;
    setZoom(next);
  };
  React.useEffect(() => {
    const node = scroller.current;
    if (!node) return;
    const unpin = () => {
      pinned.current = null;
    };
    const kinds = ['wheel', 'touchstart', 'keydown', 'pointerdown'] as const;
    for (const kind of kinds)
      node.addEventListener(kind, unpin, { passive: true });
    return () => {
      for (const kind of kinds) node.removeEventListener(kind, unpin);
    };
  }, [loaded, blocked]);
  const updateCurrent = React.useCallback(() => {
    const node = scroller.current;
    if (!node || pinned.current) return;
    const line = node.scrollTop + node.clientHeight / 3;
    let found: string | null = null;
    node.querySelectorAll<HTMLElement>('[data-page-wrap]').forEach((el) => {
      if (el.offsetTop <= line) found = el.getAttribute('data-page-wrap');
    });
    setCurrentKey((prev) => (prev === found ? prev : found));
  }, []);
  const onScroll = () => {
    if (frame.current) return;
    frame.current = requestAnimationFrame(() => {
      frame.current = 0;
      updateCurrent();
    });
  };
  React.useEffect(
    () => () => {
      if (frame.current) cancelAnimationFrame(frame.current);
    },
    [],
  );

  const activeKey = currentKey ?? pages[0]?.key ?? null;

  // Only the page being read gets medium pictures, and only once it has stayed current for a
  // moment: a fast scroll asks for nothing, the strip and the other pages keep their thumbnails.
  const [settledKey, setSettledKey] = React.useState<string | null>(null);
  React.useEffect(() => {
    if (!activeKey) return;
    const timer = setTimeout(() => setSettledKey(activeKey), SETTLE_MS);
    return () => clearTimeout(timer);
  }, [activeKey]);
  const sharp = useSpecSheetPageImages(
    projectId,
    documentId,
    sheetId,
    settledKey,
  );
  const sharpData = sharp.data ?? null;
  const scrollTo = (key: string) => {
    scrollStackTo(scroller.current, key);
    pinned.current = key;
    setCurrentKey(key);
  };
  const step = (delta: number) => {
    const at = pages.findIndex((p) => p.key === activeKey);
    const target = pages[Math.min(pages.length - 1, Math.max(0, at + delta))];
    if (target) scrollTo(target.key);
  };

  // An old Edit page link opens the reader at that page.
  const wantedPage = searchParams?.get('page') ?? null;
  const openedPage = React.useRef<string | null>(null);
  const scrolledReady = pages.length > 0 && !blocked;
  React.useEffect(() => {
    if (!wantedPage || !scrolledReady || openedPage.current === wantedPage)
      return;
    if (!pages.some((p) => p.key === wantedPage)) return;
    openedPage.current = wantedPage;
    // After the stack has laid out its placeholders.
    const timer = setTimeout(() => scrollTo(wantedPage), 0);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wantedPage, scrolledReady]);

  // The selected layer of the page being edited, and that page's layers (for the Inspector).
  const selectedLayers: TagLayer[] = selection
    ? (editing.draftOf(selection.pageKey) ??
      (loadedPictures.get(selection.pageKey)?.payload.doc?.sheets[
        loadedPictures.get(selection.pageKey)?.index ?? 0
      ]?.tags[0]?.layers as TagLayer[] | undefined) ??
      [])
    : [];
  const selectedLayer = selection
    ? (selectedLayers.find((l) => l.id === selection.layerId) ?? null)
    : null;
  const targetKey = selection?.pageKey ?? editing.lastKey() ?? null;

  // The page an apply started from while it runs: every OTHER page is read-only for that round
  // trip, since an edit made there now would be saved over the change the server is applying.
  const [applyingFrom, setApplyingFrom] = React.useState<string | null | false>(
    false,
  );
  const runApplyAll = React.useCallback(
    (layerId: string, changes: ApplyAllChanges, keep: string | null) => {
      setApplyingFrom(keep);
      void (async () => {
        // Every page's pending edit goes first, and no save lands in the middle of the apply.
        const release = await editing.settle();
        try {
          await applyAll.mutateAsync({
            sheetId,
            layerId,
            changes,
            originPageKey: keep ?? undefined,
          });
          // The server changed the other pages: their local copies are stale, start them over.
          editing.forgetOthers(keep);
          setRestarts((prev) => {
            const next = { ...prev };
            for (const page of pagesRef.current)
              if (page.key !== keep) next[page.key] = (prev[page.key] ?? 0) + 1;
            return next;
          });
        } catch {
          // The mutation reports its own error.
        } finally {
          release();
          setApplyingFrom(false);
        }
      })();
    },
    [applyAll, sheetId, editing],
  );
  // "Every page" changes are gathered while the user is still typing or clicking (a font size
  // typed as "24" is one apply, not two) and sent once they pause.
  const queuedApply = React.useRef<{
    layerId: string;
    keep: string | null;
    changes: ApplyAllChanges;
    timer: ReturnType<typeof setTimeout>;
  } | null>(null);
  // The latest `runApplyAll` (it changes every render), so the flush and its unmount cleanup
  // stay stable and a gathered change is not sent early by a re-render.
  const runApplyAllRef = React.useRef(runApplyAll);
  runApplyAllRef.current = runApplyAll;
  const flushApply = React.useCallback(() => {
    const queued = queuedApply.current;
    if (!queued) return;
    clearTimeout(queued.timer);
    queuedApply.current = null;
    runApplyAllRef.current(queued.layerId, queued.changes, queued.keep);
  }, []);
  const sendToEveryPage = React.useCallback(
    (layerId: string, changes: ApplyAllChanges) => {
      const keep = selection?.pageKey ?? null;
      const queued = queuedApply.current;
      if (queued && (queued.layerId !== layerId || queued.keep !== keep))
        flushApply();
      const prev = queuedApply.current?.changes;
      if (queuedApply.current) clearTimeout(queuedApply.current.timer);
      const merged: ApplyAllChanges = { ...prev, ...changes };
      if (prev?.props || changes.props)
        merged.props = { ...prev?.props, ...changes.props };
      queuedApply.current = {
        layerId,
        keep,
        changes: merged,
        timer: setTimeout(flushApply, APPLY_ALL_MS),
      };
    },
    [selection, flushApply],
  );
  // In Every-page mode a change made ON the canvas (a drag, a resize, a turn) of the selected layer
  // goes to every page too, the same as typing it in the Inspector.
  const everyPageRef = React.useRef({ selection, applyMode, sendToEveryPage });
  everyPageRef.current = { selection, applyMode, sendToEveryPage };
  const onLayersReport = React.useCallback(
    (key: string, base: TagLayer[], layers: TagLayer[]) => {
      const { selection: sel, applyMode: mode, sendToEveryPage: send } =
        everyPageRef.current;
      if (mode === 'all' && sel && sel.pageKey === key) {
        const before = (editing.draftOf(key) ?? base).find(
          (l) => l.id === sel.layerId,
        );
        const after = layers.find((l) => l.id === sel.layerId);
        const sent = applicableChanges(movedKeys(before, after), null);
        if (sent) send(sel.layerId, sent);
      }
      report(key, base, layers);
    },
    // `draftOf` reads a ref; `report` is stable.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [report],
  );
  // Leaving the reader sends what was gathered.
  React.useEffect(() => () => flushApply(), [flushApply]);
  const changeSelectedProps = (id: string, changes: Partial<TagLayerProps>) => {
    if (!selection) return;
    controllerRefFor(selection.pageKey).current?.updateLayerProps(id, changes);
    if (applyMode === 'all') {
      const sent = applicableChanges(null, changes);
      if (sent) sendToEveryPage(id, sent);
    }
  };

  // ---- header actions -----------------------------------------------------------------------

  const deletion = useDeferredAction({
    actionKey: 'quotation_spec_sheet.delete',
    entityType: 'quotation_spec_sheet',
    entityId: sheetId,
    verb: 'Deleting',
    subject: detail?.label ?? 'spec sheet',
    surface: 'inline',
    successMessage: 'Spec sheet deleted',
    invalidateKeys: [specSheetListKey(documentId)],
    onCommitted: () => router.push(listHref),
  });

  if (detailQuery.isLoading) {
    return (
      <div className="flex flex-col gap-3" data-testid="spec-sheet-loading">
        <Skeleton className="h-16 w-full" />
        <Skeleton className="aspect-video w-full" />
      </div>
    );
  }
  if (detailQuery.error || !detail) {
    return (
      <div className="rounded-lg border border-border px-4 py-10 text-center">
        <h3 className="text-sm font-semibold text-foreground">
          The spec sheet could not load
        </h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {detailQuery.error instanceof Error
            ? detailQuery.error.message
            : 'Try again in a moment.'}
        </p>
      </div>
    );
  }

  const canEdit = detail.can_edit;
  const templateLabelOf = (page: SpecSheetPage) =>
    page.template === 'cover'
      ? (detail.templates.cover?.name ?? '')
      : page.template === 'single'
        ? (detail.templates.single?.name ?? detail.templates.page?.name ?? '')
        : (detail.templates.page?.name ?? '');

  const menu: RecordAction[] = canEdit
    ? [
        {
          key: 'quotation_spec_sheet.delete',
          label: 'Delete',
          icon: Trash2,
          kind: 'destructive',
          disabled: deletion.isPending,
          run: () => deletion.start(),
        },
      ]
    : [];

  const activeNumber = activeKey ? numbers.get(activeKey) : undefined;
  // Outside full screen the app chrome and the page header sit above the editor; in full screen
  // only the overlay's padding and the toolbar do. The side panels lose their title row too.
  const stackHeight = focus
    ? 'max-h-[calc(100dvh-5.5rem)]'
    : 'max-h-[calc(100dvh-16rem)]';
  const panelHeight = focus
    ? 'max-h-[calc(100dvh-7.5rem)]'
    : 'max-h-[calc(100dvh-18rem)]';

  return (
    <div
      className="flex min-w-0 flex-col gap-3"
      data-testid="spec-sheet-reader"
    >
      <PageHeader
        title={`${detail.label} \u00b7 ${detail.source_label}`}
        crumbs={projectCrumbs(
          projectId,
          { tab: 'quotations' },
          { title: 'Spec sheets', path: listHref },
          { title: detail.label },
        )}
        titleClassName="truncate"
        actions={
          <BackToList
            listPath={listHref}
            label="Back to spec sheets"
            appendListState={false}
          />
        }
      />
      {/* The system's detail-page group (DetailActions): pager, gear, then the one primary. */}
      <div className="flex flex-wrap items-center justify-end gap-2">
        {canEdit && !blocked && (
          // The sheet's cover / page / single item templates, picked again: the same dialog the
          // sheet is created with, in its re-pick mode. Rows and page edits stay.
          <Button size="sm" variant="outline" onClick={() => setPicking(true)}>
            Templates
          </Button>
        )}
        {canEdit && detail.newer_templates && (
          <Button
            size="sm"
            variant="outline"
            disabled={update.isPending}
            onClick={() =>
              update.mutate({
                sheetId,
                body: { use_latest_templates: true },
              })
            }
          >
            Use latest templates
          </Button>
        )}
        <DetailActions
          pagerNode={
            <RecordNavigation
              index={null}
              total={0}
              hasPrevious={detail.prev_id !== null}
              hasNext={detail.next_id !== null}
              onPrevious={() =>
                detail.prev_id && router.push(sheetHref(detail.prev_id))
              }
              onNext={() =>
                detail.next_id && router.push(sheetHref(detail.next_id))
              }
              ariaLabel="spec sheet"
            />
          }
          actions={menu}
          gearLabel="Spec sheet actions"
          pendingAction={deletion.countdown}
          primary={
            blocked ? (
              canEdit && (
                <Button size="sm" onClick={() => setPicking(true)}>
                  Pick templates
                </Button>
              )
            ) : (
              <Button
                size="sm"
                disabled={exportPdf.isPending}
                onClick={() => exportPdf.mutate(sheetId)}
              >
                <FileDown className="size-4" aria-hidden />
                Export PDF
              </Button>
            )
          }
        />
      </div>

      {blocked ? (
        <div
          className="rounded-lg border border-border px-4 py-10 text-center"
          data-testid="spec-sheet-templates-missing"
        >
          <h3 className="text-sm font-semibold text-foreground">
            {`The ${blockedBy.join(' and ')} template${blockedBy.length > 1 ? 's' : ''} of this spec sheet ${
              blockedBy.length > 1 ? 'were' : 'was'
            } deleted.`}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {canEdit
              ? 'Pick new templates to show and export it.'
              : 'Someone who can edit this quotation can pick new templates.'}
          </p>
        </div>
      ) : (
        // keepMounted: toggling full screen must not remount the live canvases (their selection,
        // undo and any edit on its way stay put).
        <FocusShell active={focus} onExit={exitFocus} keepMounted>
          <div className="flex shrink-0 flex-wrap items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
            <Button
              size="icon"
              variant="outline"
              aria-label="Previous page"
              onClick={() => step(-1)}
            >
              <ChevronUp className="size-4" />
            </Button>
            <Button
              size="icon"
              variant="outline"
              aria-label="Next page"
              onClick={() => step(1)}
            >
              <ChevronDown className="size-4" />
            </Button>
            <span
              className="text-sm tabular-nums"
              data-testid="spec-sheet-page-of"
            >
              <b>{activeNumber ?? '-'}</b> of {printedCount}
            </span>
            <span className="mx-1 h-5 w-px bg-border" aria-hidden />
            <Button
              size="icon"
              variant="outline"
              aria-label="Zoom out"
              onClick={() => zoomTo(clampZoom(scale / ZOOM_STEP))}
            >
              <Minus className="size-4" />
            </Button>
            <span className="min-w-[3rem] text-center text-sm tabular-nums">
              {Math.round(scale * 100)}%
            </span>
            <Button
              size="icon"
              variant="outline"
              aria-label="Zoom in"
              onClick={() => zoomTo(clampZoom(scale * ZOOM_STEP))}
            >
              <Plus className="size-4" />
            </Button>
            <Button size="sm" variant="outline" onClick={() => zoomTo(null)}>
              Fit width
            </Button>
            <FocusToggle
              active={focus}
              onToggle={setFocus}
              label="spec sheet"
            />
            {canEdit && (
              <>
                <span className="mx-1 h-5 w-px bg-border" aria-hidden />
                <Button
                  size="icon"
                  variant="outline"
                  aria-label="Undo"
                  disabled={!editing.canUndo(targetKey)}
                  onClick={() => targetKey && editing.undo(targetKey)}
                >
                  <Undo2 className="size-4" />
                </Button>
                <Button
                  size="icon"
                  variant="outline"
                  aria-label="Redo"
                  disabled={!editing.canRedo(targetKey)}
                  onClick={() => targetKey && editing.redo(targetKey)}
                >
                  <Redo2 className="size-4" />
                </Button>
                {/* Always the same bar (hidden unless a text layer is picked): the toolbar keeps
                    one height whatever is selected, so the pages never slide under the pointer. */}
                <FormatBar
                  layer={selectedLayer}
                  onProps={changeSelectedProps}
                />
                <span
                  // Fixed width, one line: "Saving..." is wider than "Saved", and a toolbar that
                  // rewraps on every autosave moves every page down and back.
                  className="ms-auto w-14 shrink-0 whitespace-nowrap text-end text-xs text-muted-foreground"
                  aria-live="polite"
                  data-testid="spec-sheet-save-state"
                >
                  {editing.status === 'saving'
                    ? 'Saving...'
                    : editing.status === 'saved'
                      ? 'Saved'
                      : editing.status === 'error'
                        ? 'Not saved'
                        : ''}
                </span>
              </>
            )}
          </div>

          {isMobile && (
            <PageRail
              pages={pages}
              numbers={numbers}
              currentKey={activeKey}
              canEdit={canEdit}
              strip
              pageMm={detail.page_size}
              pictureOf={railPictureOf}
              onSelect={scrollTo}
              onReorder={(items) =>
                commit([...pages.filter((p) => p.key === COVER), ...items])
              }
              onVisibleChange={setRailVisible}
            />
          )}
          <div className="relative flex min-w-0 gap-3">
            {!isMobile && (
              <CollapsiblePanel
                title="Pages"
                side="start"
                collapsed={railCollapsed}
                onToggle={(next) => {
                  setRailCollapsed(next);
                  // A folded rail has nothing in view: stop loading chunks for it.
                  if (next) setRailVisible(new Set());
                }}
              >
                <PageRail
                  pages={pages}
                  numbers={numbers}
                  currentKey={activeKey}
                  canEdit={canEdit}
                  strip={false}
                  pageMm={detail.page_size}
                  pictureOf={railPictureOf}
                  onSelect={scrollTo}
                  onReorder={(items) =>
                    commit([...pages.filter((p) => p.key === COVER), ...items])
                  }
                  onVisibleChange={setRailVisible}
                  className={panelHeight}
                />
              </CollapsiblePanel>
            )}
            <div
              ref={scroller}
              onScroll={onScroll}
              className={cn(
                'relative min-h-[20rem] min-w-0 flex-1 overflow-auto overscroll-contain rounded-lg bg-muted',
                stackHeight,
              )}
              data-testid="spec-sheet-stack"
            >
              <div
                className="flex min-w-fit flex-col items-center gap-6 py-4"
                style={{ paddingLeft: STACK_PAD, paddingRight: STACK_PAD }}
              >
                {pages.map((page) => (
                  <ReaderPage
                    key={page.key}
                    page={page}
                    number={numbers.get(page.key) ?? null}
                    templateLabel={templateLabelOf(page)}
                    boxWidth={boxWidth}
                    boxHeight={boxHeight}
                    scale={scale}
                    pageMm={detail.page_size}
                    payload={drawn.get(page.key)?.payload ?? null}
                    sheetIndex={drawn.get(page.key)?.index}
                    live={liveKeys.has(page.key)}
                    epoch={restarts[page.key] ?? 0}
                    selectedLayerId={
                      selection?.pageKey === page.key ? selection.layerId : null
                    }
                    draftLayers={editing.draftOf(page.key)}
                    externalLayers={editing.externalOf(page.key)}
                    current={page.key === activeKey}
                    sharp={page.key === settledKey ? sharpData : null}
                    canEdit={
                      canEdit &&
                      (applyingFrom === false || applyingFrom === page.key)
                    }
                    pages={pages}
                    documentId={documentId}
                    sheetId={sheetId}
                    onPatch={patch}
                    onSelectLayer={onSelectLayer}
                    onLayersReport={onLayersReport}
                    controllerRefFor={controllerRefFor}
                  />
                ))}
              </div>
            </div>
            {canEdit && !isMobile && (
              <div className="hidden shrink-0 lg:block">
                <CollapsiblePanel
                  title="Inspector"
                  side="end"
                  collapsed={inspectorCollapsed}
                  onToggle={setInspectorCollapsed}
                >
                  <aside
                    className={cn(
                      'flex min-h-[20rem] w-72 shrink-0 flex-col overflow-hidden rounded-lg border border-border bg-background',
                      panelHeight,
                    )}
                  >
                    {selectedLayer ? (
                      <ReaderInspector
                        pageKey={selection?.pageKey ?? null}
                        layer={selectedLayer}
                        layers={selectedLayers}
                        controller={
                          selection
                            ? controllerRefFor(selection.pageKey).current
                            : null
                        }
                        mode={applyMode}
                        onModeChange={setApplyMode}
                        onApplyAll={sendToEveryPage}
                      />
                    ) : (
                      <div
                        className="p-4 text-sm text-muted-foreground"
                        data-testid="reader-inspector-empty"
                      >
                        Nothing selected
                      </div>
                    )}
                  </aside>
                </CollapsiblePanel>
              </div>
            )}
          </div>
          {canEdit && isMobile && (
            <Drawer
              modal={false}
              open={sheetOpen && Boolean(selectedLayer)}
              onOpenChange={(open) => !open && setSheetOpen(false)}
            >
              <DrawerContent className="data-[vaul-drawer-direction=bottom]:max-h-[45dvh]">
                <DrawerHeader className="sr-only">
                  <DrawerTitle>Selected layer</DrawerTitle>
                  <DrawerDescription>
                    Change the selected layer
                  </DrawerDescription>
                </DrawerHeader>
                {selectedLayer && (
                  <div className="min-h-0 overflow-y-auto">
                    <ReaderInspector
                      pageKey={selection?.pageKey ?? null}
                      layer={selectedLayer}
                      layers={selectedLayers}
                      controller={
                        selection
                          ? controllerRefFor(selection.pageKey).current
                          : null
                      }
                      mode={applyMode}
                      onModeChange={setApplyMode}
                      onApplyAll={sendToEveryPage}
                    />
                  </div>
                )}
              </DrawerContent>
            </Drawer>
          )}
          {canEdit && isMobile && selectedLayer && !sheetOpen && (
            <Button
              className="fixed inset-x-0 bottom-[calc(1rem+env(safe-area-inset-bottom))] z-40 mx-auto w-fit shadow-lg"
              onClick={openSheet}
            >
              Properties
            </Button>
          )}
        </FocusShell>
      )}
      {canEdit && picking && (
        <CreateSpecSheetDialog
          open={picking}
          onOpenChange={setPicking}
          projectId={projectId}
          documentId={documentId}
          sheet={{
            id: sheetId,
            cover: detail.templates.cover?.id ?? null,
            page: detail.templates.page?.id ?? null,
            single: detail.templates.single?.id ?? null,
          }}
        />
      )}
    </div>
  );
}
