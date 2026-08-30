'use client';

/**
 * Portal price tag request form - create / edit / view.
 *
 * Wired to real portal API via `price-tag-request-service.ts`.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
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
  ProductOption,
  ProductSetOption,
} from '../lib/price-tag-request-service';
import {
  lookupDebtors,
  lookupPromotions,
  lookupProducts,
  lookupProductSets,
  checkSetGuard,
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

function emptyDraftLine(lineType: 'product' | 'product_set'): DraftLine {
  return {
    key: `draft-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    line_type: lineType,
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
  const [products, setProducts] = useState<ProductOption[]>([]);
  const [productSets, setProductSets] = useState<ProductSetOption[]>([]);

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
    lookupProducts().then(setProducts);
    lookupProductSets().then(setProductSets);
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

  // ---- Product options ----
  const productOptions = useMemo<SearchableSelectOption[]>(
    () =>
      products.map((p) => ({
        value: p.id,
        label: p.name,
        description: p.code,
      })),
    [products],
  );

  // ---- Product set options ----
  const setOptions = useMemo<SearchableSelectOption[]>(
    () =>
      productSets.map((s) => ({
        value: s.id,
        label: s.name,
        description: s.code,
      })),
    [productSets],
  );

  // ---- Alternative product options (exclude already-selected product) ----
  const alternativeOptions = useMemo<SearchableSelectOption[]>(
    () =>
      products.map((p) => ({
        value: p.id,
        label: p.name,
        description: p.code,
      })),
    [products],
  );

  // ---- Line management ----
  const addProductLine = useCallback(() => {
    setLines((prev) => [...prev, emptyDraftLine('product')]);
  }, []);

  const addSetLine = useCallback(() => {
    setLines((prev) => [...prev, emptyDraftLine('product_set')]);
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

  // ---- Set guard on product select ----
  const handleProductSelect = useCallback(
    (key: string, productId: string) => {
      const product = products.find((p) => p.id === productId);
      if (!product) return;

      const guard = checkSetGuard(productId);
      updateLine(key, {
        product_id: productId,
        name: product.name,
        code: product.code,
        guard_error: guard.blocked ? guard.message : null,
      });
    },
    [products, updateLine],
  );

  // ---- Set select ----
  const handleSetSelect = useCallback(
    (key: string, setId: string) => {
      const pSet = productSets.find((s) => s.id === setId);
      if (!pSet) return;
      updateLine(key, {
        product_set_id: setId,
        name: pSet.name,
        code: pSet.code,
        guard_error: null,
      });
    },
    [productSets, updateLine],
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
    } catch {
      toast.error('Failed to save draft');
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
    } catch {
      toast.error('Failed to submit request');
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

      {/* Lines */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between py-3 px-4">
          <CardTitle className="text-base">Lines</CardTitle>
          <div className="flex gap-2">
            <Button size="sm" variant="outline" onClick={addProductLine}>
              <Plus className="size-3.5 mr-1" /> Product
            </Button>
            <Button size="sm" variant="outline" onClick={addSetLine}>
              <Plus className="size-3.5 mr-1" /> Set
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-3 px-4 pb-4">
          {lines.length === 0 && (
            <p className="text-sm text-muted-foreground text-center py-6">
              No lines added. Use the buttons above to add products or sets.
            </p>
          )}
          {lines.map((line, index) => (
            <LineRow
              key={line.key}
              line={line}
              index={index}
              total={lines.length}
              hasPromotion={!!promotionId}
              productOptions={productOptions}
              setOptions={setOptions}
              alternativeOptions={alternativeOptions}
              products={products}
              onProductSelect={handleProductSelect}
              onSetSelect={handleSetSelect}
              onUpdate={updateLine}
              onRemove={removeLine}
              onMove={moveLine}
            />
          ))}
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
  productOptions: SearchableSelectOption[];
  setOptions: SearchableSelectOption[];
  alternativeOptions: SearchableSelectOption[];
  products: ProductOption[];
  onProductSelect: (key: string, productId: string) => void;
  onSetSelect: (key: string, setId: string) => void;
  onUpdate: (key: string, patch: Partial<DraftLine>) => void;
  onRemove: (key: string) => void;
  onMove: (index: number, direction: 'up' | 'down') => void;
}

