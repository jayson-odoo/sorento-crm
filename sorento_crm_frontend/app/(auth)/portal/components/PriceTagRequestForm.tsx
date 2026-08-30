'use client';

/**
 * Portal price tag request form - create / edit / view.
 *
 * Wired to real portal API via `price-tag-request-service.ts`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  ArrowDown,
  ArrowUp,
  Check,
  Download,
  FileText,
  Loader2,
  MessageSquare,
  Plus,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import {
  priceTagStatusLabel,
  priceTagStatusPillClass,
} from '@/lib/price-tag-status';
import { portalBase } from '../lib/portal-paths';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
  DebtorOption,
  PromotionOption,
} from '../lib/price-tag-request-service';
import {
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
  getRequest,
  createRequest,
  submitRequest,
  approveRequest,
  requestChanges,
} from '../lib/price-tag-request-service';
import PriceTagProofViewer from './PriceTagProofViewer';
import POCrossCheckViewer from './POCrossCheckViewer';
import type { ResolvedLineData } from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';

// ---------------------------------------------------------------------------
// Draft line (client-side, before persisting)
// ---------------------------------------------------------------------------

interface DraftLine {
  key: string; // client-side key for React
  line_type: 'product' | 'product_set';
  product_id: string | null;
  product_set_id: string | null;
  name: string;
  code: string;
  show_promo_price: boolean;
  quantity: number;
  alternatives: { product_id: string; name: string; code: string }[];
  included_accessories: string;
  guard_error: string | null;
}

/**
 * A new row starts empty and TYPELESS in spirit: the Item picker decides whether
 * it is a product or a set (D47), so the dealer never has to. `product` is only
 * the placeholder until they pick, and an unpicked row blocks Submit either way.
 */
function emptyDraftLine(): DraftLine {
  return {
    key: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    line_type: 'product',
    product_id: null,
    product_set_id: null,
    name: '',
    code: '',
    show_promo_price: true,
    quantity: 1,
    alternatives: [],
    included_accessories: '',
    guard_error: null,
  };
}

/** The Item picker's option value: kind and id together, so one dropdown can
 *  answer for two tables without either half guessing which it got. */
function itemValue(line: DraftLine): string {
  if (line.line_type === 'product_set') {
    return line.product_set_id ? `product_set:${line.product_set_id}` : '';
  }
  return line.product_id ? `product:${line.product_id}` : '';
}

function lineToDraft(line: PriceTagRequestLine): DraftLine {
  return {
    key: line.id,
    line_type: line.line_type,
    product_id: line.product_id,
    product_set_id: line.product_set_id,
    name: line.name,
    code: line.code,
    show_promo_price: line.show_promo_price,
    quantity: line.quantity,
    alternatives: line.alternatives,
    included_accessories: line.included_accessories ?? '',
    guard_error: null,
  };
}

// ---------------------------------------------------------------------------
// Minimum deadline: today + 1 business day
// ---------------------------------------------------------------------------

function nextBusinessDay(): string {
  const d = new Date();
  d.setDate(d.getDate() + 1);
  // Skip Saturday and Sunday
  while (d.getDay() === 0 || d.getDay() === 6) {
    d.setDate(d.getDate() + 1);
  }
  return d.toISOString().split('T')[0];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  requestId?: string;
  slug?: string;
}

