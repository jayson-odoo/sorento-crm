'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight, FileDown, GripVertical } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import ScaledSheet, { sheetPixelSize } from '@/components/dealer-kit/ScaledSheet';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';

import {
  useSpecSheet,
  useSpecSheetMutations,
  useSpecSheetPreview,
} from '../../../../_shared/hooks/useSpecSheet';
import type {
  SpecSheetPage,
  SpecSheetRow,
  SpecSheetView,
} from '../../../../_shared/services/specSheetService';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

/**
 * PS-SPEC-SHEET: the project spec sheet of this quotation - a cover plus one page per quoted
 * item, drawn by the Spec sheet templates designed in Dealer Kit > Tag Templates.
 *
 * Prints an ISSUED revision (the latest unless another is picked). The per-page Area, Comment,
 * Marker, Print switch, hand-picked accessories and page order save on their own (on blur, on
 * drop), keyed by item, so they carry over to the next revision.
 */
export function QuotationSpecSheetTab() {
  const { projectId, documentId, canEdit } = useQuotationDocumentScreen();
  const [issueId, setIssueId] = React.useState<string | null>(null);
  const view = useSpecSheet(projectId, documentId, issueId);
  const { save, exportPdf } = useSpecSheetMutations(projectId, documentId);

  if (view.isLoading) {
    return (
      <div className="flex flex-col gap-3" data-testid="spec-sheet-loading">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (view.error || !view.data) {
    return (
      <EmptyState
        title="The spec sheet could not load"
        hint={view.error instanceof Error ? view.error.message : 'Try again in a moment.'}
      />
    );
  }

  const data = view.data;
  const effectiveIssueId = issueId ?? data.issue_id;
  const settings = data.settings;
  const ready = Boolean(effectiveIssueId && settings.cover_template_id && settings.page_template_id);
  const exportReason = !effectiveIssueId
    ? 'Issue a revision first.'
    : !ready
      ? 'Pick a cover template and a page template first.'
      : undefined;

  return (
    <div className="flex min-w-0 flex-col gap-4" data-testid="spec-sheet-tab">
      <SpecSheetPickers
        view={data}
        issueId={effectiveIssueId}
        canEdit={canEdit}
        onIssue={(next) => {
          setIssueId(next);
          if (canEdit) save.mutate({ issue_id: next });
        }}
        onTemplates={(body) => save.mutate(body)}
        exportButton={
          // The reason sits on a wrapper: a disabled button receives no hover, so its own
          // title would never show.
          <span title={exportReason} data-testid="spec-sheet-export-reason" className="inline-flex">
            <Button
              size="sm"
              disabled={!ready || exportPdf.isPending}
              onClick={() => exportPdf.mutate(effectiveIssueId)}
              data-testid="spec-sheet-export"
            >
              <FileDown className="size-4" aria-hidden />
              Export PDF
            </Button>
          </span>
        }
      />

      {!effectiveIssueId ? (
        <EmptyState
          title="No issued revision yet"
          hint="Issue a revision first."
        />
      ) : data.templates.cover.length === 0 || data.templates.page.length === 0 ? (
        <EmptyState
          title="No spec sheet templates"
          hint="Publish a Spec sheet cover and a Spec sheet page template in Dealer Kit > Tag Templates."
        />
      ) : null}

      {effectiveIssueId && (
        <SpecSheetPages
          view={data}
          canEdit={canEdit}
          onRows={(rows) => save.mutate({ rows })}
        />
      )}

      {ready && (
        <SpecSheetPreviewPanel
          projectId={projectId}
          documentId={documentId}
          issueId={effectiveIssueId}
        />
      )}
    </div>
  );
}

function EmptyState({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="rounded-lg border border-border px-4 py-10 text-center">
      <h3 className="text-sm font-semibold text-foreground">{title}</h3>
      <p className="mt-1 text-sm text-muted-foreground">{hint}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------- pickers

function templateOptions(rows: { id: string; name: string; width_mm: number | null; height_mm: number | null }[]) {
  return rows.map((row) => ({
    value: row.id,
    label: row.width_mm && row.height_mm ? `${row.name} (${row.width_mm} x ${row.height_mm} mm)` : row.name,
  }));
}

function SpecSheetPickers({
  view,
  issueId,
  canEdit,
  onIssue,
  onTemplates,
  exportButton,
}: {
  view: SpecSheetView;
  issueId: string | null;
  canEdit: boolean;
  onIssue: (issueId: string | null) => void;
  onTemplates: (body: Partial<SpecSheetView['settings']>) => void;
  exportButton: React.ReactNode;
}) {
  const ids = {
    issue: React.useId(),
    cover: React.useId(),
    page: React.useId(),
    single: React.useId(),
  };
  const issueOptions: SearchableSelectOption[] = view.issues.map((issue) => ({
    value: issue.id,
    label: issue.label,
  }));
  const cover = templateOptions(view.templates.cover);
  const page = templateOptions(view.templates.page);
  const s = view.settings;
  return (
    <div className="flex min-w-0 flex-col gap-3 md:flex-row md:items-end">
      <div className="grid min-w-0 flex-1 grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.issue}>Revision</Label>
          <SearchableSelect
            id={ids.issue}
            value={issueId ?? ''}
            onChange={(v: string) => onIssue(v || null)}
            options={issueOptions}
            placeholder="No issued revision"
            disabled={issueOptions.length === 0}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.cover}>Cover template</Label>
          <SearchableSelect
            id={ids.cover}
            clearable
            value={s.cover_template_id ?? ''}
            onChange={(v: string) => onTemplates({ cover_template_id: v || null })}
            options={cover}
            placeholder="Pick a cover"
            disabled={!canEdit}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.page}>Page template</Label>
          <SearchableSelect
            id={ids.page}
            clearable
            value={s.page_template_id ?? ''}
            onChange={(v: string) => onTemplates({ page_template_id: v || null })}
            options={page}
            placeholder="Pick a page"
            disabled={!canEdit}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.single}>Single item template</Label>
          <SearchableSelect
            id={ids.single}
            clearable
            value={s.single_page_template_id ?? ''}
            onChange={(v: string) => onTemplates({ single_page_template_id: v || null })}
            options={page}
            placeholder="Same as page template"
            disabled={!canEdit}
          />
        </div>
      </div>
      <div className="shrink-0">{exportButton}</div>
    </div>
  );
}

// ---------------------------------------------------------------------------- pages

function rowOf(page: SpecSheetPage): SpecSheetRow {
  return {
    key: page.key,
    area: page.area,
    comment: page.comment,
    marker: page.marker,
    hidden: page.hidden,
    accessories: page.picked,
  };
}

function SpecSheetPages({
  view,
  canEdit,
  onRows,
}: {
  view: SpecSheetView;
  canEdit: boolean;
  onRows: (rows: SpecSheetRow[]) => void;
}) {
  const [pages, setPages] = React.useState<SpecSheetPage[]>(view.pages);
  React.useEffect(() => setPages(view.pages), [view.pages]);

  const commit = (next: SpecSheetPage[]) => {
    setPages(next);
    onRows(next.map(rowOf));
  };
  const patch = (key: string, change: Partial<SpecSheetPage>) =>
    commit(pages.map((page) => (page.key === key ? { ...page, ...change } : page)));

  const areas = React.useMemo(
    () => Array.from(new Set(pages.map((p) => p.area).filter(Boolean))).sort(),
    [pages],
  );

  if (pages.length === 0) {
    return (
      <EmptyState
        title="No items on this revision"
        hint="Add a product or product set line to the quotation."
      />
    );
  }

  let printed = 1; // the cover is page 1
  return (
    <div className="flex min-w-0 flex-col gap-2" data-testid="spec-sheet-pages">
      <Sortable
        value={pages}
        onValueChange={(next) => commit(next as SpecSheetPage[])}
        getItemValue={(page) => page.key}
        strategy="vertical"
      >
        <div className="flex flex-col gap-2">
          {pages.map((page) => {
            const number = page.hidden ? null : ++printed;
            return (
              <SortableItem key={page.key} value={page.key} disabled={!canEdit}>
                <SpecSheetPageRow
                  page={page}
                  number={number}
                  pages={pages}
                  areas={areas}
                  canEdit={canEdit}
                  onChange={(change) => patch(page.key, change)}
                />
              </SortableItem>
            );
          })}
        </div>
      </Sortable>
    </div>
  );
}

function SpecSheetPageRow({
  page,
  number,
  pages,
  areas,
  canEdit,
  onChange,
}: {
  page: SpecSheetPage;
  number: number | null;
  pages: SpecSheetPage[];
  areas: string[];
  canEdit: boolean;
  onChange: (change: Partial<SpecSheetPage>) => void;
}) {
  const ids = {
    area: React.useId(),
    comment: React.useId(),
    marker: React.useId(),
    acc: React.useId(),
    print: React.useId(),
  };
  const [comment, setComment] = React.useState(page.comment);
  const [marker, setMarker] = React.useState(page.marker);
  React.useEffect(() => setComment(page.comment), [page.comment]);
  React.useEffect(() => setMarker(page.marker), [page.marker]);

  const setParts = page.accessories.filter((a) => a.source === 'set');
  // Another page's item, or one this page already picked. An item that hosts its own picks
  // cannot be picked (one level only), and neither can one picked by another page.
  const pickable = [
    ...pages.filter((other) => other.key !== page.key && other.picked.length === 0),
    ...page.accessories.filter((a) => a.source === 'picked' && a.key),
  ];
  const accessoryOptions: SearchableSelectOption[] = pickable.map((item) => ({
    value: (item.key as string) ?? '',
    label: item.name ? `${item.code} ${item.name}` : item.code,
  }));
  const areaOptions: SearchableSelectOption[] = Array.from(
    new Set([...areas, page.area].filter(Boolean)),
  ).map((area) => ({ value: area, label: area }));

  return (
    <div
      className={`flex min-w-0 flex-col gap-3 rounded-lg border border-border bg-background p-3 lg:flex-row lg:items-start ${
        page.hidden ? 'opacity-60' : ''
      }`}
      data-testid={`spec-sheet-page-${page.code}`}
    >
      <div className="flex min-w-0 items-start gap-2 lg:w-64 lg:shrink-0">
        {canEdit && (
          <SortableItemHandle aria-label={`Drag ${page.code} to reorder`} className="mt-0.5">
            <GripVertical className="size-4 text-muted-foreground" />
          </SortableItemHandle>
        )}
        <span className="w-8 shrink-0 text-xs text-muted-foreground">
          {number != null ? `p. ${number}` : 'Off'}
        </span>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold" title={`${page.brand} ${page.code}`.trim()}>
            {page.code}
          </div>
          <div className="truncate text-xs text-muted-foreground" title={page.name}>
            {page.name}
          </div>
          {setParts.length > 0 && (
            <div
              className="mt-1 truncate text-xs text-muted-foreground"
              title={setParts.map((a) => a.code).join(', ')}
            >
              With {setParts.map((a) => a.code).join(', ')}
            </div>
          )}
        </div>
      </div>

      <div className="grid min-w-0 flex-1 grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-[2fr_2fr_2fr_1fr_auto]">
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.area} className="text-xs">
            Area
          </Label>
          <SearchableSelect
            id={ids.area}
            size="sm"
            clearable
            value={page.area}
            onChange={(v: string) => onChange({ area: v })}
            options={areaOptions}
            placeholder="Type an area"
            disabled={!canEdit}
            createOption={{
              label: (query) => (query ? `Use "${query.toUpperCase()}"` : null),
              onCreate: (query) => onChange({ area: query.trim().toUpperCase() }),
            }}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.acc} className="text-xs">
            Accessories
          </Label>
          <SearchableMultiSelect
            id={ids.acc}
            size="sm"
            value={page.picked}
            onChange={(v: string[]) => onChange({ picked: v })}
            options={accessoryOptions}
            placeholder={setParts.length ? 'Set parts only' : 'None'}
            disabled={!canEdit}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.comment} className="text-xs">
            Comment
          </Label>
          <Input
            id={ids.comment}
            value={comment}
            maxLength={500}
            disabled={!canEdit}
            onChange={(e) => setComment(e.target.value)}
            onBlur={() => comment !== page.comment && onChange({ comment })}
          />
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <Label htmlFor={ids.marker} className="text-xs">
            Marker
          </Label>
          <Input
            id={ids.marker}
            value={marker}
            maxLength={10}
            disabled={!canEdit}
            onChange={(e) => setMarker(e.target.value)}
            onBlur={() => marker !== page.marker && onChange({ marker })}
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label htmlFor={ids.print} className="text-xs">
            Print
          </Label>
          <Switch
            id={ids.print}
            checked={!page.hidden}
            disabled={!canEdit}
            onCheckedChange={(on: boolean) => onChange({ hidden: !on })}
            aria-label={`Print ${page.code}`}
          />
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------- preview

