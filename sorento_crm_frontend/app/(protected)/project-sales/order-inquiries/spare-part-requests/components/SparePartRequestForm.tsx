'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { DatePickerField } from '@/components/ui/date-picker';
import { Label } from '@/components/ui/label';
import { NumberInput } from '@/components/ui/number-input';
import { Textarea } from '@/components/ui/textarea';
import { FormSection } from '@/components/common/FormSection';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { BASE_CURRENCY, CURRENCY_NAMED_OPTIONS } from '@/lib/currencies';
import { formatDateInMalaysia } from '@/lib/helpers';
import { searchProductOptions } from '@/app/(protected)/scm/services/scmOptionsService';
import { toast } from '@/lib/toast';
import { formatMoneyExact } from '../../../_shared/lib/money';
import { OrderInquiryStockGrid } from '../../../_shared/components/OrderInquiryStockGrid';
import { SoLineAttachmentsButton } from '../../../_shared/components/SoLineAttachmentsButton';
import { useSoLineAttachmentLookup } from '../../../_shared/hooks/useSoLineAttachments';
import {
  useSaveSparePartRequest,
  useSparePartLocations,
  useSparePartRequest,
  useSubmitSparePartRequest,
} from '../../../_shared/hooks/useSparePartRequest';
import {
  SparePartRequestError,
  type SparePartRequest,
  type SparePartRequestInput,
} from '../../../_shared/services/sparePartRequestService';

/** The catalogue by code and name (UAC R2), valued by product id. */
const searchProducts = (query: string, pageIndex: number) =>
  searchProductOptions(query, pageIndex, 'id');

type SectionKey = 'request' | 'lines';

interface DraftLine {
  key: string;
  id?: string;
  product: SearchableSelectOption | null;
  stockLocation: string;
  qty: number | null;
  unitPrice: number | null;
}

interface Problems {
  currency?: string;
  lines?: string;
  byLine: Record<string, string>;
}

let lineSeq = 0;
const newLine = (): DraftLine => ({
  key: `new-${(lineSeq += 1)}`,
  product: null,
  stockLocation: '',
  qty: null,
  unitPrice: null,
});

function lineTotal(line: DraftLine): string | null {
  if (line.qty == null || line.unitPrice == null) return null;
  if (Number.isNaN(line.qty) || Number.isNaN(line.unitPrice)) return null;
  return (line.qty * line.unitPrice).toFixed(4);
}

/** A saved request's line ids onto the form's lines (R2): each line with a product takes the
 *  first unclaimed saved line of the same product, so the next save updates those rows. */
function withSavedIds(lines: DraftLine[], saved: SparePartRequest): DraftLine[] {
  const unclaimed = [...saved.lines];
  return lines.map((line) => {
    if (!line.product) return line;
    const at = unclaimed.findIndex((l) => l.product_id === line.product?.value);
    if (at < 0) return line;
    const [match] = unclaimed.splice(at, 1);
    return { ...line, id: match.id };
  });
}

function fromRequest(request: SparePartRequest): DraftLine[] {
  return request.lines.map((l) => ({
    key: l.id,
    id: l.id,
    product: l.product_id
      ? {
          value: l.product_id,
          label: [l.item_code, l.product_name ?? l.description].filter(Boolean).join(' · '),
        }
      : null,
    stockLocation: l.stock_location ?? '',
    qty: l.qty == null ? null : Number(l.qty),
    unitPrice: l.unit_price == null ? null : Number(l.unit_price),
  }));
}

/**
 * SPARE-PART-ORDER-REQUEST (UAC R1, R2, R5, R6): the New / Edit spare part request form,
 * laid out like the price tag request form (`PriceTagRequestForm.tsx`): sections that open
 * in turn (Request, then Products once a currency is chosen), each with a one-line summary
 * while folded. Lines name a catalogue product (searched by code and name), a location that
 * starts as the header default, qty and unit price; each line's stock table is a chevron
 * away and, once saved, its photos are the fulfilment paperclip. Submit is the one main
 * button; Save as draft keeps it editable.
 */
