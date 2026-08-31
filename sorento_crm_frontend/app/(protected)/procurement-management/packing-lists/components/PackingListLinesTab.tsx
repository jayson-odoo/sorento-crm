'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Info,
  Trash2,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Table,
  TableBody,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { formatDate } from '@/lib/helpers';
import { formatStatusLabel } from '@/lib/status-badge';
import { getProducts } from '@/app/(protected)/master-data-management/products/services/productService';
import { ProductComboboxSearchable } from './ProductComboboxSearchable';
import { SupplierCombobox } from './SupplierCombobox';
import {
  usePackingListRecord,
  type DraftLine,
} from '../[id]/components/packing-list-context';

type SortField =
  | 'product'
  | 'quantity_shipped'
  | 'spo_allocated'
  | 'quantity_received'
  | 'status';

/** A Numeric column arrives as a string on the wire; anything unreadable is "not stated". */
function toNumber(value: number | string | null | undefined): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/** Volume as a person writes it: `3.4`, not `3.4000`, and "-" when nobody measured it. */
function fmtCbm(value: number | string | null | undefined): string {
  const parsed = toNumber(value);
  if (parsed === null) return '-';
  return String(Number(parsed.toFixed(3)));
}

/** A measurement as the supplier stated it, or "-" when they stated none. Never 0: an
 *  unmeasured carton and a carton of no size are different facts. */
function fmtNum(value: number | string | null | undefined): string {
  const parsed = toNumber(value);
  return parsed === null ? '-' : String(parsed);
}

/** Line-level status from quantity shipped, allocated, and received. */
function getLineStatus(quantityShipped: number, allocated: number, received: number): string {
  const qty = quantityShipped ?? 0;
  const alloc = allocated ?? 0;
  const recv = received ?? 0;
  if (alloc === 0) return 'in_transit';
  if (recv >= alloc) return 'received';
  if (qty > alloc) return 'partially_allocated';
  if (alloc >= qty && recv === 0) return 'allocated';
  if (alloc >= qty && recv > 0) return 'partially_received';
  return 'in_transit';
}

/** A numeric cell in the editor. One component so every measurement column looks the same. */
function LineNumberInput({
  line,
  name,
  label,
  step,
  onChange,
}: {
  line: DraftLine;
  name: keyof DraftLine;
  label: string;
  step?: string;
  onChange: (key: string, name: keyof DraftLine, value: string) => void;
}) {
  return (
    <Input
      type="number"
      min={0}
      step={step}
      className="h-8 w-20 text-end tabular-nums"
      value={(line[name] as string) ?? ''}
      onChange={(e) => onChange(line.key, name, e.target.value)}
      aria-label={`${label} for ${line.product_code || 'the new line'}`}
    />
  );
}

/**
 * What is in the container, and what the workbook measures it by.
 *
 * The measurement columns (material, pcs per carton, the carton's L / W / H, NW, GW) are
 * editable here because the supplier's own file is where they come from and it is not
 * always right - and because everything the container workbook derives is derived from
 * them. Draft until Save, like every other field on this record.
 */
