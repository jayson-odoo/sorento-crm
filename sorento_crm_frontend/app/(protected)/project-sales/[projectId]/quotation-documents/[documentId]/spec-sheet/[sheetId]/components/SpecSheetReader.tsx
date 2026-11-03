'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  ChevronDown,
  ChevronUp,
  FileDown,
  Minus,
  Plus,
  Trash2,
} from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import RecordNavigation from '@/components/common/RecordNavigation';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
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
  useSpecSheetPreview,
} from '../../../../../../_shared/hooks/useSpecSheet';
import type {
  SpecSheetPage,
  SpecSheetRow,
} from '../../../../../../_shared/services/specSheetService';
import { PageRail } from './PageRail';
import { COVER, ReaderPage } from './ReaderPage';

/** The most pages one preview call may ask for (the server refuses more). */
const WINDOW_MAX = 12;
/** The window starts one viewport above and below what is on screen. */
const WINDOW_MARGIN = '100% 0px';
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

  const listHref = `/project-sales/${projectId}/quotation-documents/${documentId}/spec-sheet`;
  const sheetHref = (id: string) => `${listHref}/${id}`;

  // Local copy of the pages while a write is in flight, so a drag or a toggle lands at once.
  const [override, setOverride] = React.useState<SpecSheetPage[] | null>(null);
  const detailPages = detail?.pages;
  const pages = React.useMemo(() => override ?? detailPages ?? [], [override, detailPages]);

  // Page numbers count printed pages only; the cover is page 1.
  const numbers = React.useMemo(() => {
    const map = new Map<string, number>();
    let printed = 0;
    for (const page of pages) if (page.key === COVER || !page.hidden) map.set(page.key, ++printed);
    return map;
  }, [pages]);
  const printedCount = numbers.size;

  const commit = (next: SpecSheetPage[]) => {
    setOverride(next);
    update.mutate(
      { sheetId, body: { rows: next.filter((p) => p.key !== COVER).map(rowOf) } },
      { onSettled: () => setOverride(null) },
    );
  };
  const patch = (key: string, change: Partial<SpecSheetPage>) =>
    commit(pages.map((page) => (page.key === key ? { ...page, ...change } : page)));

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
  }, [loaded]);

  const naturalW = (detail?.page_size.width_mm ?? 0) * PX_PER_MM;
  const naturalH = (detail?.page_size.height_mm ?? 0) * PX_PER_MM;
  const fitScale =
    naturalW > 0 && width > 0 ? Math.max(0.1, (width - STACK_PAD * 2) / naturalW) : FALLBACK_SCALE;
  const scale = zoom ?? fitScale;
  const boxWidth = Math.round(naturalW * scale);
  const boxHeight = Math.round(naturalH * scale);

  const [windowKeys, setWindowKeys] = React.useState<string[]>([]);
  const visibleRef = React.useRef<Set<string>>(new Set());
  const pagesRef = React.useRef<SpecSheetPage[]>(pages);
  pagesRef.current = pages;

  const recomputeWindow = React.useCallback(() => {
    // Page order, left-out pages never drawn, never more than the preview accepts.
    const next = pagesRef.current
      .filter((p) => !p.hidden && visibleRef.current.has(p.key))
      .map((p) => p.key)
      .slice(0, WINDOW_MAX);
    setWindowKeys((prev) =>
      prev.length === next.length && prev.every((k, i) => k === next[i]) ? prev : next,
    );
  }, []);

  const pageKeys = pages.map((p) => p.key).join('|');
  React.useEffect(() => {
    const root = scroller.current;
    if (!root || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver(
      (entries) => {
        const next = new Set(visibleRef.current);
        for (const entry of entries) {
          const key = entry.target.getAttribute('data-page-key');
          if (!key) continue;
          if (entry.isIntersecting) next.add(key);
          else next.delete(key);
        }
        visibleRef.current = next;
        recomputeWindow();
      },
      { root, rootMargin: WINDOW_MARGIN },
    );
    root.querySelectorAll('[data-page-key]').forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, [pageKeys, recomputeWindow]);

  // A page left out (or put back) changes what the window may draw without any scrolling.
  React.useEffect(() => {
    recomputeWindow();
  }, [pages, recomputeWindow]);

  const preview = useSpecSheetPreview(projectId, documentId, sheetId, windowKeys, windowKeys.length > 0);
  const payload = React.useMemo(
    () =>
      preview.data
        ? ({ ...preview.data, page_id: '', source: 'version' } as TagSheetDesignPayload)
        : null,
    [preview.data],
  );
  const sheetIndex = React.useMemo(() => {
    const map = new Map<string, number>();
    (preview.data?.doc?.sheets ?? []).forEach((sheet, index) => {
      const key = sheet.tags[0]?.request_tag_id;
      if (key) map.set(key, index);
    });
    return map;
  }, [preview.data]);
  const inWindow = React.useMemo(() => new Set(windowKeys), [windowKeys]);

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
        <h3 className="text-sm font-semibold text-foreground">The spec sheet could not load</h3>
        <p className="mt-1 text-sm text-muted-foreground">
          {detailQuery.error instanceof Error ? detailQuery.error.message : 'Try again in a moment.'}
        </p>
      </div>
    );
  }

  const canEdit = detail.can_edit;
  const versions = [detail.templates.cover, detail.templates.page, detail.templates.single]
    .filter((t): t is NonNullable<typeof t> => t !== null)
    .map((t) => `${t.name} v${t.version_no}`)
    .join(' / ');
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
    <div className="flex min-w-0 flex-col gap-3" data-testid="spec-sheet-reader">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border bg-background px-4 py-3">
        <div className="min-w-0">
          <Button variant="ghost" size="sm" asChild className="-ms-2 mb-1">
            <Link href={listHref}>
              <ArrowLeft className="size-4" aria-hidden />
              Spec sheets
            </Link>
          </Button>
          <h1 className="truncate text-lg font-semibold" title={`${detail.label} ${detail.source_label}`}>
            {detail.label} &middot; {detail.source_label}
          </h1>
          <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span className="truncate" title={versions}>
              {versions} &middot; {printedCount} pages
            </span>
            {detail.source_hint && <span>{detail.source_hint}</span>}
            {detail.newer_templates && (
              <Badge variant="warning" appearance="light" size="sm">
                newer template published
              </Badge>
            )}
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canEdit && detail.newer_templates && (
            <Button
              size="sm"
              variant="outline"
              disabled={update.isPending}
              onClick={() => update.mutate({ sheetId, body: { use_latest_templates: true } })}
            >
              Use latest templates
            </Button>
          )}
          <RecordNavigation
            index={null}
            total={0}
            hasPrevious={detail.prev_id !== null}
            hasNext={detail.next_id !== null}
            onPrevious={() => detail.prev_id && router.push(sheetHref(detail.prev_id))}
            onNext={() => detail.next_id && router.push(sheetHref(detail.next_id))}
            ariaLabel="spec sheet"
          />
          {deletion.countdown ?? (
            <Button size="sm" disabled={exportPdf.isPending} onClick={() => exportPdf.mutate(sheetId)}>
              <FileDown className="size-4" aria-hidden />
              Export PDF
            </Button>
          )}
          {menu.length > 0 && !deletion.countdown && (
            <DetailActionsMenu actions={menu} trigger="ellipsis" ariaLabel="spec sheet actions" />
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-background px-3 py-2">
        {isMobile && (
          <Button size="sm" variant="outline" onClick={() => setRailOpen((open) => !open)}>
            Pages
          </Button>
        )}
        <Button size="icon" variant="outline" aria-label="Previous page" onClick={() => step(-1)}>
          <ChevronUp className="size-4" />
        </Button>
        <Button size="icon" variant="outline" aria-label="Next page" onClick={() => step(1)}>
          <ChevronDown className="size-4" />
        </Button>
        <span className="text-sm tabular-nums" data-testid="spec-sheet-page-of">
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
        <span className="min-w-[3rem] text-center text-sm tabular-nums">{Math.round(scale * 100)}%</span>
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
            className={`max-h-[calc(100vh-16rem)] min-h-[20rem] shrink-0 overflow-y-auto ${
              isMobile ? 'absolute z-20 w-56 rounded-lg border border-border bg-background p-2 shadow-lg' : 'w-56'
            }`}
          >
            <PageRail
              pages={pages}
              numbers={numbers}
              currentKey={activeKey}
              canEdit={canEdit}
              onSelect={scrollTo}
              onReorder={(items) => commit([...pages.filter((p) => p.key === COVER), ...items])}
            />
          </aside>
        )}
        <div
          ref={scroller}
          onScroll={onScroll}
          className="relative max-h-[calc(100vh-16rem)] min-h-[20rem] min-w-0 flex-1 overflow-auto rounded-lg bg-muted"
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
                payload={inWindow.has(page.key) ? payload : null}
                sheetIndex={inWindow.has(page.key) ? sheetIndex.get(page.key) : undefined}
                canEdit={canEdit}
                editDisabledReason={isMobile ? 'Open this on a desktop screen to edit a page.' : undefined}
                editHref={`${sheetHref(sheetId)}/pages/${encodeURIComponent(page.key)}/edit`}
                pages={pages}
                documentId={documentId}
                sheetId={sheetId}
                onPatch={(change) => patch(page.key, change)}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
