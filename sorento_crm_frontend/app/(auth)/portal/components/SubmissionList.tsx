'use client';

/**
 * One kind's list of the contact's own forms (PORTAL-P4-REQUESTS L2, owner a25895124 Q1 a): the
 * toolbar (Filter, Sort, card / list toggle, Create on the same row), the cards or the list, and
 * the long-press preview. `PortalLanding` renders `SubmissionList` under its kind picker; a
 * salesperson's CRM list page renders `KindSubmissionList` for its one kind
 * (`components/common/MyRequestPortalList`).
 *
 * Rows and links come from the injected client (`useSubmissionClient`): absent, the portal's
 * calls and paths, so the portal is unchanged. Inside the CRM (`clientEmbedded`) Create reads
 * "Create" and is shown only when the caller says the user may create.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  ArrowDown,
  ArrowUp,
  Copy,
  FileText,
  Plus,
} from 'lucide-react';
import type { ColumnDef } from '@tanstack/react-table';
import { getCoreRowModel, useReactTable } from '@tanstack/react-table';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridTable } from '@/components/ui/data-grid-table';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Skeleton } from '@/components/ui/skeleton';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import type { ListBoardViewMode } from '@/hooks/useListBoardViewPreference';
import { formatCurrency } from '@/lib/helpers';
import {
  complaintStatusLabel,
  complaintStatusPillClass,
} from '@/lib/complaint-status';
import { revisionBadgeLabel } from '@/lib/document-number';
import {
  LANDING_LABELS,
  PortalLandingKind,
  PortalSubmissionKind,
  PortalSubmissionSummary,
  isSubmissionKind,
} from '../lib/portal-client';
import {
  clientEmbedded,
  clientPaths,
  clientService,
  useSubmissionClient,
  type SubmissionClient,
  type SubmissionPaths,
} from '../lib/submission-client';
import * as portalPriceTagRequest from '../lib/price-tag-request-service';
import * as portalSampleRequest from '../lib/sample-request-service';
import * as portalNewProductApplication from '../lib/new-product-application-service';
import * as portalSalesOpportunity from '../lib/sales-opportunity-service';
import { listOpportunitiesAsSummaries } from '../lib/sales-opportunity-landing';
import {
  portalDetailPath,
  portalDuplicatePath,
  portalHomePath,
  portalNewPath,
  portalRevisePath,
} from '../lib/portal-paths';
import { useRevisionPolicy } from '../hooks/useRevisions';
import { ReviseAction } from './ReviseAction';
import { LandingCardShell } from './LandingCardShell';
import { LandingToolbar } from './LandingToolbar';
import {
  DEFAULT_LANDING_SORT,
  activeLandingFilterCount,
  applyLandingFilters,
  landingFieldValue,
  landingFieldsFor,
  isShownAsDraft,
  sortLandingItems,
  submissionStatusLabel,
  type LandingField,
  type LandingFilters,
  type LandingSort,
} from '../lib/landing-fields';

/**
 * One kind's rows in the landing's summary shape, through `client`. Each kind answers its own
 * endpoint in its own shape: the four with services of their own adapt theirs, the rest ride the
 * generic `/submissions?type=` list.
 */
export function listKindSummaries(
  client: SubmissionClient,
  kind: PortalLandingKind,
  q?: string,
): Promise<PortalSubmissionSummary[]> {
  if (kind === 'price_tag_request') {
    return clientService(
      client,
      'priceTagRequest',
      portalPriceTagRequest,
    ).listRequestsAsSummaries(q);
  }
  if (kind === 'sample_request') {
    return clientService(
      client,
      'sampleRequest',
      portalSampleRequest,
    ).listSampleRequestsAsSummaries(q);
  }
  if (kind === 'new_product_application') {
    return clientService(
      client,
      'newProductApplication',
      portalNewProductApplication,
    ).listNewProductApplicationsAsSummaries(q);
  }
  if (kind === 'sales_opportunity') {
    return listOpportunitiesAsSummaries(q, () =>
      clientService(
        client,
        'salesOpportunity',
        portalSalesOpportunity,
      ).listPortalSalesOpportunities(),
    );
  }
  return client.fetchSubmissions(kind as PortalSubmissionKind, q);
}