export function PriceTagRequestForm({ requestId, slug }: Props) {
  const router = useRouter();
  const isNew = !requestId;

  // ---- Data fetching state ----
  const [loading, setLoading] = useState(!isNew);
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [request, setRequest] = useState<PriceTagRequestDetail | null>(null);

  // ---- Lookup data ----
  const [debtors, setDebtors] = useState<DebtorOption[]>([]);
  /** True once the debtor lookup has ANSWERED. An empty list before it has is
   *  just "not back yet", and must not read as "you are not linked". */
  const [debtorsLoaded, setDebtorsLoaded] = useState(false);
  const [promotions, setPromotions] = useState<PromotionOption[]>([]);

  // ---- Form state ----
  const [debtorCode, setDebtorCode] = useState('');
  const [promotionId, setPromotionId] = useState<string>('');
  const [neededByDate, setNeededByDate] = useState(nextBusinessDay());
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);

  // ---- Proof review state ----
  const [changesNote, setChangesNote] = useState('');
  const [showChangesDialog, setShowChangesDialog] = useState(false);

  const isEditable = isNew || request?.status === 'draft';
  const isProofReady = request?.status === 'proof_ready';

  // ---- Load lookups ----
  useEffect(() => {
    // The debtor list is scoped to the sales agent this portal account is linked
    // to, so an EMPTY answer means "nobody has linked it" and is a state the form
    // has to explain (D46a). A FAILED call is a different thing and keeps the
    // toast, or the notice would blame the account for a network fault.
    lookupDebtors()
      .then((d) => {
        setDebtors(d);
        setDebtorsLoaded(true);
      })
      .catch(() => {
        setDebtorsLoaded(false);
        toast.error('Failed to load debtors');
      });
    lookupPromotions().then(setPromotions);
  }, []);

  // ---- Load existing request ----
  useEffect(() => {
    if (!requestId) return;
    let cancelled = false;
    setLoading(true);
    getRequest(requestId)
      .then((data) => {
        if (cancelled) return;
        if (!data) {
          toast.error('Request not found');
          router.back();
          return;
        }
        setRequest(data);
        setDebtorCode(data.debtor_code ?? '');
        setPromotionId(data.promotion_id ?? '');
        setNeededByDate(data.needed_by_date);
        setNotes(data.notes ?? '');
        setLines(data.lines.map(lineToDraft));
      })
      .catch(() => {
        if (!cancelled) toast.error('Failed to load request');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId, router]);

  // ---- Debtor options ----
  const debtorOptions = useMemo<SearchableSelectOption[]>(
    () =>
      debtors.map((d) => ({
        value: d.code,
        label: d.name,
        description: d.code,
      })),
    [debtors],
  );

  // ---- Promotion options ----
  const promotionOptions = useMemo<SearchableSelectOption[]>(
    () =>
      promotions.map((p) => ({
        value: p.id,
        label: p.name,
      })),
    [promotions],
  );

  // ---- Item options: sets and products in ONE list (D47) ----
  // The label carries the word Set or Product, because the two look alike in a
  // dropdown and picking the wrong one produces a different tag.
  const fetchItemOptions = useCallback(
    async (query: string): Promise<SearchableSelectOption[]> => {
      const items = await lookupTagItems(query);
      return items.map((i) => ({
        value: `${i.kind}:${i.id}`,
        label: i.name || i.code,
        description: `${i.kind === 'product_set' ? 'Set' : 'Product'} - ${i.code}`,
      }));
    },
    [],
  );

  // Alternatives are products only: an OR choice on a tag names another product,
  // never a whole set. Same call, filtered, rather than a second endpoint.
  //
  // The multi-select hands back values alone, and a line stores the product's NAME
  // and CODE beside its id (that is what the request detail and the tag print
  // read), so every product the picker has shown is remembered here. Bounded by
  // what one person can scroll through in one form.
  const seenProductsRef = useRef(new Map<string, { name: string; code: string }>());
  const fetchAlternativeOptions = useCallback(
    async (query: string): Promise<SearchableSelectOption[]> => {
      const items = await lookupTagItems(query);
      const products = items.filter((i) => i.kind === 'product');
      for (const p of products) {
        seenProductsRef.current.set(p.id, {
          name: p.name || p.code,
          code: p.code,
        });
      }
      return products.map((i) => ({
        value: i.id,
        label: i.name || i.code,
        description: i.code,
      }));
    },
    [],
  );

  // ---- Line management ----
  const addLine = useCallback(() => {
    setLines((prev) => [...prev, emptyDraftLine()]);
  }, []);

  const removeLine = useCallback((key: string) => {
    setLines((prev) => prev.filter((l) => l.key !== key));
  }, []);

  const updateLine = useCallback(
    (key: string, patch: Partial<DraftLine>) => {
      setLines((prev) =>
        prev.map((l) => (l.key === key ? { ...l, ...patch } : l)),
      );
    },
    [],
  );

  const moveLine = useCallback((index: number, direction: 'up' | 'down') => {
    setLines((prev) => {
      const next = [...prev];
      const target = direction === 'up' ? index - 1 : index + 1;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }, []);

  // ---- One picker, both kinds (D47) ----
  // The chosen option decides the line's type; the payload the server reads is
  // unchanged, still line_type plus whichever of the two ids matches it.
  const handleItemSelect = useCallback(
    (key: string, option: SearchableSelectOption | null) => {
      if (!option) {
        updateLine(key, {
          product_id: null,
          product_set_id: null,
          name: '',
          code: '',
          guard_error: null,
        });
        return;
      }
      const [kind, id] = option.value.split(':');
      const isSet = kind === 'product_set';
      updateLine(key, {
        line_type: isSet ? 'product_set' : 'product',
        product_id: isSet ? null : id,
        product_set_id: isSet ? id : null,
        name: option.label,
        // The description reads "Set - CODE" / "Product - CODE"; the code is what
        // the row shows, so it is stored without the word in front of it.
        code: (option.description ?? '').split(' - ').slice(1).join(' - '),
        // A set is priced and printed as one thing, so any OR choices typed
        // against a product line stop applying the moment it becomes a set.
        // Spread, not a key set to undefined, which would wipe it on a product.
        ...(isSet ? { alternatives: [] } : {}),
        guard_error: null,
      });
    },
    [updateLine],
  );

  // ---- Validation ----
  const hasGuardErrors = lines.some((l) => l.guard_error);
  const hasEmptyLines = lines.some(
    (l) =>
      (l.line_type === 'product' && !l.product_id) ||
      (l.line_type === 'product_set' && !l.product_set_id),
  );

  const canSubmit =
    !!debtorCode &&
    !!neededByDate &&
    lines.length > 0 &&
    !hasGuardErrors &&
    !hasEmptyLines;

  // ---- Save draft ----
  const handleSaveDraft = useCallback(async () => {
    if (!debtorCode) {
      toast.error('Please select a debtor');
      return;
    }
    setSaving(true);
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      await createRequest({
        debtor_code: debtorCode,
        debtor_name: debtor?.name ?? debtorCode,
        promotion_id: promotionId || null,
        needed_by_date: neededByDate,
        notes: notes || null,
        lines: lines.map((l) => ({
          line_type: l.line_type,
          product_id: l.product_id,
          product_set_id: l.product_set_id,
          show_promo_price: l.show_promo_price,
          quantity: l.quantity,
          alternatives: l.alternatives,
          included_accessories: l.included_accessories || null,
          product_class: null,
        })),
      });
      toast.success('Draft saved');
      router.push(`${portalBase(slug)}?type=price_tag_request`);
    } catch (e) {
      // The server's sentence, not ours: the set guard refuses an ala carte
      // Bathroom Furniture line by NAME, and a generic message would leave the
      // salesperson with no idea which line to change.
      toast.error(e instanceof Error ? e.message : 'Failed to save draft');
    } finally {
      setSaving(false);
    }
  }, [debtorCode, debtors, promotionId, neededByDate, notes, lines, router, slug]);

  // ---- Submit ----
  const handleSubmit = useCallback(async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      const created = await createRequest({
        debtor_code: debtorCode,
        debtor_name: debtor?.name ?? debtorCode,
        promotion_id: promotionId || null,
        needed_by_date: neededByDate,
        notes: notes || null,
        lines: lines.map((l) => ({
          line_type: l.line_type,
          product_id: l.product_id,
          product_set_id: l.product_set_id,
          show_promo_price: l.show_promo_price,
          quantity: l.quantity,
          alternatives: l.alternatives,
          included_accessories: l.included_accessories || null,
          product_class: null,
        })),
      });
      await submitRequest(created.id);
      toast.success('Request submitted');
      router.push(`${portalBase(slug)}?type=price_tag_request`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to submit request');
    } finally {
      setSubmitting(false);
    }
  }, [canSubmit, debtorCode, debtors, promotionId, neededByDate, notes, lines, router, slug]);

  // ---- Approve proof ----
  const handleApprove = useCallback(async () => {
    if (!requestId) return;
    try {
      await approveRequest(requestId);
      toast.success('Proof approved');
      router.push(`${portalBase(slug)}?type=price_tag_request`);
    } catch {
      toast.error('Failed to approve');
    }
  }, [requestId, router, slug]);

  // ---- Request changes ----
  const handleRequestChanges = useCallback(async () => {
    if (!requestId || !changesNote.trim()) return;
    try {
      await requestChanges(requestId, changesNote.trim());
      toast.success('Changes requested');
      setShowChangesDialog(false);
      router.push(`${portalBase(slug)}?type=price_tag_request`);
    } catch {
      toast.error('Failed to request changes');
    }
  }, [requestId, changesNote, router, slug]);

  // ---- Loading skeleton ----
  if (loading) {
    return (
      <div className="w-full px-3 pt-4 pb-4 space-y-3">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  // ---- Read-only detail view (non-editable statuses) ----
  if (request && !isEditable && !isProofReady) {
    const showDownload =
      request.status === 'ready' || request.status === 'approved';
    return (
      <div className="w-full max-w-2xl mx-auto px-3 pt-4 pb-8 space-y-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push(`${portalBase(slug)}?type=price_tag_request`)}
        >
          <ArrowLeft className="size-4 mr-1" /> Back
        </Button>

        <RequestDetailView request={request} />

        {showDownload && (
          <Card>
            <CardContent className="pt-4">
              <Button
                onClick={() => {
                  // Phase 2: link to the actual download via download_id.
                  toast.info('PDF download will be available when export completes.');
                }}
                size="sm"
              >
                <Download className="size-4 mr-1" />
                Download PDF
              </Button>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  // ---- Proof review view ----
  if (request && isProofReady) {
    return (
      <div className="w-full max-w-2xl mx-auto px-3 pt-4 pb-8 space-y-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => router.push(`${portalBase(slug)}?type=price_tag_request`)}
        >
          <ArrowLeft className="size-4 mr-1" /> Back
        </Button>

        <RequestDetailView request={request} />

        {/* Tag sheet proof preview */}
        <ProofPreviewSection request={request} />

        {/* PO cross-check Phase 1: side-by-side */}
        <POCrossCheckViewer
          attachments={request.attachments}
          lines={request.lines.map((l) => ({
            id: l.id,
            code: l.code,
            name: l.name,
            line_type: l.line_type,
            quantity: l.quantity,
            list_price: null,
            sell_price: null,
            show_promo_price: l.show_promo_price,
            marketing_price_override: null,
          }))}
        />

        <Card>
          <CardHeader>
            <CardTitle className="text-base">Proof Review</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-col gap-2 sm:flex-row">
              <Button onClick={handleApprove} className="flex-1">
                <Check className="size-4 mr-1" />
                Approve
              </Button>
              <Button
                variant="outline"
                onClick={() => setShowChangesDialog(true)}
                className="flex-1"
              >
                <MessageSquare className="size-4 mr-1" />
                Request Changes
              </Button>
            </div>
          </CardContent>
        </Card>

        <AlertDialog
          open={showChangesDialog}
          onOpenChange={setShowChangesDialog}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Request Changes</AlertDialogTitle>
              <AlertDialogDescription>
                Describe what needs to be changed. The marketing team will revise
                the proof.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <Textarea
              value={changesNote}
              onChange={(e) => setChangesNote(e.target.value)}
              placeholder="Describe the changes needed..."
              rows={4}
            />
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction
                onClick={handleRequestChanges}
                disabled={!changesNote.trim()}
              >
                Submit
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </div>
    );
  }

  // ---- Edit / create form ----
  return (
    <div className="w-full max-w-2xl mx-auto px-3 pt-4 pb-8 space-y-4">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => router.push(`${portalBase(slug)}?type=price_tag_request`)}
      >
        <ArrowLeft className="size-4 mr-1" /> Back
      </Button>

      <h1 className="text-lg font-semibold">
        {isNew ? 'New Price Tag Request' : `Edit ${request?.doc_number ?? ''}`}
      </h1>

      {/* Debtor */}
      <div className="space-y-1.5">
        <Label htmlFor="debtor">Debtor *</Label>
        {debtorsLoaded && debtorOptions.length === 0 ? (
          <p
            className="text-sm rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
            data-testid="no-debtors-notice"
          >
            No debtors available. Your portal account is not linked to a sales
            agent yet. Ask your Sorento contact to link it.
          </p>
        ) : (
          <SearchableSelect
            id="debtor"
            value={debtorCode}
            onChange={setDebtorCode}
            options={debtorOptions}
            placeholder="Select a dealer..."
          />
        )}
      </div>

      {/* Promotion */}
      <div className="space-y-1.5">
        <Label htmlFor="promotion">Promotion</Label>
        <SearchableSelect
          id="promotion"
          value={promotionId}
          onChange={setPromotionId}
          options={promotionOptions}
          placeholder="Select a promotion (optional)..."
          clearable
        />
      </div>

      {/* Needed by date */}
      <div className="space-y-1.5">
        <Label htmlFor="needed_by_date">Needed by *</Label>
        <Input
          id="needed_by_date"
          type="date"
          value={neededByDate}
          onChange={(e) => setNeededByDate(e.target.value)}
          min={nextBusinessDay()}
        />
      </div>

      {/* Notes */}
      <div className="space-y-1.5">
        <Label htmlFor="notes">Notes</Label>
        <Textarea
          id="notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Any additional notes..."
          rows={3}
        />
      </div>

      {/* Lines: one table, one Add button, one Item dropdown (D47) */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Lines</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 px-4 pb-4">
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No lines yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="w-8 px-2 py-2 text-left">#</th>
                    <th className="min-w-[220px] px-2 py-2 text-left">Item</th>
                    <th className="w-24 px-2 py-2 text-left">Qty (tags)</th>
                    <th className="min-w-[200px] px-2 py-2 text-left">
                      Alternatives
                    </th>
                    <th className="min-w-[180px] px-2 py-2 text-left">
                      Accessories
                    </th>
                    {!!promotionId && (
                      <th className="w-28 px-2 py-2 text-left">Promo price</th>
                    )}
                    <th className="w-24 px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => (
                    <LineRow
                      key={line.key}
                      line={line}
                      index={index}
                      total={lines.length}
                      hasPromotion={!!promotionId}
                      fetchItemOptions={fetchItemOptions}
                      fetchAlternativeOptions={fetchAlternativeOptions}
                      seenProducts={seenProductsRef.current}
                      onItemSelect={handleItemSelect}
                      onUpdate={updateLine}
                      onRemove={removeLine}
                      onMove={moveLine}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <Button size="sm" variant="outline" onClick={addLine}>
            <Plus className="size-3.5 mr-1" /> Add line
          </Button>
        </CardContent>
      </Card>

      {/* PO Upload */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Purchase Order</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <div className="border-2 border-dashed rounded-lg p-4 text-center">
            <input
              type="file"
              multiple
              accept=".pdf,.jpg,.jpeg,.png"
              className="hidden"
              id="po-upload"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                setPendingFiles((prev) => [...prev, ...files]);
                e.target.value = '';
              }}
            />
            <label
              htmlFor="po-upload"
              className="cursor-pointer flex flex-col items-center gap-2 text-muted-foreground hover:text-foreground transition-colors"
            >
              <FileText className="size-8" />
              <span className="text-sm">
                Drop PO files here or click to browse
              </span>
              <span className="text-xs">PDF, JPG, PNG</span>
            </label>
          </div>
          {pendingFiles.length > 0 && (
            <div className="mt-3 space-y-1">
              {pendingFiles.map((file, i) => (
                <div
                  key={`${file.name}-${i}`}
                  className="flex items-center justify-between text-sm px-2 py-1 bg-muted rounded"
                >
                  <span className="truncate" title={file.name}>
                    {file.name}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-6 w-6 p-0"
                    onClick={() =>
                      setPendingFiles((prev) => prev.filter((_, idx) => idx !== i))
                    }
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              ))}
            </div>
          )}
          {request?.attachments && request.attachments.length > 0 && (
            <div className="mt-3 space-y-1">
              <p className="text-xs text-muted-foreground font-medium">
                Existing attachments
              </p>
              {request.attachments.map((att) => (
                <div
                  key={att.id}
                  className="flex items-center text-sm px-2 py-1 bg-muted rounded"
                >
                  <FileText className="size-3.5 mr-2 text-muted-foreground" />
                  <span className="truncate" title={att.filename}>
                    {att.filename}
                  </span>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Actions */}
      <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
        <Button
          variant="outline"
          onClick={handleSaveDraft}
          disabled={saving || submitting || !debtorCode}
        >
          {saving && <Loader2 className="size-4 mr-1 animate-spin" />}
          Save Draft
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={submitting || saving || !canSubmit}
        >
          {submitting && <Loader2 className="size-4 mr-1 animate-spin" />}
          Submit
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Line row
// ---------------------------------------------------------------------------

interface LineRowProps {
  line: DraftLine;
  index: number;
  total: number;
  hasPromotion: boolean;
  fetchItemOptions: (query: string) => Promise<SearchableSelectOption[]>;
  fetchAlternativeOptions: (query: string) => Promise<SearchableSelectOption[]>;
  seenProducts: Map<string, { name: string; code: string }>;
  onItemSelect: (key: string, option: SearchableSelectOption | null) => void;
  onUpdate: (key: string, patch: Partial<DraftLine>) => void;
  onRemove: (key: string) => void;
  onMove: (index: number, direction: 'up' | 'down') => void;
}

/**
 * One row of the lines table, on the Purchase Request pattern in `SubmissionForm`:
 * a cell per field, a trash button, and horizontal scroll on a narrow screen.
 *
 * Alternatives are disabled on a set row and say why, which is the capability the
 * Set card this replaced simply did not have.
 */
function LineRow({
  line,
  index,
  total,
  hasPromotion,
  fetchItemOptions,
  fetchAlternativeOptions,
  seenProducts,
  onItemSelect,
  onUpdate,
  onRemove,
  onMove,
}: LineRowProps) {
  const isSet = line.line_type === 'product_set';
  const picked = itemValue(line);
  const selectedItem: SearchableSelectOption | undefined = picked
    ? {
        value: picked,
        label: line.name || line.code,
        description: `${isSet ? 'Set' : 'Product'}${line.code ? ` - ${line.code}` : ''}`,
      }
    : undefined;

  return (
    <>
      <tr className="border-t border-border align-top">
        <td className="px-2 py-2 text-muted-foreground">{index + 1}</td>
        <td className="px-2 py-2">
          <SearchableSelect
            value={picked}
            onChange={() => {
              /* the whole option is what carries the kind; see onOptionChange */
            }}
            onOptionChange={(option) => onItemSelect(line.key, option)}
            fetchOptions={fetchItemOptions}
            selectedOption={selectedItem}
            clearable
            wrapOptions
            placeholder="Search a set or product..."
            emptyMessage="No sets or products match."
          />
        </td>
        <td className="px-2 py-2">
          <Input
            type="number"
            inputMode="numeric"
            min={1}
            value={line.quantity}
            onChange={(e) =>
              onUpdate(line.key, {
                quantity: Math.max(1, parseInt(e.target.value) || 1),
              })
            }
            aria-label={`Quantity for line ${index + 1}`}
          />
        </td>
        <td
          className="px-2 py-2"
          title={
            isSet
              ? 'A set is printed as one thing, so it carries no OR choices.'
              : undefined
          }
        >
          <SearchableMultiSelect
            value={line.alternatives.map((a) => a.product_id)}
            onChange={(selected) => {
              // Keep what the row already knows about a still-selected product,
              // then fall back to what the picker has shown this session, so a
              // chip never reads as a bare id.
              const known = new Map(
                line.alternatives.map((a) => [a.product_id, a]),
              );
              onUpdate(line.key, {
                alternatives: selected.map((pid) => {
                  const held = known.get(pid);
                  if (held) return held;
                  const seen = seenProducts.get(pid);
                  return {
                    product_id: pid,
                    name: seen?.name ?? '',
                    code: seen?.code ?? '',
                  };
                }),
              });
            }}
            fetchOptions={fetchAlternativeOptions}
            selectedOptions={line.alternatives.map((a) => ({
              value: a.product_id,
              label: a.name || a.code,
              description: a.code,
            }))}
            disabled={isSet}
            placeholder={isSet ? 'Not for a set' : 'Search products...'}
            emptyMessage="No products match."
          />
        </td>
        <td className="px-2 py-2">
          <Input
            value={line.included_accessories}
            onChange={(e) =>
              onUpdate(line.key, { included_accessories: e.target.value })
            }
            placeholder="e.g. Soft-close hinges"
            aria-label={`Accessories for line ${index + 1}`}
          />
        </td>
        {hasPromotion && (
          <td className="px-2 py-2">
            <Switch
              checked={line.show_promo_price}
              onCheckedChange={(v) =>
                onUpdate(line.key, { show_promo_price: v })
              }
              aria-label={`Show promo price on line ${index + 1}`}
            />
          </td>
        )}
        <td className="px-2 py-2">
          <div className="flex items-center justify-end gap-0.5">
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={index === 0}
              onClick={() => onMove(index, 'up')}
              title="Move up"
              aria-label={`Move line ${index + 1} up`}
            >
              <ArrowUp className="size-3.5" />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0"
              disabled={index === total - 1}
              onClick={() => onMove(index, 'down')}
              title="Move down"
              aria-label={`Move line ${index + 1} down`}
            >
              <ArrowDown className="size-3.5" />
            </Button>
            {/* No confirm: the row is unsaved form state, not a record. */}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 w-7 p-0 text-destructive"
              onClick={() => onRemove(line.key)}
              title="Remove line"
              aria-label={`Remove line ${index + 1}`}
            >
              <Trash2 className="size-3.5" />
            </Button>
          </div>
        </td>
      </tr>
      {line.guard_error && (
        <tr>
          <td colSpan={hasPromotion ? 7 : 6} className="px-2 pb-2">
            <p className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1.5">
              {line.guard_error}
            </p>
          </td>
        </tr>
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// Read-only detail
// ---------------------------------------------------------------------------

/**
 * Renders a scaled-down proof preview of the tag sheets.
 *
 * Phase 1: builds a mock tag sheet doc from the request lines for demonstration.
 * Phase 2: fetches the actual tag sheet doc from the backend.
 */
function ProofPreviewSection({
  request,
}: {
  request: PriceTagRequestDetail;
}) {
  // Build mock resolved data from the request's lines.
  const resolvedData: Record<string, ResolvedLineData> = {};
  for (const line of request.lines) {
    resolvedData[line.id] = {
      line_id: line.id,
      code: line.code,
      name: line.name,
      dimensions: '',
      spec_lines: '',
      list_price: null,
      sell_price: null,
      show_promo_price: line.show_promo_price,
      included_accessories: line.included_accessories ?? '',
      quantity: line.quantity,
    };
  }

  // Phase 1: build a mock tag sheet doc. Phase 2 fetches the real one.
  const mockDoc: TagSheetDoc = {
    kind: 'tag_sheet',
    imposition: {
      preset: 'a4_3up',
      page_width_mm: 210,
      page_height_mm: 297,
      bleed_mm: 3,
      gap_mm: 2,
    },
    sheets: [
      {
        id: 's1',
        tags: request.lines.map((line, i) => ({
          id: `t${i}`,
          template_id: '',
          request_line_id: line.id,
          x_mm: 10,
          y_mm: 10 + i * 100,
          width_mm: 95,
          height_mm: 90,
          layers: [
            {
              id: `l${i}-name`,
              type: 'text' as const,
              x_mm: 5,
              y_mm: 5,
              width_mm: 85,
              height_mm: 15,
              rotation_deg: 0,
              z_index: 1,
              locked: false,
              visible: true,
              slot_binding: 'name' as const,
              text_override: null,
              props: {
                kind: 'text' as const,
                text: line.name,
                fontFamily: 'DM Sans',
                fontSize: 12,
                fontWeight: 600,
                color: '#000000',
                align: 'left' as const,
                lineHeight: 1.2,
                letterSpacing: 0,
              },
            },
            {
              id: `l${i}-code`,
              type: 'text' as const,
              x_mm: 5,
              y_mm: 22,
              width_mm: 85,
              height_mm: 10,
              rotation_deg: 0,
              z_index: 2,
              locked: false,
              visible: true,
              slot_binding: 'code' as const,
              text_override: null,
              props: {
                kind: 'text' as const,
                text: line.code,
                fontFamily: 'DM Sans',
                fontSize: 9,
                fontWeight: 400,
                color: '#666666',
                align: 'left' as const,
                lineHeight: 1.2,
                letterSpacing: 0,
              },
            },
          ],
        })),
      },
    ],
  };

  return (
    <PriceTagProofViewer doc={mockDoc} resolvedData={resolvedData} />
  );
}

function RequestDetailView({
  request,
}: {
  request: PriceTagRequestDetail;
}) {
  return (
    <>
      {/* Header */}
      <Card>
        <CardContent className="pt-4 space-y-3">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <h2 className="text-lg font-semibold">{request.doc_number}</h2>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${priceTagStatusPillClass(request.status)}`}
            >
              {priceTagStatusLabel(request.status)}
            </span>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-sm">
            <div>
              <span className="text-muted-foreground">Debtor</span>
              <p className="font-medium">{request.debtor_name}</p>
            </div>
            {request.promotion_name && (
              <div>
                <span className="text-muted-foreground">Promotion</span>
                <p className="font-medium">{request.promotion_name}</p>
              </div>
            )}
            <div>
              <span className="text-muted-foreground">Needed by</span>
              <p className="font-medium">{request.needed_by_date}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Created</span>
              <p className="font-medium">
                {new Date(request.created_at).toLocaleDateString()}
              </p>
            </div>
          </div>

          {request.notes && (
            <div>
              <span className="text-sm text-muted-foreground">Notes</span>
              <p className="text-sm mt-1">{request.notes}</p>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Lines */}
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">
            Lines ({request.lines.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          {request.lines.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-4">
              No lines.
            </p>
          ) : (
            <div className="space-y-2">
              {request.lines.map((line) => (
                <div
                  key={line.id}
                  className="border rounded-lg p-3 space-y-1"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant="secondary" className="text-xs">
                      {line.line_type === 'product' ? 'Product' : 'Set'}
                    </Badge>
                    <span className="font-medium text-sm">{line.name}</span>
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    <span>Code: {line.code}</span>
                    <span>Qty: {line.quantity}</span>
                    {line.show_promo_price && (
                      <span className="text-amber-600">Promo price</span>
                    )}
                  </div>
                  {line.alternatives.length > 0 && (
                    <p className="text-xs text-muted-foreground">
                      Alternatives:{' '}
                      {line.alternatives.map((a) => a.name).join(', ')}
                    </p>
                  )}
                  {line.included_accessories && (
                    <p className="text-xs text-muted-foreground">
                      Accessories: {line.included_accessories}
                    </p>
                  )}
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Attachments */}
      {request.attachments.length > 0 && (
        <Card>
          <CardHeader className="py-3 px-4">
            <CardTitle className="text-base">PO Attachments</CardTitle>
          </CardHeader>
          <CardContent className="px-4 pb-4 space-y-1">
            {request.attachments.map((att) => (
              <div
                key={att.id}
                className="flex items-center text-sm px-2 py-1.5 bg-muted rounded"
              >
                <FileText className="size-3.5 mr-2 text-muted-foreground" />
                <span className="truncate" title={att.filename}>
                  {att.filename}
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </>
  );
}