function LineRow({
  line,
  index,
  total,
  hasPromotion,
  productOptions,
  setOptions,
  alternativeOptions,
  products,
  onProductSelect,
  onSetSelect,
  onUpdate,
  onRemove,
  onMove,
}: LineRowProps) {
  return (
    <div className="border rounded-lg p-3 space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Badge variant="secondary" className="text-xs">
            {line.line_type === 'product' ? 'Product' : 'Set'}
          </Badge>
          {line.code && (
            <span className="text-xs text-muted-foreground">{line.code}</span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            disabled={index === 0}
            onClick={() => onMove(index, 'up')}
          >
            <ArrowUp className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0"
            disabled={index === total - 1}
            onClick={() => onMove(index, 'down')}
          >
            <ArrowDown className="size-3.5" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 w-7 p-0 text-destructive"
            onClick={() => onRemove(line.key)}
          >
            <Trash2 className="size-3.5" />
          </Button>
        </div>
      </div>

      {/* Product / Set picker */}
      {line.line_type === 'product' ? (
        <div className="space-y-1.5">
          <Label className="text-xs">Product</Label>
          <SearchableSelect
            value={line.product_id ?? ''}
            onChange={(v) => onProductSelect(line.key, v)}
            options={productOptions}
            placeholder="Select product..."
          />
        </div>
      ) : (
        <div className="space-y-1.5">
          <Label className="text-xs">Product Set</Label>
          <SearchableSelect
            value={line.product_set_id ?? ''}
            onChange={(v) => onSetSelect(line.key, v)}
            options={setOptions}
            placeholder="Select set..."
          />
        </div>
      )}

      {/* Set guard error */}
      {line.guard_error && (
        <p className="text-xs text-destructive bg-destructive/10 rounded px-2 py-1.5">
          {line.guard_error}
        </p>
      )}

      {/* Quantity */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="space-y-1.5 flex-1">
          <Label className="text-xs">Quantity (tags)</Label>
          <Input
            type="number"
            min={1}
            value={line.quantity}
            onChange={(e) =>
              onUpdate(line.key, {
                quantity: Math.max(1, parseInt(e.target.value) || 1),
              })
            }
            className="w-24"
          />
        </div>

        {/* Show promo price toggle */}
        {hasPromotion && (
          <div className="flex items-center gap-2">
            <Switch
              checked={line.show_promo_price}
              onCheckedChange={(v) =>
                onUpdate(line.key, { show_promo_price: v })
              }
            />
            <Label className="text-xs">Show promo price</Label>
          </div>
        )}
      </div>

      {/* Alternatives (product lines only) */}
      {line.line_type === 'product' && (
        <div className="space-y-1.5">
          <Label className="text-xs">Alternatives (OR choices)</Label>
          <SearchableMultiSelect
            value={line.alternatives.map((a) => a.product_id)}
            onChange={(selected) => {
              const alts = selected
                .map((pid) => {
                  const p = products.find((pr) => pr.id === pid);
                  return p
                    ? { product_id: p.id, name: p.name, code: p.code }
                    : null;
                })
                .filter(Boolean) as DraftLine['alternatives'];
              onUpdate(line.key, { alternatives: alts });
            }}
            options={alternativeOptions.filter(
              (o) => o.value !== line.product_id,
            )}
            placeholder="Select alternatives..."
          />
        </div>
      )}

      {/* Accessories */}
      <div className="space-y-1.5">
        <Label className="text-xs">Accessories</Label>
        <Input
          value={line.included_accessories}
          onChange={(e) =>
            onUpdate(line.key, { included_accessories: e.target.value })
          }
          placeholder="e.g. Soft-close hinges, mirror clips"
        />
      </div>
    </div>
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