/** The list's links: the client's, or the portal's own tree (`slug`). */
function listPaths(
  paths: SubmissionPaths | undefined,
  slug?: string,
): SubmissionPaths {
  return (
    paths ?? {
      home: (kind) => portalHomePath({ slug, type: kind }),
      new: (kind) => portalNewPath(kind, slug),
      detail: (kind, id) => portalDetailPath(kind, id, slug),
      duplicate: (kind, id) => portalDuplicatePath(kind, id, slug),
      revise: (kind, id) => portalRevisePath(kind, id, slug),
    }
  );
}

function useListPaths(slug?: string): SubmissionPaths {
  const client = useSubmissionClient();
  const paths = clientPaths(client);
  return useMemo(() => listPaths(paths, slug), [paths, slug]);
}

// Shared across every kind, so the choice survives a type switch (AC-L7).
const PORTAL_VIEW_KEY = 'sorento.portalView';

/**
 * Cards or list. Cards is the default at EVERY width (R3-2, AC-R9); a stored choice still wins,
 * per device, across a reload and a type switch (AC-L7).
 */
export function usePortalListView(): [
  ListBoardViewMode,
  (mode: ListBoardViewMode) => void,
] {
  const [view, setViewState] = useState<ListBoardViewMode>('board');
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.localStorage.getItem(PORTAL_VIEW_KEY);
    if (stored === 'list' || stored === 'board') {
      setViewState(stored);
    }
  }, []);
  const setView = useCallback((mode: ListBoardViewMode) => {
    setViewState(mode);
    if (typeof window !== 'undefined') {
      window.localStorage.setItem(PORTAL_VIEW_KEY, mode);
    }
  }, []);
  return [view, setView];
}

type BadgeVariant =
  | 'primary'
  | 'secondary'
  | 'destructive'
  | 'success'
  | 'warning'
  | 'info';

// Status → badge colour. draft is intentionally neutral (no colour) so it
// reads as "not yet meaningful". The other states map to a unique colour so
// users can scan a list without reading labels.
function statusVariant(row: PortalSubmissionSummary): BadgeVariant {
  if (isShownAsDraft(row)) return 'secondary';
  const s = (row.status || '').toLowerCase();
  if (s === 'rejected' || s === 'cancelled' || s === 'lost')
    return 'destructive';
  if (
    s === 'won' ||
    s === 'approved' ||
    s === 'completed' ||
    s === 'fulfilled' ||
    s === 'settled_on_site' ||
    s === 'closed'
  ) {
    return 'success';
  }
  if (s === 'responded' || s === 'replied') return 'info';
  return 'primary';
}

// Tailwind classes that tint the card background + border by status. Kept
// subtle so text stays legible.
function statusCardClass(row: PortalSubmissionSummary): string {
  if (isShownAsDraft(row)) {
    return 'bg-card border-border';
  }
  const s = (row.status || '').toLowerCase();
  if (s === 'rejected' || s === 'cancelled' || s === 'lost') {
    return 'bg-destructive/5 border-destructive/40';
  }
  if (
    s === 'won' ||
    s === 'approved' ||
    s === 'completed' ||
    s === 'fulfilled' ||
    s === 'settled_on_site' ||
    s === 'closed'
  ) {
    return 'bg-success/5 border-success/40';
  }
  if (s === 'responded' || s === 'replied') {
    return 'bg-violet-50 border-violet-200 dark:bg-violet-950/30 dark:border-violet-900';
  }
  return 'bg-primary/5 border-primary/30';
}

