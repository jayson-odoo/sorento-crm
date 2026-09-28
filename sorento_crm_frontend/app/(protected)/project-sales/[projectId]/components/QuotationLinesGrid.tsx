'use client';

import * as React from 'react';
import type { ColumnDef, ExpandedState } from '@tanstack/react-table';
import {
  AlertTriangle,
  Plus,
  SquarePen,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { DataGridColumnHeader } from '@/components/ui/data-grid-column-header';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { PanelDataGrid } from '@/components/common/PanelDataGrid';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';
import { useUOMSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { getProductsForLineSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import type { ProductLineRef } from '@/app/(protected)/master-data-management/products/types/product.types';
import {
  useLineVerdict,
  useSeriesProductRows,
} from '../../_shared/hooks/useProjects';
import {
  INLINE_CHECKED,
  isInlineChecked,
  type InlineDraft,
} from '../../_shared/components/InlineLineTable';
import type {
  QuotationLine,
  QuotationLineVerdict,
  UnitType,
} from '../../_shared/types/project.types';
import {
  formLinesTotal,
  lineErrors,
  newFormLine,
  type QuotationFormLine,
} from '../../_shared/lib/quotationLineDraft';
import {
  formatMyrExact,
  isDecimalString,
  multiplyMoney,
} from '../../_shared/lib/money';
import { QuotationLinePhoto } from './QuotationLinePhoto';

const FLOOR_LEVEL_LABELS: Record<string, string> = {
  product: 'this product',
  category: 'its category',
  category_ancestor: 'a parent category',
  system: 'the company default',
};

export const UNIT_TYPE_OPTIONS: {
  value: UnitType;
  label: string;
  description: string;
}[] = [
  {
    value: 'house_unit',
    label: 'Per house unit',
    description: 'Multiplied by the unit count',
  },
  {
    value: 'bathroom',
    label: 'Per bathroom',
    description: 'Multiplied by bathrooms per unit',
  },
  { value: 'facility', label: 'Per facility', description: 'Gym, pool, surau' },
  {
    value: 'common_area',
    label: 'Common area',
    description: 'Priced once for the whole site',
  },
];

/** Quantities come back as "2.00"; nobody writes two bathrooms as 2.00. */
function trimAmount(value: string): string {
  const amount = Number(value);
  if (!value || Number.isNaN(amount)) return value;
  return String(amount);
}

function Dash() {
  return <span className="text-muted-foreground">-</span>;
}

function TextCell({ value, align }: { value: string; align?: 'end' }) {
  if (!value) return <Dash />;
  return (
    <span
      className={`block truncate text-sm ${align === 'end' ? 'text-end tabular-nums' : ''}`}
      title={value}
    >
      {value}
    </span>
  );
}

/**
 * The lines of one scope, in the system DataGrid (#1341).
 *
 * The owner: "this table needs to be datagrid". So this is `PanelDataGrid`, the same component
 * the project's Quotations list uses: fixed layout, resizable columns, column order from the
 * listing preferences, the pagination bar and the search box. A section heading is a band row
 * drawn by the grid's own `renderGroupHeader`, carried by the line that opens it.
 *
 * READ when `onChange` is absent: plain cells, nothing to press. With `onChange` the grid is the
 * form page's line editor: Add a line and Add a section in the toolbar, and a per-row Edit that
 * opens the row's editor in place under it (the grid's `expandedContent`), with a Remove there.
 * It writes NOTHING: every change hands the whole set back, and the page's one Save sends it.
 *
 * The item number is the line's position in the WHOLE scope, not in the filtered view, so a
 * search never turns "item 12" into "item 3"; the footer sums the whole scope for the same reason.
 */
export function QuotationLinesGrid({
  lines,
  onChange,
  quotationId,
  seriesId,
  listingKey = 'projects.projects.view::project-quotation-lines',
  title,
}: {
  lines: QuotationFormLine[];
  /** Present means editable. Receives the whole set, in display order, on every change. */
  onChange?: (lines: QuotationFormLine[]) => void;
  /** The saved scope, for the live below-floor and non-standard verdicts. Null on a new scope. */
  quotationId?: string | null;
  /** The scope's series, whose agreed price a picked product opens at. */
  seriesId?: string | null;
  listingKey?: string;
  title?: React.ReactNode;
}) {
  const editable = Boolean(onChange);
  const [expanded, setExpanded] = React.useState<ExpandedState>({});
  const [focusBandKey, setFocusBandKey] = React.useState<string | null>(null);
  const [focusRowId, setFocusRowId] = React.useState<string | null>(null);

  // Read through a ref so the column set keeps its identity while lines change: the grid
  // renders a cell function as a component, and a new identity per keystroke would remount
  // every cell of the table.
  const linesRef = React.useRef(lines);
  linesRef.current = lines;
  const onChangeRef = React.useRef(onChange);
  onChangeRef.current = onChange;

  // Through a ref too, for the same reason: the item number is read at render time, so the
  // columns do not have to be rebuilt for it.
  const indexByKey = React.useRef(new Map<string, number>());
  indexByKey.current = new Map(lines.map((line, index) => [line.key, index]));

  const uoms = useUOMSelectQuery();
  const uomOptions = React.useMemo<SearchableSelectOption[]>(
    () =>
      (uoms.data ?? []).map((unit) => ({
        value: unit.uom_code,
        label: unit.uom_code,
        description: unit.uom_name,
      })),
    [uoms.data],
  );
  const brands = useBrandSelectQuery();

  /**
   * The products the picker has shown, by id. The dropdown already holds the whole record when
   * somebody chooses one, so the fill reads it from here instead of asking the server again, and
   * the Product cell names a just-picked product before anything is saved.
   */
  const [picked, setPicked] = React.useState<Map<string, ProductLineRef>>(
    () => new Map(),
  );
  const productsById = React.useRef(new Map<string, ProductLineRef>());
  const fetchProducts = React.useCallback(async (query: string) => {
    const products = await getProductsForLineSelect(query || undefined);
    products.forEach((product) =>
      productsById.current.set(product.id, product),
    );
    return products.map((product) => ({
      value: product.id,
      label: product.product_code,
      description: product.product_name,
    }));
  }, []);

  const seriesRows = useSeriesProductRows(seriesId ?? undefined);
  const seriesPriceByProduct = React.useMemo(() => {
    const map = new Map<string, string>();
    (seriesRows.data ?? []).forEach((row) => {
      if (row.selling_price) map.set(row.product_id, row.selling_price);
    });
    return map;
  }, [seriesRows.data]);

  /**
   * What picking a product decides for the rest of its line: the description, brand, unit and
   * list price are the product's, so a line quoting SRT-WC-01 reads the same whoever typed it.
   * The unit price opens at the SERIES price where the scope's series names the product; where it
   * says nothing, the typed price is left alone. Tech spec is never filled: the product has none.
   */
  const fillFromProduct = React.useCallback(
    (productId: string): InlineDraft => {
      const product = productsById.current.get(productId);
      if (!product) return { product_id: productId };
      setPicked((previous) => new Map(previous).set(productId, product));
      const brand = (brands.data ?? []).find(
        (row) => row.id === product.brand_id,
      );
      const unit = (uoms.data ?? []).find(
        (row) => row.id === product.base_uom_id,
      );
      const filled: InlineDraft = {
        product_id: productId,
        description: product.description || product.product_name || '',
        brand_snapshot: brand?.brand_name ?? '',
        uom: unit?.uom_code ?? '',
        list_price: product.list_price ?? '',
      };
      const agreed = seriesPriceByProduct.get(productId);
      if (agreed) filled.unit_price = agreed;
      return filled;
    },
    [brands.data, seriesPriceByProduct, uoms.data],
  );

  const productLabel = React.useCallback(
    (row: QuotationFormLine): string => {
      const productId = row.draft.product_id;
      if (!productId) return '';
      const product = picked.get(productId);
      if (product) return product.product_code;
      if (row.line?.product_id === productId)
        return row.line.product_code ?? 'Selected product';
      return 'Selected product';
    },
    [picked],
  );

  const patchLine = React.useCallback((key: string, patch: InlineDraft) => {
    onChangeRef.current?.(
      linesRef.current.map((line) =>
        line.key === key
          ? { ...line, draft: { ...line.draft, ...patch } }
          : line,
      ),
    );
  }, []);

  const removeLine = React.useCallback((key: string) => {
    onChangeRef.current?.(linesRef.current.filter((line) => line.key !== key));
    setExpanded({});
  }, []);

  const addLine = React.useCallback((withSection: boolean) => {
    const added = newFormLine();
    onChangeRef.current?.([...linesRef.current, added]);
    // One editor open at a time: the new line's, so the next thing typed lands in it.
    setExpanded({ [added.key]: true });
    setFocusRowId(added.key);
    setFocusBandKey(withSection ? `band:${added.key}` : `first:${added.key}`);
  }, []);

  const toggleRow = React.useCallback((key: string) => {
    setExpanded((previous) =>
      previous !== true && (previous as Record<string, boolean>)[key]
        ? {}
        : { [key]: true },
    );
    setFocusBandKey(null);
  }, []);

  // The photo viewer, scrolled with its own arrows through the lines that HAVE a photograph.
  const photoLines = React.useMemo(
    () =>
      lines
        .map((row) => row.line)
        .filter((line): line is QuotationLine =>
          Boolean(
            line &&
            line.product_image?.state === 'chosen' &&
            (line.product_image.preview_url || line.product_image.url),
          ),
        ),
    [lines],
  );
  const photoLinesRef = React.useRef(photoLines);
  photoLinesRef.current = photoLines;
  const [previewIndex, setPreviewIndex] = React.useState<number | null>(null);
  const openPreview = React.useCallback((lineId: string) => {
    const index = photoLinesRef.current.findIndex((line) => line.id === lineId);
    if (index >= 0) setPreviewIndex(index);
  }, []);
  const photoItems = React.useMemo<AttachmentPreviewItem[]>(
    () =>
      photoLines.map((line) => {
        const image = line.product_image!;
        return {
          id: image.attachment_id ?? line.id,
          name: image.filename ?? `${line.product_code ?? 'Product'} photo`,
          url: image.preview_url || image.url || '',
          downloadUrl: image.attachment_id
            ? `/api/v1/resource-management/attachments/${image.attachment_id}/download`
            : undefined,
        };
      }),
    [photoLines],
  );

  const columns = React.useMemo<ColumnDef<QuotationFormLine>[]>(() => {
    const itemNo = (row: QuotationFormLine) =>
      (indexByKey.current.get(row.key) ?? 0) + 1;
    const defs: ColumnDef<QuotationFormLine>[] = [
      {
        // The row's position in the scope, counted straight through the sections, the way the
        // customer's own bill of quantities reads.
        id: 'item_no',
        header: ({ column }) => (
          <DataGridColumnHeader title="Item" column={column} />
        ),
        cell: ({ row }) => (
          <span className="text-sm tabular-nums">{itemNo(row.original)}</span>
        ),
        size: 64,
        minSize: 48,
        meta: { headerTitle: 'Item' },
      },
      {
        id: 'product_image',
        header: ({ column }) => (
          <DataGridColumnHeader title="Photo" column={column} />
        ),
        cell: ({ row }) => (
          <QuotationLinePhoto
            line={row.original.line}
            onPreview={
              row.original.line
                ? () => openPreview(row.original.line!.id)
                : undefined
            }
          />
        ),
        size: 96,
        minSize: 72,
        meta: { headerTitle: 'Photo' },
      },
      {
        id: 'product',
        header: ({ column }) => (
          <DataGridColumnHeader title="Product" column={column} />
        ),
        cell: ({ row }) => {
          const label = productLabel(row.original);
          return (
            <div className="min-w-0">
              {label ? <TextCell value={label} /> : null}
              <LineFlags
                quotationId={quotationId ?? null}
                line={row.original.line}
                draft={row.original.draft}
              />
            </div>
          );
        },
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Product' },
      },
      {
        id: 'description',
        header: ({ column }) => (
          <DataGridColumnHeader title="Description" column={column} />
        ),
        cell: ({ row }) => <TextCell value={row.original.draft.description} />,
        size: 240,
        minSize: 140,
        meta: { headerTitle: 'Description' },
      },
      {
        id: 'technical_spec',
        header: ({ column }) => (
          <DataGridColumnHeader title="Tech spec" column={column} />
        ),
        cell: ({ row }) => (
          <TextCell value={row.original.draft.technical_spec} />
        ),
        size: 200,
        minSize: 120,
        meta: { headerTitle: 'Tech spec' },
      },
      {
        id: 'brand',
        header: ({ column }) => (
          <DataGridColumnHeader title="Brand" column={column} />
        ),
        cell: ({ row }) => (
          <TextCell value={row.original.draft.brand_snapshot} />
        ),
        size: 140,
        minSize: 90,
        meta: { headerTitle: 'Brand' },
      },
      {
        id: 'quantity',
        header: ({ column }) => (
          <DataGridColumnHeader title="Qty" column={column} />
        ),
        cell: ({ row }) => (
          <TextCell
            value={trimAmount(row.original.draft.quantity)}
            align="end"
          />
        ),
        size: 90,
        minSize: 64,
        meta: { headerTitle: 'Qty' },
      },
      {
        id: 'uom',
        header: ({ column }) => (
          <DataGridColumnHeader title="UOM" column={column} />
        ),
        cell: ({ row }) => <TextCell value={row.original.draft.uom} />,
        size: 90,
        minSize: 64,
        meta: { headerTitle: 'UOM' },
      },
      {
        id: 'unit_price',
        header: ({ column }) => (
          <DataGridColumnHeader title="Unit price" column={column} />
        ),
        cell: ({ row }) => {
          const { draft } = row.original;
          const listPrice = draft.list_price || row.original.line?.list_price;
          return (
            <div className="min-w-0 text-end">
              <TextCell
                value={draft.unit_price ? formatMyrExact(draft.unit_price) : ''}
                align="end"
              />
              {listPrice ? (
                <span className="block truncate text-xs text-muted-foreground">
                  {`List ${formatMyrExact(listPrice)}`}
                </span>
              ) : null}
            </div>
          );
        },
        size: 130,
        minSize: 100,
        meta: { headerTitle: 'Unit price' },
      },
      {
        id: 'complete_set',
        header: ({ column }) => (
          <DataGridColumnHeader title="Complete set" column={column} />
        ),
        cell: ({ row }) => <TextCell value={row.original.draft.complete_set} />,
        size: 160,
        minSize: 100,
        meta: { headerTitle: 'Complete set' },
      },
      {
        id: 'unit_type',
        header: ({ column }) => (
          <DataGridColumnHeader title="Counts per" column={column} />
        ),
        cell: ({ row }) => (
          <TextCell
            value={
              UNIT_TYPE_OPTIONS.find(
                (option) => option.value === row.original.draft.unit_type,
              )?.label ?? ''
            }
          />
        ),
        size: 150,
        minSize: 100,
        meta: { headerTitle: 'Counts per' },
      },
      {
        // In the row, next to the money it governs: a reader scanning the Total column has to see
        // WHY a line says "rate only" without opening anything.
        id: 'is_rate_only',
        header: ({ column }) => (
          <DataGridColumnHeader title="Rate only" column={column} />
        ),
        cell: ({ row }) =>
          isInlineChecked(row.original.draft.is_rate_only) ? (
            <span className="text-sm">Yes</span>
          ) : (
            <Dash />
          ),
        size: 96,
        minSize: 72,
        meta: { headerTitle: 'Rate only' },
      },
      {
        id: 'line_total',
        header: ({ column }) => (
          <DataGridColumnHeader title="Total" column={column} />
        ),
        cell: ({ row }) => {
          const { draft } = row.original;
          // A rate-only line prints the words: blank reads as "we forgot" and RM 0.00 as "free".
          return isInlineChecked(draft.is_rate_only) ? (
            <Badge variant="secondary" appearance="light">
              rate only
            </Badge>
          ) : (
            <TextCell
              value={formatMyrExact(
                multiplyMoney(draft.quantity, draft.unit_price) ?? '0',
              )}
              align="end"
            />
          );
        },
        // The WHOLE scope, whatever the search is showing: a total that shrank with the view
        // would read as lines lost.
        footer: () => {
          const total = formLinesTotal(linesRef.current);
          return (
            <span className="block text-end tabular-nums">
              {total === null ? '-' : formatMyrExact(total)}
            </span>
          );
        },
        size: 140,
        minSize: 100,
        meta: {
          headerTitle: 'Total',
          expandedContent: (row: QuotationFormLine) => (
            <LineEditor
              key={row.key}
              index={itemNo(row)}
              row={row}
              fetchProducts={fetchProducts}
              selectedProduct={
                row.draft.product_id
                  ? {
                      value: row.draft.product_id,
                      label: productLabel(row),
                      description: row.draft.description || undefined,
                    }
                  : undefined
              }
              uomOptions={uomOptions}
              focus={
                focusBandKey === `band:${row.key}`
                  ? 'band'
                  : focusBandKey === `first:${row.key}`
                    ? 'first'
                    : null
              }
              onPatch={(patch) => patchLine(row.key, patch)}
              onPickProduct={(productId) =>
                patchLine(
                  row.key,
                  productId ? fillFromProduct(productId) : { product_id: '' },
                )
              }
              onRemove={() => removeLine(row.key)}
              onDone={() => setExpanded({})}
            />
          ),
        },
      },
    ];
    if (editable) {
      defs.push({
        id: 'actions',
        header: () => <span className="sr-only">Edit</span>,
        cell: ({ row }) => (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            mode="icon"
            aria-label={`Edit line ${itemNo(row.original)}`}
            title="Edit this line"
            onClick={(event) => {
              event.stopPropagation();
              toggleRow(row.original.key);
            }}
          >
            <SquarePen className="size-4" aria-hidden />
          </Button>
        ),
        size: 56,
        minSize: 56,
        enableResizing: false,
        meta: { headerTitle: 'Edit' },
      });
    }
    return defs;
  }, [
    editable,
    fetchProducts,
    fillFromProduct,
    focusBandKey,
    openPreview,
    patchLine,
    productLabel,
    quotationId,
    removeLine,
    toggleRow,
    uomOptions,
  ]);

  return (
    <div className="min-w-0">
      <PanelDataGrid<QuotationFormLine>
        title={title}
        columns={columns}
        rows={lines}
        getRowId={(row) => row.key}
        listingKey={listingKey}
        emptyTitle="No lines yet"
        searchPlaceholder="Search lines"
        searchOf={(row) =>
          [
            productLabel(row),
            row.draft.description,
            row.draft.brand_snapshot,
            row.draft.band_label,
          ]
            .filter(Boolean)
            .join(' ')
        }
        pageSize={25}
        focusRowId={focusRowId}
        renderGroupHeader={(row) => {
          const band = (row.draft.band_label ?? '').trim();
          return band ? band : null;
        }}
        expanded={editable ? expanded : undefined}
        onExpandedChange={editable ? setExpanded : undefined}
        onRowClick={editable ? (row) => toggleRow(row.key) : undefined}
        toolbar={
          editable ? (
            <>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => addLine(false)}
              >
                <Plus className="size-4" aria-hidden />
                Add a line
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => addLine(true)}
              >
                <Plus className="size-4" aria-hidden />
                Add a section
              </Button>
            </>
          ) : undefined
        }
      />

      {previewIndex !== null && photoItems.length > 0 && (
        <AttachmentPreviewModal
          open
          onOpenChange={(next) => {
            if (!next) setPreviewIndex(null);
          }}
          items={photoItems}
          startIndex={previewIndex}
        />
      )}
    </div>
  );
}

/**
 * One line's editor, opened in place under its row by the per-row Edit.
 *
 * Every field of the line, stacked in the printed order, so a phone can reach all of them
 * without the table scrolling sideways. Typing writes nothing; it patches the line the form holds.
 */
function LineEditor({
  index,
  row,
  fetchProducts,
  selectedProduct,
  uomOptions,
  focus,
  onPatch,
  onPickProduct,
  onRemove,
  onDone,
}: {
  index: number;
  row: QuotationFormLine;
  fetchProducts: (query: string) => Promise<SearchableSelectOption[]>;
  selectedProduct?: SearchableSelectOption;
  uomOptions: SearchableSelectOption[];
  focus: 'band' | 'first' | null;
  onPatch: (patch: InlineDraft) => void;
  onPickProduct: (productId: string) => void;
  onRemove: () => void;
  onDone: () => void;
}) {
  const { draft } = row;
  const errors = lineErrors(draft);
  const idFor = (field: string) => `quotation-line-${row.key}-${field}`;
  const bandRef = React.useRef<HTMLInputElement>(null);
  // A new line puts the caret in it: on the heading for Add a section, otherwise on the product
  // picker, the first thing a line is filled in by.
  React.useEffect(() => {
    if (focus === 'band') bandRef.current?.focus();
    if (focus === 'first')
      document.getElementById(idFor('product_id'))?.focus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focus]);

  const numberError = (value: string) =>
    value.trim() === '' || isDecimalString(value) ? null : 'Must be a number';
  const qtyError = numberError(draft.quantity ?? '');
  const priceError = numberError(draft.unit_price ?? '');

  const text = (
    field: string,
    label: string,
    placeholder?: string,
    maxLength?: number,
  ) => (
    <div className="min-w-0 space-y-1.5">
      <Label htmlFor={idFor(field)}>{label}</Label>
      <Input
        id={idFor(field)}
        value={draft[field] ?? ''}
        placeholder={placeholder}
        maxLength={maxLength}
        aria-invalid={Boolean(errors[field]) || undefined}
        onChange={(event) => onPatch({ [field]: event.target.value })}
      />
      {errors[field] ? (
        <p className="text-xs text-destructive">{errors[field]}</p>
      ) : null}
    </div>
  );

  return (
    <div
      role="group"
      aria-label={`Line ${index}`}
      className="space-y-4 border-t border-border bg-muted/30 px-4 py-4"
      onClick={(event) => event.stopPropagation()}
      onKeyDown={(event) => event.stopPropagation()}
    >
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <div className="min-w-0 space-y-1.5 sm:col-span-2 lg:col-span-4">
          <Label htmlFor={idFor('band_label')}>Section heading</Label>
          <Input
            ref={bandRef}
            id={idFor('band_label')}
            value={draft.band_label ?? ''}
            maxLength={150}
            placeholder="e.g. BILL NO 3 PAGE 15/4, OPTIONAL ITEMS"
            onChange={(event) => onPatch({ band_label: event.target.value })}
          />
        </div>
        <div className="min-w-0 space-y-1.5 sm:col-span-2">
          <Label htmlFor={idFor('product_id')}>Product</Label>
          <SearchableSelect
            id={idFor('product_id')}
            value={draft.product_id ?? ''}
            onChange={(value) => onPickProduct(value)}
            fetchOptions={fetchProducts}
            selectedOption={selectedProduct}
            clearable
            placeholder="Off-catalog line"
          />
        </div>
        <div className="sm:col-span-2">
          {text('description', 'Description', "The product's own description")}
        </div>
        {text('technical_spec', 'Tech spec', 'Rimless, 4/2.6L dual flush')}
        {text('brand_snapshot', 'Brand', 'SORENTO', 100)}
        <div className="min-w-0 space-y-1.5">
          <Label htmlFor={idFor('quantity')}>Qty</Label>
          <Input
            id={idFor('quantity')}
            inputMode="decimal"
            value={draft.quantity ?? ''}
            aria-invalid={Boolean(qtyError) || undefined}
            onChange={(event) => onPatch({ quantity: event.target.value })}
          />
          {qtyError ? (
            <p className="text-xs text-destructive">{qtyError}</p>
          ) : null}
        </div>
        <div className="min-w-0 space-y-1.5">
          <Label htmlFor={idFor('uom')}>UOM</Label>
          <SearchableSelect
            id={idFor('uom')}
            value={draft.uom ?? ''}
            onChange={(value) => onPatch({ uom: value })}
            options={uomOptions}
            clearable
            placeholder="PCS"
          />
        </div>
        <div className="min-w-0 space-y-1.5">
          <Label htmlFor={idFor('unit_price')}>Unit price</Label>
          <Input
            id={idFor('unit_price')}
            inputMode="decimal"
            value={draft.unit_price ?? ''}
            placeholder="0.00"
            aria-invalid={Boolean(priceError) || undefined}
            onChange={(event) => onPatch({ unit_price: event.target.value })}
          />
          {priceError ? (
            <p className="text-xs text-destructive">{priceError}</p>
          ) : draft.list_price ? (
            <p className="text-xs text-muted-foreground">{`List ${formatMyrExact(draft.list_price)}`}</p>
          ) : null}
        </div>
        {text(
          'complete_set',
          'Complete set',
          'c/w seat cover, flush valve',
          100,
        )}
        <div className="min-w-0 space-y-1.5">
          <Label htmlFor={idFor('unit_type')}>Counts per</Label>
          <SearchableSelect
            id={idFor('unit_type')}
            value={draft.unit_type ?? ''}
            onChange={(value) => onPatch({ unit_type: value })}
            options={UNIT_TYPE_OPTIONS}
            clearable
            placeholder="Not counted per unit"
          />
        </div>
        <div className="flex min-w-0 items-center gap-2 self-end pb-2">
          <Checkbox
            id={idFor('is_rate_only')}
            checked={isInlineChecked(draft.is_rate_only)}
            onCheckedChange={(checked) =>
              onPatch({ is_rate_only: checked === true ? INLINE_CHECKED : '' })
            }
          />
          <Label htmlFor={idFor('is_rate_only')}>Rate only</Label>
        </div>
        <div className="min-w-0 space-y-1.5 sm:col-span-2 lg:col-span-4">
          <Label htmlFor={idFor('notes')}>Notes</Label>
          <Textarea
            id={idFor('notes')}
            rows={2}
            value={draft.notes ?? ''}
            placeholder="Why this price, what was agreed, what it replaces"
            onChange={(event) => onPatch({ notes: event.target.value })}
          />
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Button type="button" size="sm" variant="outline" onClick={onRemove}>
          <Trash2 className="size-4" aria-hidden />
          Remove line
        </Button>
        <Button type="button" size="sm" variant="outline" onClick={onDone}>
          Done
        </Button>
      </div>
    </div>
  );
}

/**
 * What is true about the line, on the spot: off-catalog off the live draft; non-standard and
 * below-floor off the saved line while the draft matches it, and off the server's live verdict
 * (the same functions the save runs) the moment it diverges. A line on a scope not saved yet has
 * no scope to be judged against, so only off-catalog shows until Save.
 */
export function LineFlags({
  quotationId,
  line,
  draft,
}: {
  quotationId: string | null;
  line: QuotationLine | null;
  draft: InlineDraft;
}) {
  const productId = (draft.product_id ?? '').trim();
  const price = (draft.unit_price ?? '').trim();
  const pristine =
    line != null &&
    (line.product_id ?? '') === productId &&
    (price || '') === (line.unit_price ?? '');
  const verdict = useLineVerdict(
    quotationId ?? '',
    { product_id: productId || undefined, unit_price: price || undefined },
    !pristine && Boolean(quotationId),
  );

  const belowFloor = pristine
    ? line.is_below_floor
    : Boolean(verdict.data?.is_below_floor);
  const nonStandard = pristine
    ? line.is_non_standard
    : Boolean(verdict.data?.is_non_standard);
  const floorText = pristine
    ? describeFloor(line)
    : describeVerdictFloor(verdict.data ?? null);

  if (productId && !belowFloor && !nonStandard) return null;

  return (
    <div className="mt-1 space-y-0.5">
      <div className="flex flex-wrap items-center gap-1">
        {!productId && (
          <Badge variant="outline" className="text-2xs">
            Off-catalog
          </Badge>
        )}
        {belowFloor && (
          <Badge
            variant="destructive"
            className="gap-1 text-2xs"
            title={floorText}
          >
            <AlertTriangle className="size-3" aria-hidden />
            Below floor
          </Badge>
        )}
        {nonStandard && (
          <Badge
            variant="secondary"
            className="gap-1 text-2xs"
            title="Outside the series this scope is quoted from"
          >
            <TriangleAlert className="size-3" aria-hidden />
            Non-standard
          </Badge>
        )}
      </div>
      {belowFloor && floorText && (
        <p className="truncate text-xs text-destructive" title={floorText}>
          {floorText}
        </p>
      )}
    </div>
  );
}

function describeVerdictFloor(verdict: QuotationLineVerdict | null): string {
  if (!verdict?.floor_value) return 'Below the floor for this item.';
  const level = verdict.floor_level
    ? (FLOOR_LEVEL_LABELS[verdict.floor_level] ?? verdict.floor_level)
    : 'this item';
  return `Floor is ${formatMyrExact(verdict.floor_value)}, set on ${level}.`;
}

/** Says which rule bit, so the salesperson knows whose policy to argue with. */
function describeFloor(line: QuotationLine): string {
  if (!line.floor_value_applied) return 'Below the floor for this item.';
  const level = line.floor_level_applied
    ? (FLOOR_LEVEL_LABELS[line.floor_level_applied] ?? line.floor_level_applied)
    : 'policy';
  return `Floor was ${formatMyrExact(line.floor_value_applied)}, set on ${level}.`;
}
