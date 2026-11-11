'use client';

import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import {
  ColumnDef,
  ExpandedState,
  PaginationState,
  SortingState,
  getCoreRowModel,
  getExpandedRowModel,
  useReactTable,
} from '@tanstack/react-table';
import {
  ChevronDown,
  ChevronRight,
  Download,
  ListPlus,
  LoaderCircleIcon,
  MoreHorizontal,
  Pencil,
  Settings,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import { DataGrid } from '@/components/ui/data-grid';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { DataGridListToolbar, type ToolbarAction } from '@/components/ui/data-grid-list-toolbar';
import { DataGridPagination } from '@/components/ui/data-grid-pagination';
import { DataGridTable } from '@/components/ui/data-grid-table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { Skeleton } from '@/components/ui/skeleton';
import { DatePicker, parseDateInput } from '@/components/ui/date-picker';
import { Container } from '@/components/common/container';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { SearchableSelect, type SearchableSelectOption } from '@/components/common/SearchableSelect';
import { isSearchInFlight, useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { useDeferredRowAction } from '@/hooks/useDeferredRowAction';
import { useHasPermission } from '@/hooks/usePermissions';
import { formatLocalDateToYyyyMmDd } from '@/lib/helpers';
import { joinMulti, multiChipLabel, splitMulti } from '@/lib/list-filters/multiValue';
import { toast } from '@/lib/toast';
import { useBrandSelectQuery } from '../../shared/hooks/use-brand-select-query';
import { useProductCategorySelectQuery } from '../../shared/hooks/use-product-category-select-query';
import {
  COSTING_PARTY_KEY,
  COSTING_ROWS_KEY,
  useCostingParty,
  useCostingRows,
  useCostingSuppliers,
  useExportCosting,
  useSaveCostingRows,
} from '../hooks/useCosting';
import {
  METHOD_LABEL,
  TRANSPORT_LABEL,
  figuresFor,
  type Figures,
  money,
  percent,
  reasonText,
  shortDate,
  transportText,
  trimmed,
} from '../lib/format';
import { searchCustomersSelect } from '../../../order-management/customers/services/customerService';
import type {
  CostingParty,
  CostingReason,
  CostingRow,
  CostingRowsParams,
  CostMethod,
  RowChange,
  TransportMode,
} from '../types/costing.types';
import AddCostingProductsDialog from './AddCostingProductsDialog';
import CostingHistoryDialog from './CostingHistoryDialog';
import CostingSettingsDialog from './CostingSettingsDialog';
import CostingSupplierGrid from './CostingSupplierGrid';
import PartyProfileDialog from './PartyProfileDialog';

const SET_ON_ROW = 'Set on this row';
const METHOD_OPTIONS = (Object.keys(METHOD_LABEL) as CostMethod[]).map((value) => ({
  value,
  label: METHOD_LABEL[value],
}));
const MODE_OPTIONS = (Object.keys(TRANSPORT_LABEL) as TransportMode[]).map((value) => ({
  value,
  label: TRANSPORT_LABEL[value],
}));

/** Every data column sorts on the server (owner rule: all columns sortable), keyed by column id. */
const SERVER_SORT: Record<string, string> = {
  category: 'category_name',
  code: 'product_code',
  name: 'product_name',
  supplier: 'supplier_name',
  cost: 'unit_cost',
  rate: 'units_per_base',
  sst: 'sst_factor',
  transport: 'transport',
  landing: 'landing',
  method: 'cost_method',
  markup: 'markup_pct',
  final: 'final',
  list_price: 'list_price',
  margin: 'margin_pct',
};

// ------------------------------------------------------------------ drafts

/** One row's editable cells, as typed. */
interface Draft {
  markup: string;
  tMode: string;
  tValue: string;
  method: string;
  supplier: string;
}

interface Edit {
  base: Draft;
  cur: Draft;
}

/** What the row says now: only values set ON the row start filled; inherited ones start empty. */
function initialDraft(row: CostingRow): Draft {
  const onProduct = row.transport_source === 'product';
  return {
    markup: row.markup_source === 'row' && row.markup_pct !== null ? String(row.markup_pct) : '',
    tMode: onProduct ? (row.transport_mode ?? '') : '',
    tValue: onProduct && row.transport_value !== null ? String(row.transport_value) : '',
    method: row.cost_method_source === 'product' ? row.cost_method : '',
    supplier: row.cost_method_supplier_id ?? '',
  };
}

/** A figure typed into a box: a number, or null when blank or not a number. */
function typed(raw: string): number | null {
  if (raw.trim() === '') return null;
  const n = Number(raw);
  return Number.isFinite(n) ? n : null;
}

/** The changed cells of every edited row, or the first problem found (nothing is sent then). */
function buildChanges(edits: Record<string, Edit>, view: 'standard' | 'party'): RowChange[] | string {
  const out: RowChange[] = [];
  for (const [productId, { base, cur }] of Object.entries(edits)) {
    const change: RowChange = { product_id: productId };
    if (view === 'party' && cur.markup !== base.markup) {
      const was = typed(base.markup);
      const now = typed(cur.markup);
      if (cur.markup.trim() !== '' && (now === null || now < 0)) return 'A mark-up is a number of 0 or more.';
      if (was !== now) change.markup_pct = now;
    }
    if (cur.tMode !== base.tMode || cur.tValue !== base.tValue) {
      if (!cur.tMode && cur.tValue.trim() === '') {
        if (base.tMode || base.tValue) {
          change.transport_mode = null;
          change.transport_value = null;
        }
      } else {
        const value = typed(cur.tValue);
        if (!cur.tMode || value === null || value <= 0) {
          return 'Transport needs Add or Multiply and a value above zero, or clear both.';
        }
        if (cur.tMode !== base.tMode || value !== typed(base.tValue)) {
          change.transport_mode = cur.tMode as TransportMode;
          change.transport_value = value;
        }
      }
    }
    if (cur.method !== base.method || cur.supplier !== base.supplier) {
      if (!cur.method) {
        if (base.method) change.cost_method = null;
      } else if (cur.method === 'selected') {
        if (!cur.supplier) return 'Selected supplier needs a supplier.';
        change.cost_method = 'selected';
        change.cost_method_supplier_id = cur.supplier;
      } else if (cur.method !== base.method) {
        change.cost_method = cur.method as CostMethod;
      }
    }
    if (Object.keys(change).length > 1) out.push(change);
  }
  return out;
}

// ------------------------------------------------------------------ the edit context
//
// The cells read the draft through this context instead of closing over it, so the column
// definitions stay the same object while a value is typed: a changing `columns` makes the grid
// rebuild its cells and the typist loses the box they were in (browser pass D1).

interface EditApi {
  editing: boolean;
  view: 'standard' | 'party';
  party: CostingParty | null;
  partyId: string;
  asOf: string;
  canManage: boolean;
  removingId: string | null;
  draftOf: (row: CostingRow) => Draft;
  patchDraft: (row: CostingRow, patch: Partial<Draft>) => void;
  figures: (row: CostingRow) => Figures | null;
  openHistory: (row: CostingRow) => void;
  removeFromParty: (row: CostingRow) => void;
}

const EditContext = createContext<EditApi | null>(null);

function useEdit(): EditApi {
  const api = useContext(EditContext);
  if (!api) throw new Error('Costing cells render inside the CostingPage');
  return api;
}

// ------------------------------------------------------------------ cells

function SetMarker() {
  return <span title={SET_ON_ROW} className="ms-1 inline-block size-1.5 shrink-0 rounded-full bg-primary align-middle" />;
}

function Muted({ children }: { children: string }) {
  return <span className="text-muted-foreground">{children}</span>;
}

function TextCell({
  value,
  className,
  title,
}: {
  value: string | null | undefined;
  className?: string;
  title?: string;
}) {
  return value ? (
    <span className={`block truncate ${className ?? ''}`} title={title ?? value}>
      {value}
    </span>
  ) : (
    <Muted>-</Muted>
  );
}

function Num({ children, marker }: { children: string; marker?: boolean }) {
  return (
    <span className="block truncate text-end tabular-nums" title={children}>
      <span>{children}</span>
      {marker ? <SetMarker /> : null}
    </span>
  );
}

/** The reason an unknown figure is unknown, in place of the figure. */
function Reason({ reason }: { reason: CostingReason | undefined }) {
  if (!reason) return <Muted>-</Muted>;
  const text = reasonText(reason);
  return (
    <span className="block truncate text-xs text-muted-foreground" title={text}>
      {text}
    </span>
  );
}

const blockingReason = (row: CostingRow) =>
  row.reasons.find((r) => r.code !== 'no_transport_rule' && r.code !== 'no_list_price');
const noPriceReason = (row: CostingRow) => row.reasons.find((r) => r.code === 'no_list_price');
const transportReason = (row: CostingRow) => row.reasons.find((r) => r.code === 'no_transport_rule');

function EditHint() {
  const { editing } = useEdit();
  return editing ? (
    <span className="block truncate text-2xs font-normal text-muted-foreground">applies to every party</span>
  ) : null;
}

function SupplierPicker({
  row,
  value,
  onChange,
}: {
  row: CostingRow;
  value: string;
  onChange: (v: string) => void;
}) {
  const { partyId, asOf } = useEdit();
  const scope = useMemo(
    () => ({ ...(partyId ? { party_id: partyId } : {}), ...(asOf ? { as_of: asOf } : {}) }),
    [partyId, asOf],
  );
  const { data } = useCostingSuppliers(row.product_id, scope);
  const options = (data?.data ?? []).map((s) => ({
    value: s.supplier_id,
    label: `${s.supplier_code} - ${s.supplier_name}`,
  }));
  return (
    <SearchableSelect
      aria-label={`Supplier for ${row.product_code}`}
      value={value}
      onChange={onChange}
      options={options}
      placeholder="Supplier"
    />
  );
}

function TransportCell({ row }: { row: CostingRow }) {
  const { editing, draftOf, patchDraft } = useEdit();
  if (editing) {
    const d = draftOf(row);
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <SearchableSelect
          aria-label={`Transport for ${row.product_code}`}
          value={d.tMode}
          onChange={(v) => patchDraft(row, { tMode: v })}
          options={MODE_OPTIONS}
          placeholder="Category rule"
          clearable
        />
        <NumberInput
          aria-label={`Transport value for ${row.product_code}`}
          step="any"
          min={0}
          value={d.tValue}
          onChange={(e) => patchDraft(row, { tValue: e.target.value })}
          className="h-8 text-end"
        />
      </div>
    );
  }
  const text = transportText(row.transport_mode, row.transport_value);
  if (!text) return transportReason(row) ? <Reason reason={transportReason(row)} /> : <Muted>-</Muted>;
  return <Num marker={row.transport_source === 'product'}>{text}</Num>;
}

function MethodCell({ row }: { row: CostingRow }) {
  const { editing, draftOf, patchDraft } = useEdit();
  if (editing) {
    const d = draftOf(row);
    return (
      <div className="flex min-w-0 flex-col gap-1">
        <SearchableSelect
          aria-label={`Cost method for ${row.product_code}`}
          value={d.method}
          onChange={(v) => patchDraft(row, { method: v, supplier: v === 'selected' ? d.supplier : '' })}
          options={METHOD_OPTIONS}
          placeholder="Company default"
          clearable
        />
        {d.method === 'selected' ? (
          <SupplierPicker row={row} value={d.supplier} onChange={(v) => patchDraft(row, { supplier: v })} />
        ) : null}
      </div>
    );
  }
  const skipped = row.skipped
    .map((s) => `${s.supplier_code ?? 'A supplier'} (${s.reason === 'no_rate' ? 'no rate' : 'no cost'})`)
    .join(', ');
  return (
    <span
      className="block truncate"
      title={skipped ? `${METHOD_LABEL[row.cost_method]}. Skipped: ${skipped}` : METHOD_LABEL[row.cost_method]}
    >
      <span>{METHOD_LABEL[row.cost_method]}</span>
      {row.cost_method_source === 'product' ? <SetMarker /> : null}
    </span>
  );
}

function MarkupCell({ row }: { row: CostingRow }) {
  const { editing, view, party, draftOf, patchDraft, figures } = useEdit();
  if (editing && view === 'party') {
    return (
      <NumberInput
        aria-label={`Mark-up for ${row.product_code}`}
        step="any"
        min={0}
        value={draftOf(row).markup}
        placeholder={party && party.markup_pct !== null ? money(party.markup_pct) : undefined}
        onChange={(e) => patchDraft(row, { markup: e.target.value })}
        className="h-8 text-end"
      />
    );
  }
  const f = figures(row);
  const markup = f ? f.markup : row.markup_pct;
  if (markup === null) return noPriceReason(row) && view === 'standard' ? <Reason reason={noPriceReason(row)} /> : <Muted>-</Muted>;
  return <Num marker={row.markup_source === 'row'}>{percent(markup)}</Num>;
}

function LandingCell({ row }: { row: CostingRow }) {
  const { figures } = useEdit();
  const f = figures(row);
  const landing = f ? f.landing : row.landing;
  return landing === null ? <Reason reason={blockingReason(row)} /> : <Num>{money(landing)}</Num>;
}

function FinalCell({ row }: { row: CostingRow }) {
  const { figures } = useEdit();
  const f = figures(row);
  const final = f ? f.final : row.final;
  return final === null ? <Muted>-</Muted> : <Num>{money(final)}</Num>;
}

function MarginCell({ row }: { row: CostingRow }) {
  const { figures } = useEdit();
  const f = figures(row);
  const margin = f ? f.margin : row.margin_pct;
  return margin === null ? <Reason reason={noPriceReason(row)} /> : <Num>{percent(margin)}</Num>;
}

function RowMenu({ row }: { row: CostingRow }) {
  const { view, canManage, removingId, openHistory, removeFromParty } = useEdit();
  const canRemove = view === 'party' && canManage && !!row.party_product_id;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button type="button" variant="ghost" mode="icon" size="sm" aria-label={`${row.product_code} actions`}>
          <MoreHorizontal className="size-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onSelect={() => openHistory(row)}>History</DropdownMenuItem>
        {canRemove ? (
          <DropdownMenuItem
            variant="destructive"
            disabled={removingId === row.party_product_id}
            onSelect={() => removeFromParty(row)}
          >
            Remove from party
          </DropdownMenuItem>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function ExpandedSuppliers({ row }: { row: CostingRow }) {
  const { partyId, asOf } = useEdit();
  return <CostingSupplierGrid productId={row.product_id} partyId={partyId || null} asOf={asOf || undefined} />;
}

function Chip({ label, value, onClick }: { label: string; value: string; onClick?: () => void }) {
  const body = (
    <>
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </>
  );
  const cls = 'flex items-center gap-1.5 rounded-md border bg-background px-2.5 py-1 text-xs';
  return onClick ? (
    <button type="button" className={`${cls} hover:bg-accent`} onClick={onClick}>
      {body}
    </button>
  ) : (
    <div className={cls}>{body}</div>
  );
}

function partyMethodText(party: CostingParty, defaultMethod: CostMethod): string {
  return party.cost_method ? METHOD_LABEL[party.cost_method] : `${METHOD_LABEL[defaultMethod]} (company)`;
}

/**
 * The party select's search: the shared server-searched customers select, one line per option,
 * "NAME (CODE)", found by code or name.
 */
async function fetchParties(query: string, pageIndex: number): Promise<SearchableSelectOption[]> {
  const options = await searchCustomersSelect(query, pageIndex);
  return options.map((o) => {
    // The shared option's label is "CODE - NAME".
    const [code, ...rest] = o.label.split(' - ');
    const name = rest.join(' - ') || o.label;
    return { value: o.value, label: `${name} (${code})`, searchText: `${code} ${name}` };
  });
}

const COST_OPTIONS = [
  { value: 'has', label: 'Has cost' },
  { value: 'none', label: 'No cost' },
];

// ------------------------------------------------------------------ the view

/**
 * Products > Costing (AC-CG-01..14): the workbook in the system. One DataGrid of every product's
 * landing cost, with a party picker for a customer's prices, filters in the URL, and Edit / Save
 * in place as Sales > Targets does it (one PATCH of the changed cells). Reading needs
 * `products.cost.view`, editing `products.party_costing.manage`.
 */
export default function CostingView() {
  const canView = useHasPermission('products.cost.view');
  if (!canView) {
    return (
      <>
        <Container>
          <PageHeader title="Costing" />
        </Container>
        <Container>
          <p className="text-sm text-muted-foreground">You do not have access to costing.</p>
        </Container>
      </>
    );
  }
  return <CostingPage />;
}

export { CostingView };

function CostingPage() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const canManage = useHasPermission('products.party_costing.manage');

  const partyId = params.get('party') ?? '';
  const category = params.get('category') ?? '';
  const brand = params.get('brand') ?? '';
  const method = params.get('method') ?? '';
  const cost = params.get('cost') ?? '';
  // Both, or neither, is no narrowing; one is sent to the server.
  const costOne = splitMulti(cost).length === 1 ? splitMulti(cost)[0] : '';
  const asOf = params.get('as_of') ?? '';

  const writeUrl = (next: Record<string, string>) => {
    const sp = new URLSearchParams(params.toString());
    for (const [key, value] of Object.entries(next)) {
      if (value) sp.set(key, value);
      else sp.delete(key);
    }
    const qs = sp.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  const { value: searchText, setValue: setSearchText, debouncedValue: debouncedSearch, isSettling } =
    useDebouncedSearch();
  const [pagination, setPagination] = useState<PaginationState>({ pageIndex: 0, pageSize: 50 });
  const [sorting, setSorting] = useState<SortingState>([]);
  const [expanded, setExpanded] = useState<ExpandedState>({});
  const [editing, setEditing] = useState(false);
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [historyRow, setHistoryRow] = useState<{ id: string; code: string } | null>(null);

  // Margin exists only in the party view: a sort on it never outlives that column.
  const querySorting = sorting.filter((x) => x.id !== 'margin' || !!partyId);
  const sortKey = querySorting[0] ? SERVER_SORT[querySorting[0].id] : undefined;
  const sortDesc = !!querySorting[0]?.desc;
  const rowsParams = useMemo<CostingRowsParams>(
    () => ({
      ...(partyId ? { party_id: partyId } : {}),
      ...(debouncedSearch ? { query: debouncedSearch } : {}),
      ...(category ? { category_id: category } : {}),
      ...(brand ? { brand_id: brand } : {}),
      ...(method ? { cost_method: method } : {}),
      ...(costOne ? { cost: costOne } : {}),
      ...(asOf ? { as_of: asOf } : {}),
      page: pagination.pageIndex + 1,
      limit: pagination.pageSize,
      ...(sortKey ? { sort: sortKey, dir: sortDesc ? ('desc' as const) : ('asc' as const) } : {}),
    }),
    [partyId, debouncedSearch, category, brand, method, costOne, asOf, pagination, sortKey, sortDesc],
  );

  const { data, isLoading, isFetching, isPlaceholderData, isError, error } = useCostingRows(rowsParams);
  const rows = useMemo(() => data?.data ?? [], [data]);
  const total = data?.total ?? 0;
  const view: 'standard' | 'party' = data?.view ?? (partyId ? 'party' : 'standard');
  const party = data?.party ?? null;
  const defaultMethod = (data?.settings.default_method ?? 'primary') as CostMethod;
  const resolvedAsOf = data?.as_of;

  // The party's name from its own read, so the picker is right on first paint and after a rows error.
  const partyRead = useCostingParty(partyId || null);
  const partyShown = party ?? (partyId ? (partyRead.data ?? null) : null);
  const save = useSaveCostingRows();
  const exporter = useExportCosting();
  const categories = useProductCategorySelectQuery();
  const brands = useBrandSelectQuery();
  const removal = useDeferredRowAction({
    actionKey: 'costing_party_product.unlink',
    entityType: 'costing_party_product',
    verb: 'Removing',
    successMessage: 'Removed from the party.',
    invalidateKeys: [[...COSTING_ROWS_KEY], [...COSTING_PARTY_KEY]],
  });

  const filterKey = [partyId, debouncedSearch, category, brand, method, cost, asOf].join('|');
  useEffect(() => {
    setPagination((p) => (p.pageIndex === 0 ? p : { ...p, pageIndex: 0 }));
    setExpanded({});
  }, [filterKey]);
  useEffect(() => {
    if (view !== 'party') setSorting((all) => (all.some((x) => x.id === 'margin') ? all.filter((x) => x.id !== 'margin') : all));
  }, [view]);
  // A different party is a different set of mark-ups: leave edit rather than carry drafts over.
  useEffect(() => {
    setEditing(false);
    setEdits({});
  }, [partyId]);

  const cancelEdit = () => {
    setEditing(false);
    setEdits({});
  };

  const saveEdit = async () => {
    const changes = buildChanges(edits, view);
    if (typeof changes === 'string') {
      toast.error(changes);
      return;
    }
    if (!changes.length) {
      cancelEdit();
      return;
    }
    try {
      await save.mutateAsync({ party_id: partyId || null, changes });
      cancelEdit();
    } catch {
      // The hook toasted the reason; the edit stays open so nothing typed is lost.
    }
  };

  const editApi: EditApi = {
    editing,
    view,
    party,
    partyId,
    asOf,
    canManage,
    removingId: removal.targetId,
    draftOf: (row) => edits[row.product_id]?.cur ?? initialDraft(row),
    patchDraft: (row, patch) =>
      setEdits((all) => {
        const existing = all[row.product_id];
        const base = existing?.base ?? initialDraft(row);
        return { ...all, [row.product_id]: { base, cur: { ...(existing?.cur ?? base), ...patch } } };
      }),
    figures: (row) => {
      if (!editing) return null;
      const d = edits[row.product_id]?.cur ?? initialDraft(row);
      const value = typed(d.tValue);
      // Cleared back from a product override: the category rule applies, or + 0 when it has none.
      const cleared = !d.tMode && d.tValue.trim() === '' && row.transport_source === 'product';
      const fallback =
        row.category_transport_mode && row.category_transport_value != null
          ? { mode: row.category_transport_mode, value: row.category_transport_value }
          : { mode: 'add' as TransportMode, value: 0 };
      const markup = typed(d.markup);
      return figuresFor(
        row,
        {
          transport:
            d.tMode && value !== null && value > 0
              ? { mode: d.tMode as TransportMode, value }
              : cleared
                ? fallback
                : null,
          markup: markup !== null && markup >= 0 ? markup : null,
          inheritedMarkup: party?.markup_pct ?? null,
        },
        view,
      );
    },
    openHistory: (row) => setHistoryRow({ id: row.product_id, code: row.product_code }),
    removeFromParty: (row) =>
      removal.run({
        id: row.party_product_id as string,
        subject: `${row.product_code} from ${party?.customer_name ?? 'the party'}`,
      }),
  };

  // Stable while a value is typed: only the view (Margin or not) changes the columns.
  const columns = useMemo<ColumnDef<CostingRow>[]>(() => {
    const sortable = (
      id: string,
      title: string,
      withHint = false,
    ): Pick<ColumnDef<CostingRow>, 'header' | 'enableSorting'> => ({
      header: ({ column }) =>
        withHint ? (
          <div className="min-w-0">
            <DataGridColumnHeader title={title} column={column} />
            <EditHint />
          </div>
        ) : (
          <DataGridColumnHeader title={title} column={column} />
        ),
      enableSorting: id in SERVER_SORT,
    });

    const cols: ColumnDef<CostingRow>[] = [
      {
        id: 'expand',
        header: () => null,
        cell: ({ row }) => (
          <Button
            type="button"
            variant="ghost"
            mode="icon"
            size="sm"
            aria-label={`${row.getIsExpanded() ? 'Hide' : 'Show'} suppliers for ${row.original.product_code}`}
            onClick={() => row.toggleExpanded()}
          >
            {row.getIsExpanded() ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
          </Button>
        ),
        size: 44,
        enableSorting: false,
        enableHiding: false,
        enableResizing: false,
        meta: { expandedContent: (row: CostingRow) => <ExpandedSuppliers row={row} /> },
      },
      {
        id: 'category',
        accessorFn: (r) => r.category_name,
        ...sortable('category', 'Category'),
        cell: ({ row }) => <TextCell value={row.original.category_name} />,
        size: 130,
        meta: { headerTitle: 'Category', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'code',
        accessorFn: (r) => r.product_code,
        ...sortable('code', 'Code'),
        cell: ({ row }) => <TextCell value={row.original.product_code} className="font-medium" />,
        size: 120,
        meta: { headerTitle: 'Code', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'name',
        accessorFn: (r) => r.product_name,
        ...sortable('name', 'Name'),
        cell: ({ row }) => <TextCell value={row.original.product_name} />,
        size: 200,
        meta: { headerTitle: 'Name', skeleton: <Skeleton className="h-4 w-32" /> },
      },
      {
        id: 'supplier',
        accessorFn: (r) => r.supplier_name?.toLowerCase(),
        ...sortable('supplier', 'Supplier'),
        cell: ({ row }) => (
          <TextCell
            value={row.original.supplier_name ?? row.original.supplier_code}
            title={
              row.original.supplier_name && row.original.supplier_code
                ? `${row.original.supplier_name} (${row.original.supplier_code})`
                : undefined
            }
          />
        ),
        size: 180,
        meta: { headerTitle: 'Supplier', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'cost',
        accessorFn: (r) => r.unit_cost,
        ...sortable('cost', 'Cost'),
        cell: ({ row }) =>
          row.original.unit_cost === null ? (
            <Muted>-</Muted>
          ) : (
            <Num>{`${row.original.currency ?? ''} ${money(row.original.unit_cost)}`.trim()}</Num>
          ),
        size: 110,
        meta: { headerTitle: 'Cost', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'rate',
        accessorFn: (r) => r.units_per_base,
        ...sortable('rate', 'Rate'),
        cell: ({ row }) =>
          row.original.units_per_base === null ? <Muted>-</Muted> : <Num>{trimmed(row.original.units_per_base, 4)}</Num>,
        size: 80,
        meta: { headerTitle: 'Rate', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'sst',
        accessorFn: (r) => r.sst_factor,
        ...sortable('sst', 'SST'),
        cell: ({ row }) => <Num>{money(row.original.sst_factor)}</Num>,
        size: 70,
        meta: { headerTitle: 'SST', skeleton: <Skeleton className="h-4 w-10" /> },
      },
      {
        id: 'transport',
        accessorFn: (r) => (r.transport_mode ? `${r.transport_mode} ${String(r.transport_value ?? 0).padStart(12, '0')}` : null),
        ...sortable('transport', 'Transport', true),
        cell: ({ row }) => <TransportCell row={row.original} />,
        size: 190,
        meta: { headerTitle: 'Transport', skeleton: <Skeleton className="h-4 w-20" /> },
      },
      {
        id: 'landing',
        accessorFn: (r) => r.landing,
        ...sortable('landing', 'Landing (RM)'),
        cell: ({ row }) => <LandingCell row={row.original} />,
        size: 130,
        meta: { headerTitle: 'Landing (RM)', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'method',
        accessorFn: (r) => METHOD_LABEL[r.cost_method],
        ...sortable('method', 'Cost method', true),
        cell: ({ row }) => <MethodCell row={row.original} />,
        size: 200,
        meta: { headerTitle: 'Cost method', skeleton: <Skeleton className="h-4 w-24" /> },
      },
      {
        id: 'markup',
        accessorFn: (r) => r.markup_pct,
        ...sortable('markup', 'Mark-up'),
        cell: ({ row }) => <MarkupCell row={row.original} />,
        size: 120,
        meta: { headerTitle: 'Mark-up', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'final',
        accessorFn: (r) => r.final,
        ...sortable('final', 'Final (RM)'),
        cell: ({ row }) => <FinalCell row={row.original} />,
        size: 120,
        meta: { headerTitle: 'Final (RM)', skeleton: <Skeleton className="h-4 w-16" /> },
      },
      {
        id: 'list_price',
        accessorFn: (r) => (r.list_price === null ? null : r.list_price),
        ...sortable('list_price', 'List price (AutoCount)'),
        cell: ({ row }) =>
          row.original.list_price === null ? <Muted>-</Muted> : <Num>{money(row.original.list_price)}</Num>,
        size: 160,
        meta: { headerTitle: 'List price (AutoCount)', skeleton: <Skeleton className="h-4 w-16" /> },
      },
    ];
    if (view === 'party') {
      cols.push({
        id: 'margin',
        accessorFn: (r) => r.margin_pct,
        ...sortable('margin', 'Margin'),
        cell: ({ row }) => <MarginCell row={row.original} />,
        size: 100,
        meta: { headerTitle: 'Margin', skeleton: <Skeleton className="h-4 w-14" /> },
      });
    }
    cols.push({
      id: 'actions',
      header: () => null,
      cell: ({ row }) => <RowMenu row={row.original} />,
      size: 48,
      enableSorting: false,
      enableHiding: false,
      enableResizing: false,
    });
    return cols;
  }, [view]);

  const table = useReactTable({
    columns,
    data: rows,
    getRowId: (row) => row.product_id,
    pageCount: Math.max(1, Math.ceil(total / pagination.pageSize)),
    state: { pagination, sorting: sorting.filter((x) => x.id !== 'margin' || view === 'party'), expanded },
    manualPagination: true,
    manualSorting: true,
    onPaginationChange: setPagination,
    onSortingChange: setSorting,
    onExpandedChange: setExpanded,
    getRowCanExpand: () => true,
    getCoreRowModel: getCoreRowModel(),
    getExpandedRowModel: getExpandedRowModel(),
    columnResizeMode: 'onChange',
    enableColumnResizing: true,
  });

  const categoryOptions = (categories.data ?? []).map((c) => ({ value: c.id, label: c.category_name }));
  const brandOptions = (brands.data ?? []).map((b) => ({ value: b.id, label: b.brand_name }));
  // One chip per active filter, each with its own clear (the list pages' activeSummary).
  const chip = (title: string, key: string, raw: string, name: (v: string) => string) => {
    const values = splitMulti(raw);
    return values.length ? [{ label: multiChipLabel(title, values.map(name)), onClear: () => writeUrl({ [key]: '' }) }] : [];
  };
  const activeChips = [
    ...chip('Category', 'category', category, (v) => categoryOptions.find((o) => o.value === v)?.label ?? 'selected'),
    ...chip('Brand', 'brand', brand, (v) => brandOptions.find((o) => o.value === v)?.label ?? 'selected'),
    ...chip('Cost method', 'method', method, (v) => METHOD_LABEL[v as CostMethod] ?? v),
    ...(costOne ? chip('Cost', 'cost', costOne, (v) => COST_OPTIONS.find((o) => o.value === v)?.label ?? v) : []),
  ];
  const exportParams: CostingRowsParams = { ...rowsParams, page: undefined, limit: undefined };

  const secondaryActions: ToolbarAction[] = [
    {
      key: 'export',
      label: 'Export',
      icon: Download,
      onClick: () => exporter.mutate(exportParams),
      disabled: exporter.isPending,
    },
    ...(view === 'party' && canManage && party?.has_profile
      ? [{ key: 'add-products', label: 'Add products', icon: ListPlus, onClick: () => setAddOpen(true) }]
      : []),
  ];

  const emptyMessage = debouncedSearch
    ? 'Nothing matches this search.'
    : party && !party.has_profile
      ? 'This party has no costing profile yet'
      : party
        ? 'No products on this party yet'
        : 'No products';

  const headerActions = (
    <>
      <Button variant="outline" onClick={() => setSettingsOpen(true)}>
        <Settings className="size-4" />
        Settings
      </Button>
      {canManage && party && !party.has_profile ? (
        <Button variant="outline" onClick={() => setProfileOpen(true)}>
          Set up costing
        </Button>
      ) : null}
      {canManage ? (
        editing ? (
          <>
            <Button variant="outline" onClick={cancelEdit} disabled={save.isPending}>
              Cancel
            </Button>
            <Button variant="primary" onClick={() => void saveEdit()} disabled={save.isPending}>
              {save.isPending ? <LoaderCircleIcon className="size-4 animate-spin" /> : null}
              Save
            </Button>
          </>
        ) : (
          <Button variant="primary" onClick={() => setEditing(true)} disabled={!rows.length}>
            <Pencil className="size-4" />
            Edit
          </Button>
        )
      ) : null}
    </>
  );

  return (
    <EditContext.Provider value={editApi}>
      <Container>
        <PageHeader title="Costing" actions={headerActions} />
      </Container>
      <Container>
        <div className="space-y-4">
          {party ? (
            <div className="flex flex-wrap items-center gap-2">
              <Chip
                label="Party mark-up"
                value={party.markup_pct === null ? 'Not set' : percent(party.markup_pct)}
                onClick={canManage ? () => setProfileOpen(true) : undefined}
              />
              <Chip
                label="Cost method"
                value={partyMethodText(party, defaultMethod)}
                onClick={canManage ? () => setProfileOpen(true) : undefined}
              />
              <Chip label="Rates as of" value={shortDate(resolvedAsOf)} />
              <Chip label="Products" value={String(party.product_count)} />
            </div>
          ) : null}
          <DataGrid
            table={table}
            recordCount={total}
            isLoading={isLoading}
            isPlaceholderData={isPlaceholderData}
            listingKey="products.cost.view::costing"
            standardToolbar={false}
            tableLayout={{ width: 'fixed', columnsResizable: true, columnsVisibility: true }}
            emptyMessage={emptyMessage}
          >
            <Card>
              <CardHeader className="block">
                {/* Keyed by view: the toolbar memoises the grid's columns on the table object, which
                    never changes, so a Margin that has gone would stay in its lists. */}
                <DataGridListToolbar
                  key={view}
                  table={table}
                  searchSlot={
                    <div
                      data-testid="costing-search-slot"
                      className="flex w-full flex-wrap items-center gap-2 sm:w-auto sm:flex-nowrap"
                    >
                      <div className="w-full sm:w-56">
                        <SearchableSelect
                          id="costing-party"
                          aria-label="Party"
                          value={partyId}
                          onChange={(v) => writeUrl({ party: v })}
                          fetchOptions={fetchParties}
                          paginated
                          clearable
                          truncateTriggerLabel
                          placeholder="Company standard"
                          selectedOption={
                            partyShown
                              ? { value: partyId, label: `${partyShown.customer_name} (${partyShown.customer_code})` }
                              : undefined
                          }
                        />
                      </div>
                      <DatePicker
                        ariaLabel="As of"
                        className="w-full gap-1 sm:w-40"
                        value={parseDateInput(asOf || resolvedAsOf || '')}
                        onChange={(d) => writeUrl({ as_of: d ? formatLocalDateToYyyyMmDd(d) : '' })}
                      />
                      <ListSearchInput
                        value={searchText}
                        onChange={setSearchText}
                        isSettling={isSearchInFlight(isSettling, isFetching, debouncedSearch)}
                        placeholder="Search code or name"
                        className="w-full sm:w-48"
                      />
                    </div>
                  }
                  filters={{
                    kind: 'custom',
                    active: activeChips.length > 0,
                    activeCount: activeChips.length,
                    activeSummary: activeChips,
                    content: (
                      <div className="space-y-4">
                        <div>
                          <Label htmlFor="costing-filter-category">Category</Label>
                          <SearchableMultiSelect
                            id="costing-filter-category"
                            value={splitMulti(category)}
                            onChange={(v) => writeUrl({ category: joinMulti(v) })}
                            options={categoryOptions}
                            placeholder="All categories"
                            loadError={categories.error}
                            onRetry={() => void categories.refetch()}
                            triggerClassName="mt-1"
                            clearable
                          />
                        </div>
                        <div>
                          <Label htmlFor="costing-filter-brand">Brand</Label>
                          <SearchableMultiSelect
                            id="costing-filter-brand"
                            value={splitMulti(brand)}
                            onChange={(v) => writeUrl({ brand: joinMulti(v) })}
                            options={brandOptions}
                            placeholder="All brands"
                            loadError={brands.error}
                            onRetry={() => void brands.refetch()}
                            triggerClassName="mt-1"
                            clearable
                          />
                        </div>
                        <div>
                          <Label htmlFor="costing-filter-method">Cost method</Label>
                          <SearchableMultiSelect
                            id="costing-filter-method"
                            value={splitMulti(method)}
                            onChange={(v) => writeUrl({ method: joinMulti(v) })}
                            options={METHOD_OPTIONS}
                            placeholder="All cost methods"
                            triggerClassName="mt-1"
                            clearable
                          />
                        </div>
                        <div>
                          <Label htmlFor="costing-filter-cost">Cost</Label>
                          <SearchableMultiSelect
                            id="costing-filter-cost"
                            value={splitMulti(cost)}
                            onChange={(v) => writeUrl({ cost: joinMulti(v) })}
                            options={COST_OPTIONS}
                            placeholder="All rows"
                            triggerClassName="mt-1"
                            clearable
                          />
                        </div>
                      </div>
                    ),
                  }}
                  exportConfig={false}
                  secondaryActions={secondaryActions}
                />
              </CardHeader>
              {isError ? (
                <div className="px-5 pb-2 text-sm text-destructive">
                  {error instanceof Error ? error.message : 'Failed to load costing.'}
                </div>
              ) : null}
              <CardTable>
                <DataGridTable />
              </CardTable>
              <CardFooter>
                <DataGridPagination />
              </CardFooter>
            </Card>
          </DataGrid>
        </div>
      </Container>
      <CostingSettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
      <CostingHistoryDialog
        open={!!historyRow}
        onOpenChange={(open) => !open && setHistoryRow(null)}
        productId={historyRow?.id ?? null}
        productCode={historyRow?.code ?? ''}
        partyId={partyId || null}
      />
      {party ? <PartyProfileDialog open={profileOpen} onOpenChange={setProfileOpen} party={party} /> : null}
      {party && partyId ? (
        <AddCostingProductsDialog
          open={addOpen}
          onOpenChange={setAddOpen}
          customerId={partyId}
          partyName={party.customer_name}
        />
      ) : null}
    </EditContext.Provider>
  );
}