// Per-kind primary/secondary metadata picked for the compact card layout.
function pickCardMeta(row: PortalSubmissionSummary): {
  product?: string;
  project?: string;
  customer?: string;
} {
  if (row.kind === 'complaint') {
    return {
      product: row.product_code ?? undefined,
      project: row.project_title ?? undefined,
      customer: row.customer_name ?? undefined,
    };
  }
  if (row.kind === 'stock_inquiry') {
    return {
      product: row.product_code ?? undefined,
      project: row.project_name ?? undefined,
      customer: row.project_customer ?? undefined,
    };
  }
  if (
    row.kind === 'price_tag_request' ||
    row.kind === 'sales_opportunity' ||
    row.kind === 'sample_request' ||
    row.kind === 'new_product_application'
  ) {
    return { customer: row.customer_name ?? undefined };
  }
  return {
    project: row.project_title ?? row.sponsor_subject ?? undefined,
    customer: row.customer_name ?? undefined,
  };
}

/** "New <label>", except a label that already starts with "New" (New Product Application). */
function newKindLabel(kind: PortalLandingKind): string {
  const label = LANDING_LABELS[kind];
  return /^New\b/.test(label) ? label : `New ${label}`;
}

/**
 * One kind on its own (a CRM list page, L2): the search, then `SubmissionList`, its rows read
 * through the client. No kind picker, no portal header, no verify redirect; the page's own
 * width. `onCreate`: Create opens something on the page instead of a `/new` page (an
 * opportunity's Log opportunity modal).
 */
export function KindSubmissionList({
  kind,
  canCreate,
  onCreate,
}: {
  kind: PortalLandingKind;
  canCreate: boolean;
  onCreate?: () => void;
}) {
  const client = useSubmissionClient();
  const {
    value: search,
    setValue: setSearch,
    debouncedValue: debouncedSearch,
    isSettling: searchSettling,
  } = useDebouncedSearch();
  const [view, setView] = usePortalListView();
  const [filters, setFilters] = useState<LandingFilters>({});
  const [sort, setSort] = useState<LandingSort>(DEFAULT_LANDING_SORT);
  const [items, setItems] = useState<PortalSubmissionSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listKindSummaries(client, kind, debouncedSearch)
      .then((rows) => {
        if (cancelled) return;
        setItems(rows);
        setError(null);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(
          e instanceof Error ? e.message : 'Failed to load submissions.',
        );
      });
    return () => {
      cancelled = true;
    };
  }, [client, kind, debouncedSearch]);

  return (
    <div className="space-y-3">
      <ListSearchInput
        value={search}
        onChange={setSearch}
        isSettling={searchSettling}
        placeholder="Search..."
        aria-label="Search submissions"
        className="w-full"
        inputClassName="h-12 text-base"
      />
      {error ? (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      ) : items === null ? (
        <div className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <SubmissionList
          kind={kind}
          items={items}
          filters={filters}
          onFiltersChange={setFilters}
          sort={sort}
          onSortChange={setSort}
          view={view}
          onViewChange={setView}
          search={search}
          onClearSearch={() => setSearch('')}
          canCreate={canCreate}
          onCreate={onCreate}
        />
      )}
    </div>
  );
}