export function SparePartRequestForm({ id }: { id?: string } = {}) {
  const router = useRouter();
  const existing = useSparePartRequest(id);
  // R2: the draft this form has written to. Set by the first save of a New form, so a
  // refused Submit followed by another Submit or Save updates that draft, never a second one.
  const [savedId, setSavedId] = useState<string | undefined>(id);
  const locations = useSparePartLocations();
  const save = useSaveSparePartRequest();
  const submit = useSubmitSparePartRequest();

  const [currency, setCurrency] = useState<string>(id ? '' : BASE_CURRENCY);
  const [neededBy, setNeededBy] = useState<string | null>(null);
  const [defaultLocation, setDefaultLocation] = useState('');
  const [reason, setReason] = useState('');
  const [lines, setLines] = useState<DraftLine[]>(() => (id ? [] : [newLine()]));
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [problems, setProblems] = useState<Problems>({ byLine: {} });
  const loadedRef = useRef(false);

  useEffect(() => {
    const request = existing.data;
    if (!request || loadedRef.current) return;
    loadedRef.current = true;
    setCurrency(request.currency ?? '');
    setNeededBy(request.needed_by ?? null);
    setDefaultLocation(request.default_location ?? '');
    setReason(request.reason ?? '');
    setLines(request.lines.length ? fromRequest(request) : [newLine()]);
  }, [existing.data]);

  // ---- Sections, as PriceTagRequestForm (openSectionOnce): a rule opens a section once,
  // and a section folded by hand is never reopened by a rule.
  const [sectionOpen, setSectionOpen] = useState<Record<SectionKey, boolean>>({
    request: true,
    lines: false,
  });
  const sectionSettledRef = useRef<Set<SectionKey>>(new Set());
  const openSectionOnce = useCallback((key: SectionKey) => {
    if (sectionSettledRef.current.has(key)) return;
    sectionSettledRef.current.add(key);
    setSectionOpen((prev) => (prev[key] ? prev : { ...prev, [key]: true }));
  }, []);
  const toggleSection = useCallback((key: SectionKey, next: boolean) => {
    sectionSettledRef.current.add(key);
    setSectionOpen((prev) => ({ ...prev, [key]: next }));
  }, []);
  useEffect(() => {
    if (currency) openSectionOnce('lines');
  }, [currency, openSectionOnce]);

  const total = useMemo(
    () => lines.reduce((sum, line) => sum + Number(lineTotal(line) ?? 0), 0).toFixed(4),
    [lines],
  );
  const summaries: Record<SectionKey, string | null> = {
    request: [currency || null, neededBy ? `needed by ${formatDateInMalaysia(neededBy)}` : null]
      .filter(Boolean)
      .join(', ') || null,
    lines: lines.some((l) => l.product)
      ? `${lines.length} line${lines.length === 1 ? '' : 's'}, ${formatMoneyExact(total, currency)}`
      : null,
  };

  const savedRowIds = useMemo(() => lines.map((l) => l.id).filter(Boolean) as string[], [lines]);
  const photos = useSoLineAttachmentLookup(savedRowIds, 'order_inquiry_row');
  // A new form's draft is its requester's to edit once its first save has landed.
  const canEditPhotos = Boolean(existing.data?.can_edit) || (!id && Boolean(savedId));

  const updateLine = (key: string, patch: Partial<DraftLine>) =>
    setLines((prev) => prev.map((l) => (l.key === key ? { ...l, ...patch } : l)));

  const body = (): SparePartRequestInput => ({
    currency: currency || null,
    needed_by: neededBy,
    default_location: defaultLocation || null,
    reason: reason.trim() || null,
    lines: lines
      .filter((l) => l.product)
      .map((l) => ({
        id: l.id ?? null,
        product_id: l.product?.value ?? null,
        stock_location: l.stockLocation || null,
        qty: l.qty == null || Number.isNaN(l.qty) ? null : String(l.qty),
        unit_price: l.unitPrice == null || Number.isNaN(l.unitPrice) ? null : String(l.unitPrice),
      })),
  });

  /** R5: what Submit needs, said next to the field it is about. */
  const checkForSubmit = (): Problems => {
    const found: Problems = { byLine: {} };
    if (!currency) found.currency = 'Choose the currency.';
    const chosen = lines.filter((l) => l.product);
    if (chosen.length === 0) found.lines = 'Add at least one product.';
    for (const line of lines) {
      if (!line.product) {
        if (chosen.length > 0 && (line.qty != null || line.unitPrice != null)) {
          found.byLine[line.key] = 'Choose a product.';
        }
        continue;
      }
      if (line.qty == null || Number.isNaN(line.qty) || line.qty <= 0) {
        found.byLine[line.key] = 'Enter a quantity above 0.';
      } else if (line.unitPrice != null && (Number.isNaN(line.unitPrice) || line.unitPrice < 0)) {
        found.byLine[line.key] = 'The unit price cannot be negative.';
      } else if (!line.stockLocation && !defaultLocation) {
        found.byLine[line.key] = 'Choose a location.';
      }
    }
    return found;
  };

  const showServerProblem = (error: unknown) => {
    const message = error instanceof Error ? error.message : 'Something went wrong.';
    const field = error instanceof SparePartRequestError ? error.field : undefined;
    if (field === 'currency') setProblems({ byLine: {}, currency: message });
    else if (field === 'lines' || field === 'qty' || field === 'unit_price')
      setProblems({ byLine: {}, lines: message });
    else toast.error(message);
  };

  // R7: an Edit form writes nothing until its request has loaded (an empty `lines` would
  // remove every line and its photos).
  const notLoaded = Boolean(id) && !existing.data;
  const busy = save.isPending || submit.isPending || notLoaded;

  const persist = async () => {
    const saved = await save.mutateAsync({ id: savedId, body: body() });
    setSavedId(saved.id);
    setLines((prev) => withSavedIds(prev, saved));
    return saved;
  };

  const onSaveDraft = async () => {
    setProblems({ byLine: {} });
    if (busy) return;
    try {
      const saved = await persist();
      toast.success('Saved as draft');
      router.push(`/project-sales/order-inquiries/${saved.id}`);
    } catch (error) {
      showServerProblem(error);
    }
  };

  const onSubmit = async () => {
    if (busy) return;
    const found = checkForSubmit();
    setProblems(found);
    if (found.currency || found.lines || Object.keys(found.byLine).length) {
      if (found.lines || Object.keys(found.byLine).length) toggleSection('lines', true);
      return;
    }
    try {
      const saved = await persist();
      await submit.mutateAsync(saved.id);
      router.push(`/project-sales/order-inquiries/${saved.id}`);
    } catch (error) {
      showServerProblem(error);
    }
  };

  if (id && existing.isError) {
    return (
      <div className="space-y-3 rounded-md border border-border p-6 text-center">
        <p className="text-sm font-semibold">Could not load this request</p>
        <p className="text-sm text-muted-foreground">
          {existing.error instanceof Error ? existing.error.message : 'Try again in a moment.'}
        </p>
        <Button type="button" variant="outline" onClick={() => void existing.refetch()}>
          Try again
        </Button>
      </div>
    );
  }

  if (notLoaded) {
    return (
      <div className="space-y-4" role="status" aria-label="Loading the request">
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (id && existing.data && !existing.data.can_edit) {
    return <p className="text-sm text-muted-foreground">This request is no longer a draft.</p>;
  }

  const locationOptions = locations.data ?? [];
  const defaultLabel = defaultLocation
    ? `Default (${defaultLocation})`
    : 'Choose a location';

  return (
    // D4: min-w-0 so the page never grows to the lines table's width at 375 (it scrolls in
    // its own box instead).
    <div className="min-w-0 space-y-4">
      <FormSection
        title="Request"
        summary={summaries.request}
        open={sectionOpen.request}
        onOpenChange={(next) => toggleSection('request', next)}
      >
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="spr-currency">Currency *</Label>
            <SearchableSelect
              id="spr-currency"
              value={currency}
              onChange={(value) => {
                setCurrency(value);
                setProblems((p) => ({ ...p, currency: undefined }));
              }}
              options={CURRENCY_NAMED_OPTIONS}
              placeholder="Choose the currency"
            />
            {problems.currency ? (
              <p className="text-xs text-destructive">{problems.currency}</p>
            ) : null}
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="spr-needed-by">Needed by</Label>
            <DatePickerField id="spr-needed-by" value={neededBy} onChange={setNeededBy} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="spr-default-location">Default location</Label>
            <SearchableSelect
              id="spr-default-location"
              value={defaultLocation}
              onChange={setDefaultLocation}
              options={locationOptions}
              loadError={locations.error}
              onRetry={() => void locations.refetch()}
              placeholder="No default"
              clearable
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="spr-reason">Reason</Label>
            <Textarea
              id="spr-reason"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
              rows={3}
            />
          </div>
        </div>
      </FormSection>

      <FormSection
        title="Products"
        summary={summaries.lines}
        open={sectionOpen.lines}
        onOpenChange={(next) => toggleSection('lines', next)}
        bodyClassName="p-0"
      >
        <div className="overflow-x-auto">
          {/* 840px of columns: fits the card at 1280 (935px inside); below that the table
              scrolls inside its own box, so 375 stays usable. */}
          <table className="w-full min-w-[840px] table-fixed text-sm">
            <thead className="border-b border-border bg-muted/40 text-left text-xs text-muted-foreground">
              <tr>
                <th className="w-12 px-3 py-2 font-medium">No.</th>
                <th className="w-56 px-3 py-2 font-medium">Product</th>
                <th className="w-40 px-3 py-2 font-medium">Location</th>
                <th className="w-24 px-3 py-2 text-right font-medium">Qty</th>
                <th className="w-28 px-3 py-2 text-right font-medium">Unit price</th>
                <th className="w-32 px-3 py-2 text-right font-medium">Total</th>
                <th className="w-[72px] px-3 py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {lines.map((line, index) => {
                const lineProblem = problems.byLine[line.key];
                const lineTotalValue = lineTotal(line);
                return [
                  <tr key={line.key} className="border-b border-border align-top">
                    <td className="px-3 py-2">
                      <div className="flex items-center gap-1">
                        <Button
                          type="button"
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          className="size-6"
                          disabled={!line.product}
                          aria-label={`${expanded[line.key] ? 'Hide' : 'Show'} stock for line ${index + 1}`}
                          aria-expanded={Boolean(expanded[line.key])}
                          onClick={() =>
                            setExpanded((prev) => ({ ...prev, [line.key]: !prev[line.key] }))
                          }
                        >
                          {expanded[line.key] ? (
                            <ChevronDown className="size-3.5" aria-hidden />
                          ) : (
                            <ChevronRight className="size-3.5" aria-hidden />
                          )}
                        </Button>
                        <span className="tabular-nums">{index + 1}</span>
                      </div>
                    </td>
                    <td className="px-3 py-2">
                      <SearchableSelect
                        aria-label={`Product for line ${index + 1}`}
                        value={line.product?.value ?? ''}
                        onChange={() => undefined}
                        onOptionChange={(option) => updateLine(line.key, { product: option })}
                        selectedOption={line.product ?? undefined}
                        fetchOptions={searchProducts}
                        paginated
                        placeholder="Search code or name"
                        wrapOptions
                      />
                      {lineProblem ? (
                        <p className="mt-1 text-xs text-destructive">{lineProblem}</p>
                      ) : null}
                    </td>
                    <td className="px-3 py-2">
                      <SearchableSelect
                        aria-label={`Location for line ${index + 1}`}
                        value={line.stockLocation}
                        onChange={(value) => updateLine(line.key, { stockLocation: value })}
                        options={locationOptions}
                        placeholder={defaultLabel}
                        clearable
                      />
                    </td>
                    <td className="px-3 py-2">
                      <NumberInput
                        aria-label={`Qty for line ${index + 1}`}
                        value={line.qty}
                        onValueChange={(qty) => updateLine(line.key, { qty })}
                        min={0}
                        step="any"
                        className="text-right tabular-nums"
                      />
                    </td>
                    <td className="px-3 py-2">
                      <NumberInput
                        aria-label={`Unit price for line ${index + 1}`}
                        value={line.unitPrice}
                        onValueChange={(unitPrice) => updateLine(line.key, { unitPrice })}
                        min={0}
                        step="any"
                        className="text-right tabular-nums"
                      />
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      <span className="block truncate pt-2" title={lineTotalValue ? formatMoneyExact(lineTotalValue, currency) : ''}>
                        {lineTotalValue ? formatMoneyExact(lineTotalValue, currency) : '-'}
                      </span>
                    </td>
                    <td className="px-3 py-2">
                      <div className="flex items-center justify-end gap-1">
                        {line.id ? (
                          <SoLineAttachmentsButton
                            lineId={line.id}
                            target={{ kind: 'order_inquiry_row', id: line.id }}
                            label={`Line ${index + 1} ${line.product?.label ?? ''}`.trim()}
                            attachments={photos.data[line.id] ?? []}
                            canEdit={canEditPhotos}
                          />
                        ) : null}
                        <Button
                          type="button"
                          mode="icon"
                          variant="ghost"
                          size="sm"
                          aria-label={`Remove line ${index + 1}`}
                          title="Remove line"
                          disabled={lines.length === 1}
                          onClick={() => setLines((prev) => prev.filter((l) => l.key !== line.key))}
                        >
                          <Trash2 className="size-3.5" aria-hidden />
                        </Button>
                      </div>
                    </td>
                  </tr>,
                  expanded[line.key] && line.product ? (
                    <tr key={`${line.key}-stock`} className="border-b border-border">
                      <td colSpan={7} className="px-3 py-2">
                        <OrderInquiryStockGrid
                          productId={line.product.value}
                          location={line.stockLocation || defaultLocation || null}
                        />
                      </td>
                    </tr>
                  ) : null,
                ];
              })}
            </tbody>
            <tfoot>
              <tr>
                <td colSpan={5} className="px-3 py-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setLines((prev) => [...prev, newLine()])}
                  >
                    <Plus className="size-4" aria-hidden />
                    Add product
                  </Button>
                </td>
                <td className="px-3 py-2 text-right font-medium tabular-nums">
                  {formatMoneyExact(total, currency)}
                </td>
                <td className="px-3 py-2 text-xs text-muted-foreground">Total</td>
              </tr>
            </tfoot>
          </table>
        </div>
        {problems.lines ? <p className="px-4 pb-3 text-xs text-destructive">{problems.lines}</p> : null}
      </FormSection>

      <div className="flex flex-wrap justify-end gap-2">
        <Button type="button" variant="outline" disabled={busy} onClick={() => void onSaveDraft()}>
          Save as draft
        </Button>
        <Button type="button" disabled={busy} onClick={() => void onSubmit()}>
          Submit
        </Button>
      </div>
    </div>
  );
}

export default SparePartRequestForm;
