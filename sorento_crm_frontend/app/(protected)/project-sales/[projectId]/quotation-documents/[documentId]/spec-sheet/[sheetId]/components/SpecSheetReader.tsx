'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import {
  ChevronDown,
  ChevronUp,
  FileDown,
  Minus,
  Plus,
  Trash2,
} from 'lucide-react';

import { Button } from '@/components/ui/button';
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
  specSheetListKey,
  useSpecSheetDetail,
  useSpecSheetMutations,
  useSpecSheetPageImages,
  useSpecSheetPreviews,
} from '../../../../../../_shared/hooks/useSpecSheet';
import type {
  SpecSheetPage,
  SpecSheetRow,
} from '../../../../../../_shared/services/specSheetService';
import { CreateSpecSheetDialog } from '../../../components/CreateSpecSheetDialog';
import { PageRail } from './PageRail';
import { COVER, ReaderPage } from './ReaderPage';

/** Pages per preview call. The window snaps to these chunks, so a scroll that stays inside one
 *  costs nothing and a scroll back is a cache hit. Well under the server's 12-key limit. */
const CHUNK_SIZE = 6;
/** The most pages drawn at once, however far the viewport is zoomed out. */
const DRAWN_MAX = 12;
/** The window starts one viewport above and below what is on screen. */
const WINDOW_MARGIN = '100% 0px';
/** The page being read must stay put this long before its sharper pictures are asked for. */
const SETTLE_MS = 250;
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
  const [railOpen, setRailOpen] = React.useState(false);
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
    () => chunks.filter((keys) => keys.some((k) => visible.has(k))),
    [chunks, visible],
  );
  const previews = useSpecSheetPreviews(
    projectId,
    documentId,
    sheetId,
    windowChunks,
  );

  // key -> the payload that holds its sheet, for the pages that are near AND already fetched.
  // One payload object per fetched answer, so a page's props stay the same between renders.
  const payloads = React.useRef(new WeakMap<object, TagSheetDesignPayload>());
  const drawn = (() => {
    const map = new Map<
      string,
      { payload: TagSheetDesignPayload; index: number }
    >();
    const hidden = new Set(pages.filter((p) => p.hidden).map((p) => p.key));
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
        if (
          key &&
          visible.has(key) &&
          !hidden.has(key) &&
          map.size < DRAWN_MAX
        ) {
          map.set(key, { payload: shared, index });
        }
      });
    }
    return map;
  })();

  // ---- current page (page N of M) -----------------------------------------------------------

  const frame = React.useRef(0);
  const updateCurrent = React.useCallback(() => {
    const node = scroller.current;
    if (!node) return;
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
  const sharpBase = settledKey
    ? (drawn.get(settledKey)?.payload ?? null)
    : null;
  const sharpData = sharp.data;
  const sharpPayload = React.useMemo(
    () =>
      sharpBase && sharpData
        ? {
            ...sharpBase,
            images: { ...sharpBase.images, ...sharpData.images },
            assets: { ...sharpBase.assets, ...sharpData.assets },
          }
        : null,
    [sharpBase, sharpData],
  );
  const scrollTo = (key: string) => {
    const el = Array.from(
      scroller.current?.querySelectorAll<HTMLElement>('[data-page-wrap]') ?? [],
    ).find((node) => node.getAttribute('data-page-wrap') === key);
    el?.scrollIntoView?.({ block: 'start' });
    setCurrentKey(key);
    setRailOpen(false);
  };
  const step = (delta: number) => {
    const at = pages.findIndex((p) => p.key === activeKey);
    const target = pages[Math.min(pages.length - 1, Math.max(0, at + delta))];
    if (target) scrollTo(target.key);
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
        <>
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
            {isMobile && (
              <Button
                size="sm"
                variant="outline"
                onClick={() => setRailOpen((open) => !open)}
              >
                Pages
              </Button>
            )}
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
              onClick={() => setZoom(clampZoom(scale / ZOOM_STEP))}
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
              onClick={() => setZoom(clampZoom(scale * ZOOM_STEP))}
            >
              <Plus className="size-4" />
            </Button>
            <Button size="sm" variant="outline" onClick={() => setZoom(null)}>
              Fit width
            </Button>
          </div>

          <div className="relative flex min-w-0 gap-3">
            {(!isMobile || railOpen) && (
              <aside
                className={`max-h-[calc(100dvh-16rem)] min-h-[20rem] shrink-0 overflow-y-auto ${
                  isMobile
                    ? 'absolute z-20 w-56 rounded-lg border border-border bg-background p-2 shadow-lg'
                    : 'w-56'
                }`}
              >
                <PageRail
                  pages={pages}
                  numbers={numbers}
                  currentKey={activeKey}
                  canEdit={canEdit}
                  onSelect={scrollTo}
                  onReorder={(items) =>
                    commit([...pages.filter((p) => p.key === COVER), ...items])
                  }
                />
              </aside>
            )}
            <div
              ref={scroller}
              onScroll={onScroll}
              className="relative max-h-[calc(100dvh-16rem)] min-h-[20rem] min-w-0 flex-1 overflow-auto rounded-lg bg-muted"
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
                    payload={
                      page.key === settledKey && sharpPayload
                        ? sharpPayload
                        : (drawn.get(page.key)?.payload ?? null)
                    }
                    sheetIndex={drawn.get(page.key)?.index}
                    canEdit={canEdit}
                    editDisabledReason={
                      isMobile
                        ? 'Open this on a desktop screen to edit a page.'
                        : undefined
                    }
                    editHref={`${sheetHref(sheetId)}/pages/${encodeURIComponent(page.key)}/edit`}
                    pages={pages}
                    documentId={documentId}
                    sheetId={sheetId}
                    onPatch={patch}
                  />
                ))}
              </div>
            </div>
          </div>
        </>
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