export function SubmissionList({
  kind,
  items,
  filters,
  onFiltersChange,
  sort,
  onSortChange,
  view,
  onViewChange,
  slug,
  search,
  onClearSearch,
  embedded = false,
  canCreate = true,
  onCreate,
}: {
  kind: PortalLandingKind;
  items: PortalSubmissionSummary[];
  filters: LandingFilters;
  onFiltersChange: (next: LandingFilters) => void;
  sort: LandingSort;
  onSortChange: (next: LandingSort) => void;
  view: ListBoardViewMode;
  onViewChange: (mode: ListBoardViewMode) => void;
  slug?: string;
  /** A search term is answered server-side (`fetchSubmissions(kind, q)`),
   *  so a search-only zero result already arrives as `items.length === 0`
   *  with no client-side `filters` set at all (review round 2, AC-L8) - the
   *  empty state has to know about it too, not just `filters`. */
  search?: string;
  onClearSearch?: () => void;
  /** Inside the CRM shell: the New label shows in full at every width (the row wraps instead). */
  embedded?: boolean;
  /** False: no Create (a CRM user without the kind's create grant). */
  canCreate?: boolean;
  /** Create opens something on the page instead of navigating (see `KindSubmissionList`). */
  onCreate?: () => void;
}) {
  const client = useSubmissionClient();
  const paths = useListPaths(slug);
  // Inside a CRM page (the injected client): the CRM's own word, at every width.
  const inCrm = clientEmbedded(client);
  const createLabel = inCrm ? 'Create' : newKindLabel(kind);
  const fields = useMemo(() => landingFieldsFor(kind), [kind]);
  const filtered = useMemo(
    () =>
      sortLandingItems(
        applyLandingFilters(items, fields, filters),
        fields,
        sort,
      ),
    [items, fields, filters, sort],
  );

  const [previewRow, setPreviewRow] = useState<PortalSubmissionSummary | null>(
    null,
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <LandingToolbar
          fields={fields}
          items={items}
          filters={filters}
          onFiltersChange={onFiltersChange}
          sort={sort}
          onSortChange={onSortChange}
          view={view}
          onViewChange={onViewChange}
        />
        {!canCreate ? null : onCreate ? (
          <Button
            type="button"
            size="sm"
            className="shrink-0"
            title={createLabel}
            aria-label={createLabel}
            onClick={onCreate}
          >
            <Plus className="shrink-0" />
            <span className="whitespace-nowrap">{createLabel}</span>
          </Button>
        ) : (
          <Button
            asChild
            size="sm"
            className="shrink-0"
            title={createLabel}
            aria-label={createLabel}
          >
            <Link href={paths.new(kind)}>
              <Plus className="shrink-0" />
              {/* Review round 2/3: "New Price Tag Request" (the longest label)
                  pushed the toolbar onto two rows at 375px - below `sm` the
                  clip hides everything past "New" (no ellipsis, so it never
                  shows a ragged fragment of the kind name), the full label at
                  `sm` and up. One text node, not two - a wrapping element
                  around a bare "New" here reads as a second, stray "New" next
                  to a submission card's own status badge of the same word
                  (`PortalLanding.priceTag.test.tsx`). */}
              <span
                className={
                  embedded || inCrm
                    ? 'whitespace-nowrap'
                    : 'block max-w-[31px] overflow-hidden whitespace-nowrap sm:max-w-none sm:inline'
                }
              >
                {createLabel}
              </span>
            </Link>
          </Button>
        )}
      </div>
      {filtered.length === 0 ? (
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground space-y-2">
            <FileText className="h-8 w-8 mx-auto" />
            {items.length === 0 &&
            !(search ?? '').trim() &&
            activeLandingFilterCount(filters) === 0 ? (
              <p>No {LANDING_LABELS[kind].toLowerCase()} submissions yet.</p>
            ) : (
              <>
                <p>No submissions match your filters.</p>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    onFiltersChange({});
                    onClearSearch?.();
                  }}
                >
                  Clear filters
                </Button>
              </>
            )}
          </CardContent>
        </Card>
      ) : view === 'list' ? (
        <SubmissionTable
          kind={kind}
          items={filtered}
          fields={fields}
          sort={sort}
          onSortChange={onSortChange}
          slug={slug}
        />
      ) : (
        <ul className="space-y-2.5">
          {filtered.map((row) => (
            <li key={row.id}>
              <SubmissionCard
                row={row}
                kind={kind}
                slug={slug}
                onLongPress={() => setPreviewRow(row)}
              />
            </li>
          ))}
        </ul>
      )}

      <SubmissionPreviewDialog
        row={previewRow}
        kind={kind}
        slug={slug}
        onOpenChange={(open) => !open && setPreviewRow(null)}
      />
    </div>
  );
}

/**
 * Click / long-press / keyboard wiring shared by SubmissionCard and
 * SubmissionRow (D-L5) - both open the detail page on a tap/click/Enter and
 * the preview dialog on a long-press, right-click or context-menu key.
 */
