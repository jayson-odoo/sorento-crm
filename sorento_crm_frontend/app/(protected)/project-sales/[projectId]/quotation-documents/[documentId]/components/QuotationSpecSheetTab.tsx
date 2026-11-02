'use client';

import * as React from 'react';
import { ChevronLeft, ChevronRight, EyeOff, FileDown, RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Sortable, SortableItem, SortableItemHandle } from '@/components/ui/sortable';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import ScaledSheet, { PX_PER_MM, sheetPixelSize } from '@/components/dealer-kit/ScaledSheet';
import type { TagSheetDesignPayload } from '@/lib/dealer-kit/design-payload';
import type { TagLayer } from '@/lib/dealer-kit/tag-template-types';

import {
  useSpecSheet,
  useSpecSheetMutations,
  useSpecSheetPreview,
} from '../../../../_shared/hooks/useSpecSheet';
import type {
  SpecSheetPage,
  SpecSheetPreview,
  SpecSheetRow,
  SpecSheetView,
} from '../../../../_shared/services/specSheetService';
import { useQuotationDocumentScreen } from './QuotationDocumentContext';

/**
 * PS-SPEC-SHEET: the project spec sheet of this quotation - a cover plus one page per quoted
 * item, drawn by the Spec sheet templates designed in Dealer Kit > Tag Templates.
 *
 * The pages ARE the editor (owner, mock v5): no table. A strip of the pages (drag to reorder),
 * the open page as it prints, and on it: click AREA / COMMENT / marker to type over them, Leave
 * out / Put back, Add accessory. AREA starts as the Section heading the line sits under on the
 * Lines tab. Everything saves on its own, keyed by item, so the next revision keeps it.
 */