export function PackingListLinesTab() {
  const {
    packingList,
    editing,
    draftLines,
    setLineField,
    addLine,
    removeLine,
    suppliers,
    supplierNameById,
    sourceInvoices,
  } = usePackingListRecord();

  const {
    value: searchInput,
    setValue: setSearchInput,
    debouncedValue: search,
  } = useDebouncedSearch();
  const [sortField, setSortField] = useState<SortField>('product');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');

  const invoicesByLine = sourceInvoices?.by_shipment_line ?? {};

  const sortedAndFilteredLines = useMemo(() => {
    if (!packingList?.shipment_lines) return [];
    const q = search.trim().toLowerCase();
    const filtered = packingList.shipment_lines.filter((line) => {
      if (!q) return true;
      const code = line.product?.product_code?.toLowerCase() ?? '';
      const name = line.product?.product_name?.toLowerCase() ?? '';
      return code.includes(q) || name.includes(q);
    });

    return [...filtered].sort((a, b) => {
      let aVal: string | number;
      let bVal: string | number;
      switch (sortField) {
        case 'product':
          aVal = a.product?.product_code?.toLowerCase() ?? '';
          bVal = b.product?.product_code?.toLowerCase() ?? '';
          break;
        case 'quantity_shipped':
          aVal = a.quantity_shipped ?? 0;
          bVal = b.quantity_shipped ?? 0;
          break;
        case 'spo_allocated':
          aVal = a.spo_allocated_quantity ?? 0;
          bVal = b.spo_allocated_quantity ?? 0;
          break;
        case 'quantity_received':
          aVal = a.quantity_received ?? 0;
          bVal = b.quantity_received ?? 0;
          break;
        case 'status':
          aVal =
            a.line_status ??
            getLineStatus(
              a.quantity_shipped ?? 0,
              a.spo_allocated_quantity ?? 0,
              a.quantity_received ?? 0,
            );
          bVal =
            b.line_status ??
            getLineStatus(
              b.quantity_shipped ?? 0,
              b.spo_allocated_quantity ?? 0,
              b.quantity_received ?? 0,
            );
          break;
        default:
          return 0;
      }
      if (typeof aVal === 'string' && typeof bVal === 'string') {
        return sortDirection === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }
      return sortDirection === 'asc'
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });
  }, [packingList?.shipment_lines, search, sortField, sortDirection]);

  /**
   * What the rows on screen add up to. The VISIBLE rows, deliberately: a footer under a
   * searched table that quietly totals the whole container reads as the search having
   * found more than it did.
   *
   * `unmeasured` is counted rather than folded into the volume, because a total of 41 cbm
   * computed from half the lines is not 41 cbm, and a container planned on it arrives too
   * full to close.
   */
  const lineTotals = useMemo(() => {
    // While editing, the totals follow the DRAFT - a footer that keeps showing the saved
    // figures under quantities somebody is changing reads as the edit not working.
    const rows = editing
      ? draftLines.map((l) => ({
          quantity_shipped: Number(l.quantity_shipped || 0),
          cartons_count: l.cartons_count === '' ? null : Number(l.cartons_count),
          cbm: l.cbm === '' ? null : l.cbm,
        }))
      : sortedAndFilteredLines;
    let qty = 0;
    let cartons = 0;
    let cbm = 0;
    let unmeasured = 0;
    for (const line of rows) {
      qty += line.quantity_shipped ?? 0;
      cartons += line.cartons_count ?? 0;
      const volume = toNumber(line.cbm);
      if (volume === null) unmeasured += 1;
      else cbm += volume;
    }
    return { qty, cartons, cbm: cbm === 0 && unmeasured > 0 ? null : cbm, unmeasured };
  }, [sortedAndFilteredLines, editing, draftLines]);

  if (!packingList) return null;

  /** Server-searched, so any of the 10k+ products is reachable rather than a first page. */
  const fetchProducts = async (query: string, pageIndex: number) => {
    const res = await getProducts({
      pageIndex,
      pageSize: 50,
      sorting: [],
      searchQuery: query,
      status: 'active',
    });
    return { data: res.data ?? [] };
  };

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const SortIcon = ({ field }: { field: SortField }) => {
    if (sortField !== field) {
      return <ArrowUpDown className="size-4 ml-1 text-muted-foreground" />;
    }
    return sortDirection === 'asc' ? (
      <ArrowUp className="size-4 ml-1" />
    ) : (
      <ArrowDown className="size-4 ml-1" />
    );
  };

  const SortableHead = ({ field, children }: { field: SortField; children: string }) => (
    <TableHead>
      <button
        onClick={() => handleSort(field)}
        className="flex items-center hover:text-foreground transition-colors"
      >
        {children}
        <SortIcon field={field} />
      </button>
    </TableHead>
  );

  const lineSupplierName = (supplierId?: string | null): string | null =>
    (supplierId ? supplierNameById.get(supplierId) : null) ?? null;

  // In edit mode the table is always rendered, even with no lines yet: the empty state is
  // where somebody would go to ADD the first one, and a card with no table in it has
  // nowhere to put it.
  const hasLines = (packingList.shipment_lines?.length ?? 0) > 0;
  if (!editing && !hasLines) {
    return (
      <Card>
        <CardContent className="py-10 text-center">
          <p className="text-sm font-medium">No shipment lines</p>
          <p className="mt-1 text-sm text-muted-foreground">
            This packing list has no product lines yet. They arrive with the packing list
            import, or can be added by editing the packing list.
          </p>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        {/* "Shipment Lines" plus a 224px search box does not fit the 286px of card content
            at 375px, so the header wraps rather than pushing the page into scroll. */}
        <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="min-w-0 break-words">Shipment Lines</CardTitle>
          <ListSearchInput
            value={searchInput}
            onChange={setSearchInput}
            placeholder="Search by product code"
            className="w-full sm:w-56"
          />
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <SortableHead field="product">Product</SortableHead>
                  {/* Whose line this is. Not sortable: the lines arrive grouped by the
                      packing list they were read from, and re-ordering them loses that. */}
                  <TableHead>Supplier</TableHead>
                  <SortableHead field="quantity_shipped">Quantity Shipped</SortableHead>
                  {/* What the container workbook measures the line by. Read off the
                      supplier's file, corrected here. */}
                  <TableHead>Material</TableHead>
                  <TableHead className="text-end">Pcs/ctn</TableHead>
                  <TableHead className="text-end">Cartons</TableHead>
                  <TableHead className="text-end">L</TableHead>
                  <TableHead className="text-end">W</TableHead>
                  <TableHead className="text-end">H</TableHead>
                  <TableHead className="text-end">NW</TableHead>
                  <TableHead className="text-end">GW</TableHead>
                  <TableHead className="text-end">CBM</TableHead>
                  {/* Which document charged these goods. Empty on a line that came off a
                      real packing list rather than a proforma invoice. */}
                  <TableHead>From PI</TableHead>
                  <SortableHead field="spo_allocated">SPO Allocated</SortableHead>
                  <SortableHead field="quantity_received">Received Quantity</SortableHead>
                  <SortableHead field="status">Status</SortableHead>
                  {/* An action has no read-only counterpart, so this column exists only
                      while editing - the fields themselves do not move. */}
                  {editing ? <TableHead /> : null}
                </TableRow>
              </TableHeader>
              {editing ? (
                <TableBody>
                  {draftLines.map((line) => (
                    <TableRow key={line.key}>
                      <TableCell>
                        {line.id ? (
                          <span className="font-medium">{line.product_code || '-'}</span>
                        ) : (
                          <ProductComboboxSearchable
                            className="w-56"
                            value={line.product_id}
                            onChange={(v) => setLineField(line.key, 'product_id', v)}
                            fetchProducts={fetchProducts}
                            placeholder="Search a product"
                          />
                        )}
                      </TableCell>
                      <TableCell>
                        <SupplierCombobox
                          className="w-48"
                          value={line.supplier_id}
                          onChange={(v) => setLineField(line.key, 'supplier_id', v)}
                          suppliers={suppliers}
                          placeholder="No factory named"
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="quantity_shipped"
                          label="Quantity"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <Input
                          className="h-8 w-32"
                          value={line.material}
                          onChange={(e) =>
                            setLineField(line.key, 'material', e.target.value)
                          }
                          aria-label={`Material for ${line.product_code || 'the new line'}`}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="pcs_per_carton"
                          label="Pcs per carton"
                          step="0.0001"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="cartons_count"
                          label="Cartons"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="carton_length_cm"
                          label="Carton length"
                          step="0.01"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="carton_width_cm"
                          label="Carton width"
                          step="0.01"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="carton_height_cm"
                          label="Carton height"
                          step="0.01"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="net_weight_per_carton"
                          label="Net weight"
                          step="0.001"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="gross_weight_per_carton"
                          label="Gross weight"
                          step="0.001"
                          onChange={setLineField}
                        />
                      </TableCell>
                      <TableCell>
                        <LineNumberInput
                          line={line}
                          name="cbm"
                          label="CBM"
                          step="0.001"
                          onChange={setLineField}
                        />
                      </TableCell>
                      {/* No input counterparts: these are what the container did, not what
                          somebody types about it. */}
                      <TableCell className="text-muted-foreground">-</TableCell>
                      <TableCell className="text-muted-foreground">-</TableCell>
                      <TableCell className="text-muted-foreground">-</TableCell>
                      <TableCell className="text-muted-foreground">-</TableCell>
                      <TableCell className="text-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-8 gap-1 px-2 text-xs text-destructive hover:text-destructive"
                          // Nothing is confirmed and nothing is deferred (D7):
                          // the line leaves the DRAFT, and Save is what sends it,
                          // so until then there is nothing to take back.
                          onClick={() => removeLine(line.key)}
                        >
                          <Trash2 className="size-3.5" />
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  <TableRow>
                    <TableCell colSpan={17}>
                      <Button variant="outline" size="sm" onClick={addLine}>
                        Add line
                      </Button>
                    </TableCell>
                  </TableRow>
                </TableBody>
              ) : (
                <TableBody>
                  {sortedAndFilteredLines.map((line) => {
                    const lineStatus =
                      line.line_status ??
                      getLineStatus(
                        line.quantity_shipped ?? 0,
                        line.spo_allocated_quantity ?? 0,
                        line.quantity_received ?? 0,
                      );
                    return (
                      <TableRow key={line.id}>
                        <TableCell>
                          {line.product?.id ? (
                            <Link
                              href={`/master-data-management/products/${line.product.id}`}
                              className="font-medium text-primary hover:underline"
                            >
                              {line.product.product_code}
                            </Link>
                          ) : (
                            line.product?.product_code || '-'
                          )}
                        </TableCell>
                        <TableCell>
                          <span
                            className="block max-w-[180px] truncate"
                            title={lineSupplierName(line.supplier_id) ?? undefined}
                          >
                            {lineSupplierName(line.supplier_id) ?? '-'}
                          </span>
                        </TableCell>
                        <TableCell>{line.quantity_shipped}</TableCell>
                        <TableCell>
                          <span
                            className="block max-w-[140px] truncate"
                            title={line.material ?? undefined}
                          >
                            {line.material || '-'}
                          </span>
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {fmtNum(line.pcs_per_carton)}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {line.cartons_count ?? '-'}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {fmtNum(line.carton_length_cm)}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {fmtNum(line.carton_width_cm)}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {fmtNum(line.carton_height_cm)}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {fmtNum(line.net_weight_per_carton)}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {/* The old single weight is read as the gross one where the new
                              column is empty - it is the only weight most containers hold. */}
                          {fmtNum(line.gross_weight_per_carton ?? line.weight_per_carton)}
                        </TableCell>
                        <TableCell className="text-end tabular-nums">
                          {/* Null reads "-", never 0: a line nobody measured and a line
                              that takes no room are different facts. */}
                          {fmtCbm(line.cbm)}
                        </TableCell>
                        <TableCell>
                          {(invoicesByLine[line.id] ?? []).length === 0 ? (
                            <span className="text-muted-foreground">-</span>
                          ) : (
                            <div className="flex flex-col gap-0.5">
                              {invoicesByLine[line.id].map((src, i) => (
                                <Link
                                  // The position too: ONE invoice can charge the same
                                  // shipment line twice (two PI lines of the same PI
                                  // consolidated into one container line), and the pair
                                  // (invoice, line) then repeats - a duplicate React key,
                                  // which drops the second link from the render.
                                  key={`${src.proforma_invoice_id}-${line.id}-${i}`}
                                  href={`/scm/proforma-invoices/${src.proforma_invoice_id}`}
                                  className="text-primary hover:underline"
                                >
                                  {src.pi_number}
                                  <span className="ms-1 text-xs text-muted-foreground">
                                    {src.qty}
                                  </span>
                                </Link>
                              ))}
                            </div>
                          )}
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span>
                              {line.spo_allocated_quantity != null
                                ? line.spo_allocated_quantity
                                : '-'}
                            </span>
                            {line.related_spo_allocations?.length ? (
                              <Popover>
                                <PopoverTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-6 text-muted-foreground hover:text-foreground"
                                    aria-label={`View related SPO for ${line.product?.product_code || 'this line'}`}
                                  >
                                    <Info className="size-4" />
                                  </Button>
                                </PopoverTrigger>
                                <PopoverContent align="start" className="w-80 space-y-4 p-4">
                                  <div className="space-y-1">
                                    <p className="text-sm font-medium">
                                      {line.product?.product_code || 'Related SPO'}
                                    </p>
                                  </div>
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      Related SPO
                                    </p>
                                    <div className="space-y-2">
                                      {line.related_spo_allocations.map((spo) => (
                                        <Link
                                          key={spo.id}
                                          href={`/procurement-management/spo-allocations/${spo.id}`}
                                          className="block rounded-md border px-3 py-2 hover:bg-muted/50"
                                        >
                                          <div className="flex items-center justify-between gap-2">
                                            <span className="text-sm font-medium text-primary">
                                              {spo.spo_number || 'SPO Allocation'}
                                            </span>
                                            {spo.receipt_status ? (
                                              <Badge
                                                status={spo.receipt_status}
                                                className="shrink-0"
                                              >
                                                {formatStatusLabel(spo.receipt_status)}
                                              </Badge>
                                            ) : null}
                                          </div>
                                          {spo.allocated_quantity != null ? (
                                            <p className="mt-1 text-xs text-muted-foreground">
                                              Allocated: {spo.allocated_quantity}
                                            </p>
                                          ) : null}
                                        </Link>
                                      ))}
                                    </div>
                                  </div>
                                </PopoverContent>
                              </Popover>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <div className="flex items-center gap-2">
                            <span>
                              {line.quantity_received != null ? line.quantity_received : '-'}
                            </span>
                            {line.related_grns?.length ? (
                              <Popover>
                                <PopoverTrigger asChild>
                                  <Button
                                    variant="ghost"
                                    size="icon"
                                    className="size-6 text-muted-foreground hover:text-foreground"
                                    aria-label={`View related GRN for ${line.product?.product_code || 'this line'}`}
                                  >
                                    <Info className="size-4" />
                                  </Button>
                                </PopoverTrigger>
                                <PopoverContent align="start" className="w-80 space-y-4 p-4">
                                  <div className="space-y-1">
                                    <p className="text-sm font-medium">
                                      {line.product?.product_code || 'Related GRN'}
                                    </p>
                                  </div>
                                  <div className="space-y-2">
                                    <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                                      Related GRN
                                    </p>
                                    <div className="space-y-2">
                                      {line.related_grns.map((grn) => (
                                        <Link
                                          key={grn.id}
                                          href={`/procurement-management/grn/${grn.id}`}
                                          className="block rounded-md border px-3 py-2 hover:bg-muted/50"
                                        >
                                          <div className="flex items-center justify-between gap-2">
                                            <span className="text-sm font-medium text-primary">
                                              {grn.picking_number || 'GRN'}
                                            </span>
                                            {grn.picking_status ? (
                                              <Badge
                                                status={grn.picking_status}
                                                className="shrink-0"
                                              >
                                                {formatStatusLabel(grn.picking_status)}
                                              </Badge>
                                            ) : null}
                                          </div>
                                          <p className="mt-1 text-xs text-muted-foreground">
                                            {grn.spo_number || 'No SPO'}
                                            {grn.picking_date
                                              ? ` • ${formatDate(new Date(grn.picking_date))}`
                                              : ''}
                                          </p>
                                        </Link>
                                      ))}
                                    </div>
                                  </div>
                                </PopoverContent>
                              </Popover>
                            ) : null}
                          </div>
                        </TableCell>
                        <TableCell>
                          <Badge status={lineStatus}>
                            {formatStatusLabel(lineStatus)}
                          </Badge>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              )}
              {/* The total is what the container is judged against, so it sits under the
                  column rather than being added up by hand. */}
              <TableFooter>
                <TableRow>
                  <TableCell colSpan={2}>Total</TableCell>
                  <TableCell className="text-end tabular-nums">{lineTotals.qty}</TableCell>
                  <TableCell colSpan={2} />
                  <TableCell className="text-end tabular-nums">{lineTotals.cartons}</TableCell>
                  <TableCell colSpan={5} />
                  <TableCell className="text-end tabular-nums">
                    {fmtCbm(lineTotals.cbm)}
                    {lineTotals.unmeasured > 0 ? (
                      <span className="ms-1 text-xs font-normal text-muted-foreground">
                        ({lineTotals.unmeasured} unmeasured)
                      </span>
                    ) : null}
                  </TableCell>
                  <TableCell colSpan={editing ? 5 : 4} />
                </TableRow>
              </TableFooter>
            </Table>
          </div>
        </CardContent>
      </Card>
    </>
  );
}

export default PackingListLinesTab;