function useSubmissionPress({
  kind,
  id,
  slug,
  onLongPress,
}: {
  kind: PortalLandingKind;
  id: string;
  slug?: string;
  onLongPress: () => void;
}) {
  const router = useRouter();
  const paths = useListPaths(slug);
  const longPressTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressFired = useRef(false);

  const startPress = () => {
    longPressFired.current = false;
    longPressTimer.current = setTimeout(() => {
      longPressFired.current = true;
      onLongPress();
    }, 450);
  };
  const clearPress = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  return {
    role: 'link' as const,
    tabIndex: 0,
    onClick: () => {
      if (longPressFired.current) {
        longPressFired.current = false;
        return;
      }
      router.push(paths.detail(kind, id));
    },
    onKeyDown: (e: React.KeyboardEvent) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        router.push(paths.detail(kind, id));
      }
    },
    onContextMenu: (e: React.MouseEvent) => {
      e.preventDefault();
      onLongPress();
    },
    onTouchStart: startPress,
    onTouchEnd: clearPress,
    onTouchMove: clearPress,
    onTouchCancel: clearPress,
    onMouseDown: startPress,
    onMouseUp: clearPress,
    onMouseLeave: clearPress,
  };
}

/**
 * List view (R3-2, AC-R9/AC-R10): the repo DataGrid, one column per field of
 * the current kind, rather than the old `<ul>` of `SubmissionRow`. Header
 * click drives the SAME sort state the toolbar's Sort dropdown uses (R3-3's
 * rule: the active field flips direction, a different field picks its type's
 * natural default) - `SortableHeader` duplicates that small rule rather than
 * sharing it with `LandingToolbar`, since the two live in different DOM
 * shapes (menu item vs. column header).
 */
function SortableHeader({
  field,
  sort,
  onSortChange,
}: {
  field: LandingField;
  sort: LandingSort;
  onSortChange: (next: LandingSort) => void;
}) {
  const isActive = sort.key === field.key;
  return (
    <button
      type="button"
      className="flex items-center gap-1 text-left font-medium"
      onClick={(e) => {
        e.stopPropagation();
        onSortChange({
          key: field.key,
          dir: isActive
            ? sort.dir === 'asc'
              ? 'desc'
              : 'asc'
            : field.type === 'date'
              ? 'desc'
              : 'asc',
        });
      }}
    >
      <span>{field.label}</span>
      {isActive &&
        (sort.dir === 'asc' ? (
          <ArrowUp className="size-3.5 text-muted-foreground" />
        ) : (
          <ArrowDown className="size-3.5 text-muted-foreground" />
        ))}
    </button>
  );
}