export function QuotationSpecSheetTab() {
  const { projectId, documentId, canEdit } = useQuotationDocumentScreen();
  const [issueId, setIssueId] = React.useState<string | null>(null);
  const view = useSpecSheet(projectId, documentId, issueId);
  const { save, exportPdf } = useSpecSheetMutations(projectId, documentId);

  const data = view.data;
  const effectiveIssueId = issueId ?? data?.issue_id ?? null;
  const settings = data?.settings;
  const ready = Boolean(
    effectiveIssueId && settings?.cover_template_id && settings?.page_template_id,
  );
  const preview = useSpecSheetPreview(projectId, documentId, effectiveIssueId, ready);

  if (view.isLoading) {
    return (
      <div className="flex flex-col gap-3" data-testid="spec-sheet-loading">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="aspect-video w-full" />
      </div>
    );
  }
  if (view.error || !data) {
    return (
      <EmptyState
        title="The spec sheet could not load"
        hint={view.error instanceof Error ? view.error.message : 'Try again in a moment.'}
      />
    );
  }

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
        <EmptyState title="No issued revision yet" hint="Issue a revision first." />
      ) : data.templates.cover.length === 0 || data.templates.page.length === 0 ? (
        <EmptyState
          title="No spec sheet templates"
          hint="Publish a Spec sheet cover and a Spec sheet page template in Dealer Kit > Tag Templates."
        />
      ) : data.pages.length === 0 ? (
        <EmptyState
          title="No items on this revision"
          hint="Add a product or product set line to the quotation."
        />
      ) : !ready ? null : preview.isLoading ? (
        <Skeleton className="aspect-video w-full" />
      ) : preview.error || !preview.data ? (
        <EmptyState
          title="The pages could not be drawn"
          hint={preview.error instanceof Error ? preview.error.message : 'Try again in a moment.'}
        />
      ) : (
        <SpecSheetPages
          pages={data.pages}
          payload={preview.data}
          canEdit={canEdit}
          onRows={(rows) => save.mutate({ rows })}
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

function templateOptions(
  rows: { id: string; name: string; width_mm: number | null; height_mm: number | null }[],
) {
  return rows.map((row) => ({
    value: row.id,
    label:
      row.width_mm && row.height_mm ? `${row.name} (${row.width_mm} x ${row.height_mm} mm)` : row.name,
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

const COVER = 'cover';
const THUMB_WIDTH = 132;

/** Which page field a text layer prints, if it is one a page may type over. */
type EditableField = 'area' | 'comment' | 'marker';
const FIELD_TOKENS: Record<EditableField, RegExp> = {
  area: /\{\{\s*line\.area\s*\}\}/,
  comment: /\{\{\s*line\.comment\s*\}\}/,
  marker: /\{\{\s*line\.marker\s*\}\}/,
};
const FIELD_LABELS: Record<EditableField, string> = {
  area: 'Area',
  comment: 'Comment',
  marker: 'Marker',
};

function editableField(layer: TagLayer): EditableField | null {
  if (layer.props.kind !== 'text') return null;
  const text = layer.text_override ?? layer.props.text ?? '';
  return (Object.keys(FIELD_TOKENS) as EditableField[]).find((f) => FIELD_TOKENS[f].test(text)) ?? null;
}

function SpecSheetPages({
  pages,
  payload,
  canEdit,
  onRows,
}: {
  pages: SpecSheetPage[];
  payload: SpecSheetPreview;
  canEdit: boolean;
  onRows: (rows: SpecSheetRow[]) => void;
}) {
  const [items, setItems] = React.useState<SpecSheetPage[]>(pages);
  React.useEffect(() => setItems(pages), [pages]);
  const [selected, setSelected] = React.useState<string>(COVER);

  const sheetIndex = React.useMemo(() => {
    const map = new Map<string, number>();
    (payload.doc?.sheets ?? []).forEach((sheet, index) => {
      const key = sheet.tags[0]?.request_tag_id;
      if (key) map.set(key, index);
    });
    return map;
  }, [payload]);

  const commit = (next: SpecSheetPage[]) => {
    setItems(next);
    onRows(next.map(rowOf));
  };
  const patch = (key: string, change: Partial<SpecSheetPage>) =>
    commit(items.map((page) => (page.key === key ? { ...page, ...change } : page)));

  // Page numbers count printed pages only; the cover is page 1.
  const numbers = new Map<string, number>();
  let printed = 1;
  for (const page of items) if (!page.hidden) numbers.set(page.key, ++printed);

  const order = [COVER, ...items.map((p) => p.key)];
  const position = order.indexOf(selected);
  const current = items.find((p) => p.key === selected) ?? null;
  const fullPayload = { ...payload, page_id: '', source: 'version' } as TagSheetDesignPayload;
  const natural = sheetPixelSize(payload.doc ?? null);
  const thumbScale = natural.width > 0 ? THUMB_WIDTH / natural.width : 0;

  return (
    <div className="flex min-w-0 flex-col gap-3" data-testid="spec-sheet-pages">
      <div className="flex min-w-0 gap-2 overflow-x-auto pb-2" data-testid="spec-sheet-strip">
        <PageThumb
          label="1 Cover"
          active={selected === COVER}
          onSelect={() => setSelected(COVER)}
          payload={fullPayload}
          sheet={sheetIndex.get(COVER)}
          scale={thumbScale}
        />
        <Sortable
          value={items}
          onValueChange={(next) => commit(next as SpecSheetPage[])}
          getItemValue={(page) => page.key}
          strategy="horizontal"
        >
          <div className="flex gap-2">
            {items.map((page) => (
              <SortableItem key={page.key} value={page.key} disabled={!canEdit}>
                <PageThumb
                  label={`${numbers.get(page.key) ?? '-'} ${page.code}`}
                  active={selected === page.key}
                  hidden={page.hidden}
                  onSelect={() => setSelected(page.key)}
                  payload={fullPayload}
                  sheet={sheetIndex.get(page.key)}
                  scale={thumbScale}
                  handle={
                    canEdit ? (
                      <SortableItemHandle
                        aria-label={`Drag ${page.code} to reorder`}
                        className="absolute left-1 top-1"
                        style={{ width: THUMB_WIDTH, height: (THUMB_WIDTH * 9) / 16 }}
                        onClick={() => setSelected(page.key)}
                      />
                    ) : null
                  }
                />
              </SortableItem>
            ))}
          </div>
        </Sortable>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="text-sm font-semibold" data-testid="spec-sheet-open-page">
            {current
              ? `${current.hidden ? 'Left out' : `Page ${numbers.get(current.key)}`}: ${current.code}`
              : 'Page 1: Cover'}
          </span>
          {current && canEdit && (
            <PageActions page={current} pages={items} onChange={(c) => patch(current.key, c)} />
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            aria-label="Previous page"
            disabled={position <= 0}
            onClick={() => setSelected(order[position - 1])}
          >
            <ChevronLeft className="size-4" />
          </Button>
          <Button
            size="sm"
            variant="outline"
            aria-label="Next page"
            disabled={position >= order.length - 1}
            onClick={() => setSelected(order[position + 1])}
          >
            <ChevronRight className="size-4" />
          </Button>
        </div>
      </div>

      <OpenPage
        payload={fullPayload}
        sheet={sheetIndex.get(selected)}
        page={current}
        canEdit={canEdit}
        onChange={(c) => current && patch(current.key, c)}
      />
    </div>
  );
}

function PageThumb({
  label,
  active,
  hidden = false,
  onSelect,
  payload,
  sheet,
  scale,
  handle,
}: {
  label: string;
  active: boolean;
  hidden?: boolean;
  onSelect: () => void;
  payload: TagSheetDesignPayload;
  sheet: number | undefined;
  scale: number;
  handle?: React.ReactNode;
}) {
  return (
    <div
      className={`relative flex shrink-0 flex-col gap-1 rounded-md p-1 ${
        active ? 'ring-2 ring-primary' : 'ring-1 ring-border'
      } ${hidden ? 'opacity-50' : ''}`}
      style={{ width: THUMB_WIDTH + 8 }}
    >
      <div
        className="overflow-hidden rounded-sm bg-muted"
        style={{ width: THUMB_WIDTH, height: (THUMB_WIDTH * 9) / 16 }}
        onClick={onSelect}
        aria-hidden
      >
        {sheet !== undefined && scale > 0 ? (
          <ScaledSheet payload={payload} sheetIndex={sheet} scale={scale} />
        ) : (
          <div className="flex size-full items-center justify-center text-2xs text-muted-foreground">
            Left out
          </div>
        )}
      </div>
      <button
        type="button"
        className="truncate text-left text-xs text-muted-foreground"
        title={label}
        onClick={onSelect}
        aria-pressed={active}
      >
        {label}
      </button>
      {handle}
    </div>
  );
}

function PageActions({
  page,
  pages,
  onChange,
}: {
  page: SpecSheetPage;
  pages: SpecSheetPage[];
  onChange: (change: Partial<SpecSheetPage>) => void;
}) {
  const accId = React.useId();
  // Another page's item with no picks of its own, or one this page already picked.
  const options: SearchableSelectOption[] = [
    ...pages
      .filter((other) => other.key !== page.key && other.picked.length === 0)
      .map((other) => ({ value: other.key, label: `${other.code} ${other.name}`.trim() })),
    ...page.accessories
      .filter((a) => a.source === 'picked' && a.key)
      .map((a) => ({ value: a.key as string, label: `${a.code} ${a.name}`.trim() })),
  ];
  return (
    <>
      <Button
        size="sm"
        variant="outline"
        onClick={() => onChange({ hidden: !page.hidden })}
        data-testid="spec-sheet-leave-out"
      >
        {page.hidden ? <RotateCcw className="size-4" aria-hidden /> : <EyeOff className="size-4" aria-hidden />}
        {page.hidden ? 'Put back' : 'Leave out'}
      </Button>
      <div className="w-56 min-w-0">
        <Label htmlFor={accId} className="sr-only">
          Add accessory
        </Label>
        <SearchableMultiSelect
          id={accId}
          size="sm"
          value={page.picked}
          onChange={(v: string[]) => onChange({ picked: v })}
          options={options}
          placeholder="Add accessory"
        />
      </div>
    </>
  );
}

function OpenPage({
  payload,
  sheet,
  page,
  canEdit,
  onChange,
}: {
  payload: TagSheetDesignPayload;
  sheet: number | undefined;
  page: SpecSheetPage | null;
  canEdit: boolean;
  onChange: (change: Partial<SpecSheetPage>) => void;
}) {
  const box = React.useRef<HTMLDivElement>(null);
  const [width, setWidth] = React.useState(0);
  const [editing, setEditing] = React.useState<EditableField | null>(null);
  const [draft, setDraft] = React.useState('');

  React.useLayoutEffect(() => {
    const node = box.current;
    if (!node) return;
    const measure = () => setWidth(node.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  React.useEffect(() => setEditing(null), [page?.key]);

  const natural = sheetPixelSize(payload.doc ?? null);
  const scale = natural.width > 0 && width > 0 ? Math.min(1, width / natural.width) : 0;
  const tag = sheet !== undefined ? payload.doc?.sheets[sheet]?.tags[0] : undefined;
  // The spots a page may type over: text layers of the template printing AREA / COMMENT / marker.
  const spots = page && canEdit && tag
    ? tag.layers
        .filter((l) => l.visible !== false)
        .map((layer) => ({ layer, field: editableField(layer) }))
        .filter((s): s is { layer: TagLayer; field: EditableField } => s.field !== null)
    : [];
  const px = (mm: number) => mm * PX_PER_MM * scale;

  const start = (field: EditableField) => {
    if (!page) return;
    setDraft(page[field]);
    setEditing(field);
  };
  const finish = () => {
    if (page && editing && draft !== page[editing]) {
      const value = editing === 'area' ? draft.trim().toUpperCase() : draft;
      onChange({ [editing]: value } as Partial<SpecSheetPage>);
    }
    setEditing(null);
  };

  if (page?.hidden) {
    return <EmptyState title="Left out of the spec sheet" hint="Put back prints this page again." />;
  }

  return (
    <div ref={box} className="min-w-0" data-testid="spec-sheet-open">
      {sheet !== undefined && scale > 0 && (
        <div className="relative" style={{ width: natural.width * scale }}>
          <ScaledSheet payload={payload} sheetIndex={sheet} scale={scale} />
          {spots.map(({ layer, field }) => {
            const style: React.CSSProperties = {
              position: 'absolute',
              left: px(layer.x_mm),
              top: px(layer.y_mm),
              width: px(layer.width_mm),
              height: Math.max(px(layer.height_mm), 20),
            };
            return editing === field ? (
              <Input
                key={layer.id}
                autoFocus
                aria-label={FIELD_LABELS[field]}
                value={draft}
                maxLength={field === 'marker' ? 10 : field === 'area' ? 200 : 500}
                onChange={(e) => setDraft(e.target.value)}
                onBlur={finish}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') finish();
                  if (e.key === 'Escape') setEditing(null);
                }}
                style={style}
                className="h-auto rounded-sm bg-background px-1 py-0 text-xs"
              />
            ) : (
              <button
                key={layer.id}
                type="button"
                aria-label={`Edit ${FIELD_LABELS[field]}`}
                title={`Edit ${FIELD_LABELS[field]}`}
                onClick={() => start(field)}
                style={style}
                className="rounded-sm outline-dashed outline-1 outline-transparent hover:bg-primary/5 hover:outline-primary focus-visible:outline-primary"
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