function SpecSheetPreviewPanel({
  projectId,
  documentId,
  issueId,
}: {
  projectId: string;
  documentId: string;
  issueId: string | null;
}) {
  const preview = useSpecSheetPreview(projectId, documentId, issueId, true);
  const [index, setIndex] = React.useState(0);
  const box = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);

  React.useLayoutEffect(() => {
    const node = box.current;
    if (!node) return;
    const measure = () => setWidth(node.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const payload = preview.data;
  const count = payload?.doc?.sheets?.length ?? 0;
  const current = Math.min(index, Math.max(count - 1, 0));
  const natural = sheetPixelSize(payload?.doc ?? null);
  const scale = natural.width > 0 && width > 0 ? Math.min(1, width / natural.width) : 0;

  return (
    <section className="flex min-w-0 flex-col gap-2" data-testid="spec-sheet-preview">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">Preview</h3>
        {count > 0 && (
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="outline"
              aria-label="Previous page"
              disabled={current === 0}
              onClick={() => setIndex(current - 1)}
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="min-w-20 text-center text-xs text-muted-foreground">
              Page {current + 1} of {count}
            </span>
            <Button
              size="sm"
              variant="outline"
              aria-label="Next page"
              disabled={current >= count - 1}
              onClick={() => setIndex(current + 1)}
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        )}
      </div>
      <div ref={box} className="min-w-0">
        {preview.isLoading ? (
          <Skeleton className="aspect-video w-full" />
        ) : preview.error ? (
          <EmptyState
            title="The pages could not be drawn"
            hint={preview.error instanceof Error ? preview.error.message : 'Try again in a moment.'}
          />
        ) : payload && scale > 0 ? (
          <ScaledSheet
            payload={{ ...payload, page_id: '', source: 'version' } as TagSheetDesignPayload}
            sheetIndex={current}
            scale={scale}
          />
        ) : null}
      </div>
    </section>
  );
}