function submissionTableColumns(
  fields: LandingField[],
  sort: LandingSort,
  onSortChange: (next: LandingSort) => void,
): ColumnDef<PortalSubmissionSummary>[] {
  // Named, not an anonymous arrow returned from `header()` (react/display-name):
  // a ColumnDef.header renders as its own component, and an unnamed one
  // trips the lint rule even though it never gets its own devtools entry.
  const header = (field: LandingField) => {
    function SortableColumnHeader() {
      return (
        <SortableHeader field={field} sort={sort} onSortChange={onSortChange} />
      );
    }
    return SortableColumnHeader;
  };
  const documentField = fields.find((f) => f.key === 'document_number') ?? {
    key: 'document_number',
    label: 'Form Number',
    type: 'text' as const,
  };
  const statusField = fields.find((f) => f.key === 'status') ?? {
    key: 'status',
    label: 'Status',
    type: 'status' as const,
  };
  const createdField = fields.find((f) => f.key === 'created_at') ?? {
    key: 'created_at',
    label: 'Created',
    type: 'date' as const,
  };
  // Every kind's card carries these three as COMMON_FIELDS; everything else
  // in `fields` is the kind's own set. `needed_by_date` (price_tag_request
  // only) is a date, so it never lands here - it gets its own "Need by"
  // column below, same as the card's dedicated "Need by" row.
  const textKindFields = fields.filter(
    (f) =>
      f.type === 'text' && f.key !== 'document_number' && f.key !== 'status',
  );
  // Review round 3: the column only exists for a kind that actually carries
  // the field (today, price_tag_request only) - a synthetic descriptor for
  // every other kind gave every list a permanently blank "Need by" column.
  const needByField = fields.find((f) => f.key === 'needed_by_date');

  const dateCell = (value: string | null | undefined) =>
    value ? (
      new Date(value).toLocaleDateString()
    ) : (
      <span className="text-muted-foreground">-</span>
    );

  const columns: ColumnDef<PortalSubmissionSummary>[] = [
    {
      accessorKey: 'document_number',
      header: header(documentField),
      cell: ({ row }) => {
        const value = row.original.document_number ?? row.original.title ?? '-';
        return (
          <span className="block truncate" title={value}>
            {value}
          </span>
        );
      },
      size: 170,
      minSize: 100,
    },
    {
      accessorKey: 'status',
      header: header(statusField),
      cell: ({ row }) => {
        const text = submissionStatusLabel(row.original);
        return (
          <Badge
            variant={statusVariant(row.original)}
            className="truncate"
            title={text}
          >
            {text}
          </Badge>
        );
      },
      size: 120,
      minSize: 90,
    },
    ...textKindFields.map(
      (field): ColumnDef<PortalSubmissionSummary> => ({
        accessorKey: field.key,
        header: header(field),
        cell: ({ row }) => {
          const value = landingFieldValue(row.original, field) ?? '-';
          return (
            <span className="block truncate" title={value}>
              {value}
            </span>
          );
        },
        size: 150,
        minSize: 100,
      }),
    ),
    ...(needByField
      ? [
          {
            accessorKey: 'needed_by_date',
            header: header(needByField),
            cell: ({ row }) => dateCell(row.original.needed_by_date),
            size: 110,
            minSize: 90,
          } satisfies ColumnDef<PortalSubmissionSummary>,
        ]
      : []),
    {
      accessorKey: 'created_at',
      header: header(createdField),
      cell: ({ row }) => dateCell(row.original.created_at),
      size: 110,
      minSize: 90,
    },
  ];
  return columns;
}

function SubmissionTable({
  kind,
  items,
  fields,
  sort,
  onSortChange,
  slug,
}: {
  kind: PortalLandingKind;
  items: PortalSubmissionSummary[];
  fields: LandingField[];
  sort: LandingSort;
  onSortChange: (next: LandingSort) => void;
  slug?: string;
}) {
  const paths = useListPaths(slug);
  const columns = useMemo(
    () => submissionTableColumns(fields, sort, onSortChange),
    [fields, sort, onSortChange],
  );
  // `items` arrives already filtered + sorted (`sortLandingItems`, driven by
  // the same `sort` state the column headers write to) - the table just
  // displays it in that order rather than re-sorting client-side itself.
  const table = useReactTable({
    columns,
    data: items,
    getRowId: (row) => row.id,
    getCoreRowModel: getCoreRowModel(),
    columnResizeMode: 'onChange',
  });

  return (
    <DataGrid
      table={table}
      recordCount={items.length}
      rowHref={(row) => paths.detail(kind, row.id)}
      // Columns are DATA (they change with the kind), never a fixed set to
      // remember per user - same rationale `McpToolsList` documents for its
      // own `listingKey={null}`.
      listingKey={null}
      tableLayout={{
        width: 'fixed',
        columnsResizable: true,
        columnsDraggable: false,
        columnsMovable: false,
        columnsVisibility: false,
      }}
    >
      <DataGridTable />
    </DataGrid>
  );
}

function SubmissionCard({
  row,
  kind,
  slug,
  onLongPress,
}: {
  row: PortalSubmissionSummary;
  kind: PortalLandingKind;
  slug?: string;
  onLongPress: () => void;
}) {
  const press = useSubmissionPress({ kind, id: row.id, slug, onLongPress });
  const meta = pickCardMeta(row);
  const primary = row.document_number ?? row.title ?? '-';
  const tintClass = statusCardClass(row);

  // Complaints use the shared status map so portal labels + colours tally with
  // the internal system view; other kinds keep the generic badge variant.
  const isComplaint = row.kind === 'complaint';
  const statusText = submissionStatusLabel(row);

  return (
    <LandingCardShell {...press} tintClass={tintClass}>
      {/* Status badge anchored top-right; allows multi-word status to wrap
          onto two lines without colliding with the primary text. */}
      {isComplaint && !row.is_draft ? (
        <span
          className={`absolute top-2 right-2 max-w-[45%] inline-flex items-center justify-end rounded-md px-2 py-0.5 text-xs font-semibold whitespace-normal text-right leading-tight ${complaintStatusPillClass(row.status)}`}
        >
          {statusText}
        </span>
      ) : (
        <Badge
          variant={statusVariant(row)}
          className="absolute top-2 right-2 max-w-[45%] whitespace-normal text-right leading-tight justify-end"
        >
          {statusText}
        </Badge>
      )}
      <div className="space-y-1 pr-[45%]">
        <div className="flex flex-wrap items-center gap-1.5">
          <p className="text-base font-semibold break-words" title={primary}>
            {primary}
          </p>
          {revisionBadgeLabel(row.revision_no) && (
            <Badge variant="secondary">
              {revisionBadgeLabel(row.revision_no)}
            </Badge>
          )}
          {row.has_revision_draft && (
            <Badge variant="warning" data-testid="revising-chip">
              Revising
            </Badge>
          )}
        </div>
      </div>
      <div className="space-y-1 mt-1">
        {meta.product && (
          <p
            className="text-sm text-foreground/80 break-words"
            title={meta.product}
          >
            <span className="text-muted-foreground">Product: </span>
            {meta.product}
          </p>
        )}
        {meta.project && (
          <p
            className="text-sm text-foreground/80 break-words"
            title={meta.project}
          >
            <span className="text-muted-foreground">Project: </span>
            {meta.project}
          </p>
        )}
        {meta.customer && (
          <p
            className="text-sm text-foreground/80 break-words"
            title={meta.customer}
          >
            <span className="text-muted-foreground">Customer: </span>
            {meta.customer}
          </p>
        )}
        {row.expected_amount != null && (
          <p className="text-sm text-foreground/80">
            <span className="text-muted-foreground">Amount: </span>
            {formatCurrency(row.expected_amount)}
          </p>
        )}
        {row.expected_close_date && (
          <p className="text-sm text-foreground/80">
            <span className="text-muted-foreground">Expected close: </span>
            {new Date(
              `${row.expected_close_date.slice(0, 10)}T00:00:00`,
            ).toLocaleDateString('en-GB', {
              dateStyle: 'medium',
            })}
          </p>
        )}
        {row.needed_by_date && (
          <p className="text-sm text-foreground/80">
            <span className="text-muted-foreground">Need by: </span>
            {new Date(row.needed_by_date).toLocaleDateString(undefined, {
              dateStyle: 'medium',
            })}
          </p>
        )}
        {row.last_revised_at ? (
          <p className="text-xs text-muted-foreground">
            Revised{' '}
            {new Date(row.last_revised_at).toLocaleDateString(undefined, {
              dateStyle: 'medium',
            })}
          </p>
        ) : (
          row.created_at && (
            <p className="text-xs text-muted-foreground">
              {new Date(row.created_at).toLocaleDateString(undefined, {
                dateStyle: 'medium',
              })}
            </p>
          )
        )}
        {row.rejection_reason && (
          <p className="text-xs text-destructive line-clamp-2">
            {row.rejection_reason}
          </p>
        )}
      </div>
    </LandingCardShell>
  );
}

function SubmissionPreviewDialog({
  row,
  kind,
  slug,
  onOpenChange,
}: {
  row: PortalSubmissionSummary | null;
  kind: PortalLandingKind;
  slug?: string;
  onOpenChange: (open: boolean) => void;
}) {
  const router = useRouter();
  const paths = useListPaths(slug);
  // The list carries no policy block, so the card reads the same `revision`
  // block the detail page renders from. One GET, opened on long press only.
  // Revisions are a submission-kind mechanism: a gated kind has no such
  // endpoint, so it is asked for nothing rather than 404ing on every preview.
  const { policy } = useRevisionPolicy(
    isSubmissionKind(kind) ? kind : 'stock_inquiry',
    isSubmissionKind(kind) ? (row?.id ?? null) : null,
  );
  const meta = row
    ? pickCardMeta(row)
    : { product: undefined, project: undefined, customer: undefined };
  const entries: { label: string; value: string }[] = [];
  if (row) {
    if (row.document_number)
      entries.push({ label: 'Document number', value: row.document_number });
    if (row.title) entries.push({ label: 'Title', value: row.title });
    if (meta.product) entries.push({ label: 'Product', value: meta.product });
    if (meta.project) entries.push({ label: 'Project', value: meta.project });
    if (meta.customer)
      entries.push({ label: 'Customer', value: meta.customer });
    if (row.delivery_order_number)
      entries.push({ label: 'DO number', value: row.delivery_order_number });
    if (row.item_description)
      entries.push({ label: 'Item description', value: row.item_description });
    if (row.purpose) entries.push({ label: 'Purpose', value: row.purpose });
    if (row.reference && row.reference !== row.document_number) {
      entries.push({ label: 'Reference', value: row.reference });
    }
    if (row.created_at) {
      entries.push({
        label: 'Created',
        value: new Date(row.created_at).toLocaleString(undefined, {
          dateStyle: 'medium',
          timeStyle: 'short',
        }),
      });
    }
    if (row.rejection_reason)
      entries.push({ label: 'Rejection reason', value: row.rejection_reason });
  }

  return (
    <Dialog open={Boolean(row)} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base flex items-center gap-2 flex-wrap">
            <span className="break-words">
              {row?.document_number ?? row?.title ?? 'Submission'}
            </span>
            {row &&
              (row.kind === 'complaint' && !row.is_draft ? (
                <span
                  className={`inline-flex items-center rounded-md px-2 py-0.5 text-xs font-semibold ${complaintStatusPillClass(row.status)}`}
                >
                  {complaintStatusLabel(row.status)}
                </span>
              ) : (
                <Badge variant={statusVariant(row)}>
                  {submissionStatusLabel(row)}
                </Badge>
              ))}
          </DialogTitle>
        </DialogHeader>
        <div className="flex-1 min-h-0 overflow-y-auto space-y-3 -mx-1 px-1">
          {entries.map((e) => (
            <div key={e.label} className="space-y-0.5">
              <p className="text-xs uppercase tracking-wide text-muted-foreground">
                {e.label}
              </p>
              <p className="text-sm break-words whitespace-pre-wrap">
                {e.value}
              </p>
            </div>
          ))}
        </div>
        <ReviseAction
          policy={policy}
          onRevise={() => {
            if (row) router.push(paths.revise(kind, row.id));
            onOpenChange(false);
          }}
          className="border-t pt-3"
        />
        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="h-10"
          >
            Close
          </Button>
          {/* An opportunity's New form takes no source to copy from. */}
          {kind !== 'sales_opportunity' ? (
            <Button
              variant="outline"
              onClick={() => {
                if (row) router.push(paths.duplicate(kind, row.id));
                onOpenChange(false);
              }}
              className="h-10"
            >
              <Copy className="h-4 w-4 mr-2" />
              Duplicate
            </Button>
          ) : null}
          <Button
            onClick={() => {
              if (row) router.push(paths.detail(kind, row.id));
              onOpenChange(false);
            }}
            className="h-10"
          >
            Open
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
