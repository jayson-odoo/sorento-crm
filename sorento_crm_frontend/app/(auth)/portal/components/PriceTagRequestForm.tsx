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
  Copy,
  Download,
  FileText,
  Loader2,
  MessageSquare,
  Plus,
  Trash2,
} from 'lucide-react';
import { toast } from '@/lib/toast';
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
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { FormSection } from './FormSection';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import {
  priceTagStatusLabel,
  priceTagStatusPillClass,
} from '@/lib/price-tag-status';
import { portalBase, portalDuplicatePath } from '../lib/portal-paths';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLine,
  DebtorOption,
  PromotionOption,
  PriceMode,
  TagItemOption,
} from '../lib/price-tag-request-service';
import {
  lookupDebtors,
  lookupPromotions,
  lookupTagItems,
  getRequest,
  createRequest,
  updateRequest,
  deleteRequest,
  submitRequest,
  approveRequest,
  requestChanges,
  downloadPriceTagPdf,
} from '../lib/price-tag-request-service';
import PriceTagProofViewer from './PriceTagProofViewer';
import POCrossCheckViewer from './POCrossCheckViewer';
import { AttachmentDropzone } from './AttachmentDropzone';
import {
  AIExtractDialog,
  type AIExtractApplyPayload,
} from './AIExtractDialog';
import type { AIExtractedProductLine } from '../lib/portal-client';
import AttachmentPreviewModal from '@/components/common/AttachmentPreviewModal';
import { toPreviewItem, portalFetchBytes } from '../lib/portal-preview';
import {
  uploadAttachment,
  getPriceTagDesign,
  type PortalAttachment,
} from '../lib/portal-client';
import type { ResolvedLineData } from '@/app/(public)/c/print/tag-sheet/[downloadId]/components/TagSheetRenderer';
import type { TagSheetDoc } from '@/lib/dealer-kit/tag-template-types';
import { cn } from '@/lib/utils';

/** Where an AI-extracted product line stands against the catalogue lookup
 *  (D7/AC-S6-2), shown in the extract dialog's own result table. */
type AIMatchStatus = 'loading' | 'matched_product' | 'matched_set' | 'not_found';

// ---------------------------------------------------------------------------
// Draft line (client-side, before persisting)
// ---------------------------------------------------------------------------

// D-P1: the four sections, top to bottom, on both the edit form and the
// read-only view.
type SectionKey = 'customer' | 'sales_order' | 'price' | 'need_by';

interface DraftLine {
  key: string; // client-side key for React
  line_type: 'product' | 'product_set';
  product_id: string | null;
  product_set_id: string | null;
  name: string;
  code: string;
  quantity: number;
  alternatives: { product_id: string; name: string; code: string }[];
  included_accessories: string;
  /** Free-text note on the line (D6). */
  remarks: string;
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
    quantity: 1,
    alternatives: [],
    included_accessories: '',
    remarks: '',
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
    // show_promo_price is read-only server state, not form state: it is
    // derived from the header's price_mode on every save (D5), so the draft
    // never carries or resends it (review fix).
    quantity: line.quantity,
    alternatives: line.alternatives,
    included_accessories: line.included_accessories ?? '',
    remarks: line.remarks ?? '',
    guard_error: null,
  };
}

// ---------------------------------------------------------------------------
// What Submit says when something is missing (D48b)
//
// One sentence per problem, written where the problem is. The wording names the
// next action rather than the rule, because the salesperson is mid-form, not
// reading a spec.
// ---------------------------------------------------------------------------

const MISSING_DEBTOR = 'Select the dealer these tags are for.';
const MISSING_DEADLINE = 'Pick the date you need them by.';
const MISSING_LINES = 'Add at least one line.';
const EMPTY_LINE = 'Pick a set or a product for this line.';

/** Statuses the real design (D11) is visible at, once one exists to show. */
const DESIGN_PREVIEW_STATUSES = new Set([
  'proof_ready',
  'changes_requested',
  'approved',
  'ready',
]);

/**
 * The field keys a refusal named, if it named any.
 *
 * Duck-typed rather than `instanceof PriceTagRequestError`: the error crosses a
 * module boundary and the only thing that matters is whether it carries the
 * list.
 */
function errorFields(e: unknown): string[] {
  const fields = (e as { fields?: unknown } | null)?.fields;
  if (!Array.isArray(fields)) return [];
  return fields.filter((f): f is string => typeof f === 'string');
}

/** Bring the first complaint into view, after the render that drew it. */
function scrollToFirstProblem(): void {
  setTimeout(() => {
    const node = document.querySelector('[data-error-anchor]');
    node?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
  }, 50);
}

// ---------------------------------------------------------------------------
// Minimum deadline: today + 1 business day
//
// The `min` of the date input only. The field itself starts EMPTY: a deadline
// nobody chose is not an answer, and since D48a a draft is allowed to have none.
// Submit asks for it by name.
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
  // The id a create call answered with, held in STATE rather than trusted to
  // live only in the `requestId` prop (the route param) - a retry after
  // create-succeeded-but-flushPendingFiles-failed never gets a fresh prop, so
  // without this the next Save Draft/Submit click saw `isNew` again and
  // created a second row for the same draft.
  const [createdRequestId, setCreatedRequestId] = useState<string | null>(null);

  // ---- Lookup data ----
  const [debtors, setDebtors] = useState<DebtorOption[]>([]);
  /** True once the debtor lookup has ANSWERED. An empty list before it has is
   *  just "not back yet", and must not read as "you are not linked". */
  const [debtorsLoaded, setDebtorsLoaded] = useState(false);
  const [promotions, setPromotions] = useState<PromotionOption[]>([]);

  // ---- Form state ----
  const [debtorCode, setDebtorCode] = useState('');
  const [promotionId, setPromotionId] = useState<string>('');
  // Header price mode (D5): replaces the per-line "Promo price" switch.
  // Selling requires a promotion, so clearing the promotion while Selling is
  // chosen flips the control back to List price.
  const [priceMode, setPriceMode] = useState<PriceMode>('list');
  const [neededByDate, setNeededByDate] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [attachments, setAttachments] = useState<PortalAttachment[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);

  // ---- AI extract sales order lines (D7, per-file per D-P3) ----
  const [aiExtractOpen, setAiExtractOpen] = useState(false);
  // Set the moment a tile's own Extract action is tapped, so the dialog opens
  // straight on that one file's results (D-P3) instead of the upload stage.
  const [aiExtractFiles, setAiExtractFiles] = useState<File[] | undefined>(
    undefined,
  );
  // Per-row match state for the CURRENT extraction, indexed the same as the
  // dialog's own `result.products` - populated as each code resolves so the
  // dialog can show "Not found" before Apply is even clicked (AC-S6-2), and
  // read again by the apply handler so it never re-looks-up what this
  // already knows.
  const [aiMatchStatuses, setAiMatchStatuses] = useState<AIMatchStatus[]>([]);
  const aiMatchesRef = useRef<(TagItemOption | null)[]>([]);

  // ---- Proof review state ----
  const [changesNote, setChangesNote] = useState('');
  const [showChangesDialog, setShowChangesDialog] = useState(false);

  // ---- Delete draft ----
  const [deleting, setDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  // ---- Read-only view: PO attachment preview + Download PDF (D19/S2) ----
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [gearOpen, setGearOpen] = useState(false);

  // ---- What Submit found wrong, where it found it (D48b) ----
  // Set by a Submit click and by a server refusal that named a field; cleared
  // field by field as each one is answered.
  const [fieldErrors, setFieldErrors] = useState<{
    debtor?: string;
    neededBy?: string;
    lines?: string;
  }>({});
  const [serverMessage, setServerMessage] = useState<string | null>(null);

  // A draft is `portal_draft_at`, not a status: a draft's status is `new`, the
  // same status a submitted request keeps until marketing claims it. Checking
  // the status for 'draft' matched nothing, so re-opening a saved draft showed
  // the read-only page instead of the form.
  const isDraft = Boolean(request?.portal_draft_at);
  const isEditable = isNew || isDraft;
  const isProofReady = request?.status === 'proof_ready';
  // The design preview shows for longer than the approve/request-changes
  // actions do (D11/AC-S4-4): once approved the salesperson can still look
  // at what they approved, but Approve/Request Changes only make sense while
  // the design is actually waiting on them.
  const showDesignPreview = !!request && DESIGN_PREVIEW_STATUSES.has(request.status);
  // The id to save/flush against: the route param when one exists, else
  // whatever a create call in THIS session already answered with.
  const effectiveId = requestId ?? createdRequestId ?? undefined;

  // ---- Sections (D-P1): Customer open by default, everything else opens
  // progressively as the form gains the value the next section needs. A rule
  // fires once per section per form load; a section the user collapsed by
  // hand (tracked in the same ref) is never reopened by a rule.
  const [sectionOpen, setSectionOpen] = useState<Record<SectionKey, boolean>>({
    customer: true,
    sales_order: false,
    price: false,
    need_by: false,
  });
  const sectionSettledRef = useRef<Set<SectionKey>>(new Set());
  // Whether the price mode reflects a real pick (a click, or a prefilled/
  // loaded value) rather than just its 'list' default at mount - the default
  // must not itself open Additional Information on a blank new form.
  const priceModeChosenRef = useRef(false);

  const openSectionOnce = useCallback((key: SectionKey) => {
    if (sectionSettledRef.current.has(key)) return;
    sectionSettledRef.current.add(key);
    setSectionOpen((prev) => (prev[key] ? prev : { ...prev, [key]: true }));
  }, []);

  const toggleSection = useCallback((key: SectionKey, next: boolean) => {
    sectionSettledRef.current.add(key);
    setSectionOpen((prev) => ({ ...prev, [key]: next }));
  }, []);

  // Picking a customer opens Sales Order & Lines (AC-P3).
  useEffect(() => {
    if (debtorCode) openSectionOnce('sales_order');
  }, [debtorCode, openSectionOnce]);

  // The first line (AI or Add line) opens Price (AC-P7).
  useEffect(() => {
    if (lines.length > 0) openSectionOnce('price');
  }, [lines.length, openSectionOnce]);

  // A chosen price mode opens Additional Information (AC-P8); Selling only
  // counts once it and a promotion are both there is not required - Selling
  // alone is enough (D-P2, submit works with no promotion).
  useEffect(() => {
    if (!priceModeChosenRef.current) return;
    if (priceMode === 'list' || priceMode === 'selling') {
      openSectionOnce('need_by');
    }
  }, [priceMode, openSectionOnce]);

  const selectedDebtorName = useMemo(
    () => debtors.find((d) => d.code === debtorCode)?.name ?? null,
    [debtors, debtorCode],
  );
  const selectedPromotionName = useMemo(
    () => promotions.find((p) => p.id === promotionId)?.name ?? null,
    [promotions, promotionId],
  );
  const fileCount = attachments.length + pendingFiles.length;

  // Collapsed-header one-liners (AC-P9); empty sections show none.
  const sectionSummaries: Record<SectionKey, string | null> = {
    customer: selectedDebtorName,
    sales_order:
      lines.length > 0 || fileCount > 0
        ? `${lines.length} line${lines.length === 1 ? '' : 's'}, ${fileCount} file${fileCount === 1 ? '' : 's'}`
        : null,
    price:
      priceMode === 'selling'
        ? `Selling price${selectedPromotionName ? ` - ${selectedPromotionName}` : ''}`
        : 'List price',
    need_by:
      neededByDate || notes.trim()
        ? [neededByDate || null, notes.trim() ? 'notes' : null]
            .filter(Boolean)
            .join(' - ')
        : null,
  };

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
        setPriceMode(data.price_mode ?? 'list');
        // A loaded request already has a real price mode, not the blank
        // form's resting default - so a later mode click is free to act on
        // it (AC-P8). Also open every section that already holds a value
        // directly (AC-P11): a `setPriceMode('list')` here is a no-op when
        // the mode was already 'list' at mount, so the reactive rule alone
        // would never see it change and never fire.
        priceModeChosenRef.current = true;
        // Both are nullable on a draft (D48a): an empty input, not a crash.
        setNeededByDate(data.needed_by_date ?? '');
        setNotes(data.notes ?? '');
        setLines(data.lines.map(lineToDraft));
        setAttachments(data.attachments ?? []);
        if (data.debtor_code) openSectionOnce('sales_order');
        if (data.lines.length > 0) openSectionOnce('price');
        openSectionOnce('need_by');
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
    // router.back() only fires on a 404, and Next's router is stable across
    // renders regardless; omitted so a fresh-object router mock cannot force
    // an unrelated re-render into a refetch loop.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestId]);

  // ---- Duplicate (D-D1): `?from=<id>` copies header fields + lines into a
  // NEW draft. Attachments stay empty (Sales Order files are not copied);
  // nothing is saved until Save draft / Submit. A source this contact does
  // not own, or that no longer exists, falls back to a toast + empty form.
  useEffect(() => {
    if (!isNew || typeof window === 'undefined') return;
    const fromId = new URL(window.location.href).searchParams.get('from');
    if (!fromId || !fromId.trim()) return;
    let cancelled = false;
    getRequest(fromId.trim())
      .then((data) => {
        if (cancelled || !data) {
          if (!cancelled) toast.error('Could not copy that submission.');
          return;
        }
        setDebtorCode(data.debtor_code ?? '');
        setPromotionId(data.promotion_id ?? '');
        setPriceMode(data.price_mode ?? 'list');
        priceModeChosenRef.current = true;
        setNeededByDate(data.needed_by_date ?? '');
        setNotes(data.notes ?? '');
        setLines(data.lines.map(lineToDraft));
        // AC-D3: Customer, Sales Order & Lines and Price open because they
        // hold values; Additional Information opens too (same no-op-state
        // reasoning as the load-existing-request effect above).
        if (data.debtor_code) openSectionOnce('sales_order');
        if (data.lines.length > 0) openSectionOnce('price');
        openSectionOnce('need_by');
      })
      .catch(() => {
        if (!cancelled) toast.error('Could not copy that submission.');
      });
    return () => {
      cancelled = true;
    };
  }, [isNew, openSectionOnce]);

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

  // ---- AI extract sales order lines (D7) ----
  //
  // Fires when the dialog moves to Review, so a row can already read "Not
  // found" before Apply is clicked (AC-S6-2). Matches by exact code, trimmed
  // and case-insensitive, against the SAME lookup the Item picker above
  // uses - one call per code, which is fine for a sales order's page count.
  const handleAIExtracted = useCallback(
    (products: AIExtractedProductLine[]) => {
      setAiMatchStatuses(products.map(() => 'loading'));
      aiMatchesRef.current = products.map(() => null);
      products.forEach((p, index) => {
        const code = (p.product_code ?? '').trim();
        const lookup = code ? lookupTagItems(code) : Promise.resolve([]);
        lookup
          .then((items) => {
            const match =
              items.find(
                (i) => i.code.trim().toLowerCase() === code.toLowerCase(),
              ) ?? null;
            aiMatchesRef.current[index] = match;
            setAiMatchStatuses((prev) => {
              const next = [...prev];
              next[index] = match
                ? match.kind === 'product_set'
                  ? 'matched_set'
                  : 'matched_product'
                : 'not_found';
              return next;
            });
          })
          .catch(() => {
            aiMatchesRef.current[index] = null;
            setAiMatchStatuses((prev) => {
              const next = [...prev];
              next[index] = 'not_found';
              return next;
            });
          });
      });
    },
    [],
  );

  /** Apply = append one line per matched row (D7). unit_price is shown in the
   *  dialog only and is never stored (ADR 0008) - no field in `DraftLine`
   *  reads it. Reads the SAME matches `handleAIExtracted` already resolved,
   *  rather than looking every code up a second time. */
  const handleAIExtractApply = useCallback((payload: AIExtractApplyPayload) => {
    const matches = aiMatchesRef.current;
    const newLines: DraftLine[] = [];
    const notFoundCodes: string[] = [];
    payload.productLines.forEach((p, index) => {
      const match = matches[index];
      const code = (p.product_code ?? '').trim();
      if (!match) {
        if (code) notFoundCodes.push(code);
        return;
      }
      const qty = p.quantity != null ? Math.max(1, Math.round(p.quantity)) : 1;
      newLines.push({
        key: `draft-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 8)}`,
        line_type: match.kind,
        product_id: match.kind === 'product' ? match.id : null,
        product_set_id: match.kind === 'product_set' ? match.id : null,
        name: match.name || match.code,
        code: match.code,
        quantity: qty,
        alternatives: [],
        included_accessories: '',
        remarks: p.notes ?? '',
        guard_error: null,
      });
    });
    if (newLines.length > 0) {
      setLines((prev) => [...prev, ...newLines]);
      toast.success(
        `Added ${newLines.length} line${newLines.length === 1 ? '' : 's'} from the sales order.`,
      );
    }
    if (notFoundCodes.length > 0) {
      toast.error(`Not found: ${notFoundCodes.join(', ')}`);
    }
    // The dialog's own alsoAttach checkbox (checked by default): the file(s)
    // read for extraction join the SAME pending/flush path a Sales Order
    // drop uses, so Save Draft/Submit upload them once - not here, and not
    // twice.
    if (payload.alsoAttach && payload.files.length > 0) {
      setPendingFiles((prev) => [...prev, ...payload.files]);
    }
  }, []);

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

  // ---- What there is to save, and what Submit still needs (D48) ----

  /** Save Draft asks for one thing only: that there is something to save. A
   *  dropped PO file with nothing else filled in still counts (AC-S1-2) - it is
   *  parked in `pendingFiles` waiting on a draft id to upload to, and Save Draft
   *  is the only way to give it one. */
  const hasSomethingToSave =
    !!debtorCode ||
    !!promotionId ||
    !!neededByDate ||
    notes.trim().length > 0 ||
    lines.length > 0 ||
    pendingFiles.length > 0;

  const payloadLines = () =>
    lines.map((l) => ({
      line_type: l.line_type,
      product_id: l.product_id,
      product_set_id: l.product_set_id,
      quantity: l.quantity,
      alternatives: l.alternatives,
      included_accessories: l.included_accessories || null,
      remarks: l.remarks || null,
      product_class: null,
    }));

  /** The keys the form and the server both use to place a message. A server
   *  refusal answers with the same vocabulary (`line:<index>` for a row), so
   *  one mapping serves both. */
  const applyFieldErrors = useCallback(
    (keys: string[], rowMessage: string) => {
      const next: { debtor?: string; neededBy?: string; lines?: string } = {};
      const rows = new Set<number>();
      for (const key of keys) {
        if (key === 'debtor_name' || key === 'debtor_code') {
          next.debtor = MISSING_DEBTOR;
        } else if (key === 'needed_by_date') {
          next.neededBy = MISSING_DEADLINE;
        } else if (key === 'lines') {
          next.lines = MISSING_LINES;
        } else if (key.startsWith('line:')) {
          const index = Number(key.slice('line:'.length));
          if (Number.isInteger(index)) rows.add(index);
        }
      }
      setFieldErrors(next);
      if (rows.size > 0) {
        setLines((prev) =>
          prev.map((l, index) => ({
            ...l,
            guard_error: rows.has(index) ? rowMessage : null,
          })),
        );
      }
      return Object.keys(next).length + rows.size;
    },
    [],
  );

  /** Everything Submit can see wrong from here, reported at once. Need by is
   *  optional (D-P2b) - only a server refusal can still name it, until the
   *  backend rule drops too. */
  const collectProblems = useCallback(() => {
    const next: { debtor?: string; neededBy?: string; lines?: string } = {};
    if (!debtorCode) next.debtor = MISSING_DEBTOR;
    if (lines.length === 0) next.lines = MISSING_LINES;
    const emptyRows = lines
      .map((l, index) => (l.product_id || l.product_set_id ? -1 : index))
      .filter((index) => index >= 0);
    return { next, emptyRows };
  }, [debtorCode, lines]);

  /** How many things the form is currently complaining about, for the one line
   *  above the actions. */
  const problemCount =
    Object.keys(fieldErrors).length + lines.filter((l) => l.guard_error).length;

  // Answering a field clears its message; leaving it red after it is filled in
  // is the same failure as not showing one at all.
  useEffect(() => {
    setFieldErrors((prev) => {
      if (!prev.debtor && !prev.neededBy && !prev.lines) return prev;
      const next = { ...prev };
      if (next.debtor && debtorCode) delete next.debtor;
      if (next.neededBy && neededByDate) delete next.neededBy;
      if (next.lines && lines.length > 0) delete next.lines;
      return next;
    });
  }, [debtorCode, neededByDate, lines.length]);

  // D-P2 (owner ruling): Selling with no promotion is a valid end state now -
  // clearing the promotion no longer flips the mode back to List. Switching
  // TO List is the only thing that clears the promotion (in the button's own
  // onClick below), so an emptied field never leaves a stale id behind.

  // ---- PO attachments: buffer pre-draft, flush once the draft exists ----
  //
  // The legacy SubmissionForm pattern (D2): a file dropped before Save Draft or
  // Submit is held in `pendingFiles` (nothing to upload TO yet) and uploaded the
  // moment the draft is created. A file that fails names itself in the thrown
  // error and stays in `pendingFiles`, so Save Draft / Submit refuse to look
  // like they finished cleanly.
  const flushPendingFiles = useCallback(
    async (id: string) => {
      if (pendingFiles.length === 0) return;
      const uploaded: PortalAttachment[] = [];
      const remaining: File[] = [];
      const errors: string[] = [];
      for (const file of pendingFiles) {
        try {
          const att = await uploadAttachment('price_tag_request', id, file);
          uploaded.push(att);
        } catch (e) {
          const msg = e instanceof Error ? e.message : 'unknown error';
          errors.push(`${file.name}: ${msg}`);
          remaining.push(file);
        }
      }
      if (uploaded.length > 0) setAttachments((prev) => [...prev, ...uploaded]);
      setPendingFiles(remaining);
      if (errors.length > 0) {
        throw new Error(
          `${errors.length} attachment${errors.length > 1 ? 's' : ''} failed: ${errors.join('; ')}`,
        );
      }
    },
    [pendingFiles],
  );

  // ---- Save draft (D48a: validates nothing) ----
  const handleSaveDraft = useCallback(async () => {
    setSaving(true);
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      const payload = {
        debtor_code: debtorCode || null,
        debtor_name: debtorCode ? (debtor?.name ?? debtorCode) : null,
        promotion_id: promotionId || null,
        needed_by_date: neededByDate || null,
        notes: notes || null,
        price_mode: priceMode,
        lines: payloadLines(),
      };
      // An open draft is UPDATED, not created again: saving twice used to leave
      // the salesperson with two rows and no way to tell them apart - and so
      // does a RETRY after the create half of a previous attempt succeeded
      // but the attachment flush after it failed, which is why this checks
      // `effectiveId` (state) rather than only the `requestId` prop.
      const saved = effectiveId
        ? await updateRequest(effectiveId, payload)
        : await createRequest(payload);
      if (!effectiveId) setCreatedRequestId(saved.id);
      await flushPendingFiles(saved.id);
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [effectiveId, debtorCode, debtors, promotionId, priceMode, neededByDate, notes, lines, flushPendingFiles, router, slug]);

  // ---- Delete draft ----
  const handleDeleteDraft = useCallback(async () => {
    if (!requestId) return;
    setDeleting(true);
    try {
      await deleteRequest(requestId);
      toast.success('Draft deleted');
      router.push(`${portalBase(slug)}?type=price_tag_request`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to delete draft');
    } finally {
      setDeleting(false);
      setShowDeleteDialog(false);
    }
  }, [requestId, router, slug]);

  // ---- Submit (D48b: the button is live, the click explains itself) ----
  const handleSubmit = useCallback(async () => {
    const { next, emptyRows } = collectProblems();
    if (Object.keys(next).length > 0 || emptyRows.length > 0) {
      setServerMessage(null);
      setFieldErrors(next);
      setLines((prev) =>
        prev.map((l, index) => ({
          ...l,
          guard_error: emptyRows.includes(index) ? EMPTY_LINE : null,
        })),
      );
      scrollToFirstProblem();
      return;
    }

    setSubmitting(true);
    setServerMessage(null);
    setFieldErrors({});
    setLines((prev) => prev.map((l) => ({ ...l, guard_error: null })));
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      const payload = {
        debtor_code: debtorCode,
        debtor_name: debtor?.name ?? debtorCode,
        promotion_id: promotionId || null,
        needed_by_date: neededByDate,
        notes: notes || null,
        price_mode: priceMode,
        lines: payloadLines(),
      };
      // Same reasoning as Save Draft: a retry after a create succeeded but the
      // attachment flush after it failed must update that row, not create a
      // second one.
      const created = effectiveId
        ? await updateRequest(effectiveId, payload)
        : await createRequest(payload);
      if (!effectiveId) setCreatedRequestId(created.id);
      await flushPendingFiles(created.id);
      await submitRequest(created.id);
      toast.success('Request submitted');
      router.push(`${portalBase(slug)}?type=price_tag_request`);
    } catch (e) {
      // A refusal that named a field or a row goes THERE, once: the summary then
      // says how many things need attention and nothing more, because the same
      // sentence in two places reads as two problems. A refusal that named
      // nothing we recognise has nowhere to go but the summary and the toast,
      // which is where every other failure lands.
      const message = e instanceof Error ? e.message : 'Failed to submit request';
      const named = errorFields(e);
      const placed = named.length > 0 ? applyFieldErrors(named, message) : 0;
      if (placed > 0) {
        setServerMessage(null);
        scrollToFirstProblem();
      } else {
        setServerMessage(message);
        toast.error(message);
      }
    } finally {
      setSubmitting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collectProblems, applyFieldErrors, effectiveId, debtorCode, debtors, promotionId, priceMode, neededByDate, notes, lines, flushPendingFiles, router, slug]);

  // ---- Approve proof ----
  const handleApprove = useCallback(async () => {
    if (!requestId) return;
    try {
      await approveRequest(requestId);
      toast.success('Design approved');
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

  // ---- Download PDF (D19): the request's latest completed tag sheet export ----
  const handleDownloadPdf = useCallback(async () => {
    if (!requestId) return;
    setDownloadingPdf(true);
    try {
      await downloadPriceTagPdf(requestId);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to download the PDF');
    } finally {
      setDownloadingPdf(false);
      // Close the gear once the download has settled (success or failure) -
      // a failure still toasts, so nothing is lost by not leaving it open.
      setGearOpen(false);
    }
  }, [requestId]);

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

  // ---- Read-only view (ADR: View = Edit) ----
  //
  // Every non-editable status - including proof-ready - renders the SAME
  // sections in the SAME order as the edit form below (debtor, promotion,
  // needed-by, notes, lines table, PO attachments), each input swapped in
  // place for its read-only value (AC-S2-1). Proof-ready appends the proof
  // section beneath it (AC-S2-2); `RequestDetailView` no longer exists as a
  // separate layout.
  if (request && !isEditable) {
    const attachmentPreviewItems = attachments.map(toPreviewItem);

    return (
      <div className="w-full max-w-5xl mx-auto px-3 pt-4 pb-8 space-y-4">
        <div className="flex items-center justify-between gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => router.push(`${portalBase(slug)}?type=price_tag_request`)}
          >
            <ArrowLeft className="size-4 mr-1" /> Back
          </Button>
          {/* The gear (D19): Download PDF, disabled with a reason until a
              completed export exists. The stub toast is gone. Controlled open
              state so the menu closes itself once the download settles,
              instead of sitting open with a stale item until an outside
              click. */}
          <DetailActionsMenu
            ariaLabel="Price tag request actions"
            open={gearOpen}
            onOpenChange={setGearOpen}
          >
            <DropdownMenuItem
              disabled={!request.has_completed_export || downloadingPdf}
              onSelect={(event) => {
                event.preventDefault();
                void handleDownloadPdf();
              }}
            >
              {downloadingPdf ? (
                <Loader2 className="size-4 animate-spin" />
              ) : (
                <Download className="size-4" />
              )}
              <span className="flex flex-col items-start">
                <span>{downloadingPdf ? 'Downloading...' : 'Download PDF'}</span>
                {!request.has_completed_export && !downloadingPdf && (
                  <span className="text-xs text-muted-foreground">
                    No completed export yet
                  </span>
                )}
              </span>
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={(event) => {
                event.preventDefault();
                setGearOpen(false);
                router.push(portalDuplicatePath('price_tag_request', request.id, slug));
              }}
            >
              <Copy className="size-4" />
              Duplicate
            </DropdownMenuItem>
          </DetailActionsMenu>
        </div>

        <div className="space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold">{request.doc_number}</h1>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold ${priceTagStatusPillClass(request.status)}`}
            >
              {priceTagStatusLabel(request.status)}
            </span>
          </div>
          {/* Read-only metadata, never a form field: created is derived, not
              something the salesperson typed. */}
          <p className="text-xs text-muted-foreground">
            Created {new Date(request.created_at).toLocaleDateString()}
          </p>
        </div>

        {/* Same four sections as the edit form, same order, all open by
            default (AC-P11) - headers still toggle, there is just no rule
            here to reopen one a reader collapses. */}
        <FormSection
          title="Customer"
          summary={sectionSummaries.customer}
          open={sectionOpen.customer}
          onOpenChange={(next) => toggleSection('customer', next)}
        >
          <div className="space-y-1.5">
            <Label>Customer</Label>
            <p className="text-sm font-medium py-2">
              {request.debtor_name ?? '-'}
            </p>
          </div>
        </FormSection>

        <FormSection
          title="Sales Order & Lines"
          summary={sectionSummaries.sales_order}
          open={sectionOpen.sales_order}
          onOpenChange={(next) => toggleSection('sales_order', next)}
        >
          {/* Sales Order - the files the salesperson attached, openable in
              place. Always rendered, empty state when there are none, so a
              reader never wonders whether the section has one at all. */}
          <div className="space-y-1.5">
            <Label>Sales Order</Label>
            {attachments.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">
                No sales order files attached.
              </p>
            ) : (
              <div className="space-y-1">
                {attachments.map((att, idx) => (
                  <button
                    key={att.link_id}
                    type="button"
                    onClick={() => {
                      setPreviewIndex(idx);
                      setPreviewOpen(true);
                    }}
                    className="flex w-full items-center text-sm px-2 py-1.5 bg-muted rounded hover:bg-muted/70 transition-colors text-left"
                  >
                    <FileText className="size-3.5 mr-2 text-muted-foreground shrink-0" />
                    <span
                      className="truncate"
                      title={att.filename ?? undefined}
                    >
                      {att.filename || 'Attachment'}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Lines: same table the edit form uses, cells read-only. */}
          <div className="space-y-1.5">
            <Label>Lines ({request.lines.length})</Label>
            {request.lines.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No lines.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] table-fixed text-sm">
                  <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                    <tr>
                      <th className="w-10 px-2 py-2 text-left">#</th>
                      <th className="w-[45%] px-2 py-2 text-left">Item</th>
                      <th className="w-[15%] px-2 py-2 text-left">
                        Qty (tags)
                      </th>
                      <th className="w-[40%] px-2 py-2 text-left">Remarks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {request.lines.map((line, index) => (
                      <tr
                        key={line.id}
                        className="border-t border-border align-top"
                      >
                        <td className="px-2 py-2 text-muted-foreground">
                          {index + 1}
                        </td>
                        <td className="px-2 py-2">
                          <div
                            className="font-medium truncate"
                            title={line.name}
                          >
                            {line.name}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {line.line_type === 'product' ? 'Product' : 'Set'}
                            {line.code ? ` - ${line.code}` : ''}
                          </div>
                        </td>
                        <td className="px-2 py-2">{line.quantity}</td>
                        <td
                          className="px-2 py-2 text-muted-foreground truncate"
                          title={line.remarks ?? undefined}
                        >
                          {line.remarks || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </FormSection>

        <FormSection
          title="Price"
          summary={sectionSummaries.price}
          open={sectionOpen.price}
          onOpenChange={(next) => toggleSection('price', next)}
        >
          <div className="space-y-1.5">
            <Label>Price</Label>
            <p className="text-sm font-medium py-2">
              {(request.price_mode ?? 'list') === 'selling'
                ? 'Selling price'
                : 'List price'}
            </p>
          </div>
          {(request.price_mode ?? 'list') === 'selling' && (
            <div className="space-y-1.5">
              <Label>Promotion</Label>
              <p className="text-sm font-medium py-2">
                {request.promotion_name ?? '-'}
              </p>
            </div>
          )}
        </FormSection>

        <FormSection
          title="Additional Information"
          summary={sectionSummaries.need_by}
          open={sectionOpen.need_by}
          onOpenChange={(next) => toggleSection('need_by', next)}
        >
          <div className="space-y-1.5">
            <Label>Need by</Label>
            <p className="text-sm font-medium py-2">
              {request.needed_by_date ?? '-'}
            </p>
          </div>
          <div className="space-y-1.5">
            <Label>Notes</Label>
            <p className="text-sm py-2">
              {request.notes || (
                <span className="text-muted-foreground">No notes.</span>
              )}
            </p>
          </div>
        </FormSection>

        <AttachmentPreviewModal
          open={previewOpen}
          onOpenChange={setPreviewOpen}
          items={attachmentPreviewItems}
          startIndex={previewIndex}
          fetchBytes={portalFetchBytes}
        />

        {/* Design preview appends beneath the same layout (AC-S2-2); nothing
            below here renders for a plain read-only status. It shows for
            longer than the review actions do (D11/AC-S4-4). */}
        {showDesignPreview && <ProofPreviewSection request={request} />}

        {isProofReady && (
          <>
            {/* Same `attachments` state the Sales Order card above reads
                (not `request.attachments`, which is only ever the snapshot
                from the initial fetch) - one source, so the two can never
                show a different file list for the same request. */}
            <POCrossCheckViewer
              attachments={attachments}
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
                <CardTitle className="text-base">Design Review</CardTitle>
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
                    Describe what needs to be changed. The marketing team will
                    revise the design.
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
          </>
        )}
      </div>
    );
  }

  // ---- Edit / create form ----
  return (
    <div className="w-full max-w-5xl mx-auto px-3 pt-4 pb-8 space-y-4">
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

      {/* Customer - open by default; picking one opens Sales Order & Lines
          (AC-P3). */}
      <FormSection
        title="Customer"
        summary={sectionSummaries.customer}
        open={sectionOpen.customer}
        onOpenChange={(next) => toggleSection('customer', next)}
      >
        <div
          className="space-y-1.5"
          {...(fieldErrors.debtor ? { 'data-error-anchor': 'debtor' } : {})}
        >
          <Label htmlFor="debtor">Customer *</Label>
          {debtorsLoaded && debtorOptions.length === 0 ? (
            <p
              className="text-sm rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200"
              data-testid="no-debtors-notice"
            >
              No customers available. Your portal account is not linked to a
              sales agent yet. Ask your Sorento contact to link it.
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
          {fieldErrors.debtor && (
            <p className="text-xs text-destructive">{fieldErrors.debtor}</p>
          )}
        </div>
      </FormSection>

      {/* Sales Order & Lines - the AI extract / dropzone and the lines table
          share one section (D-P1): the first line lands here from either one,
          and opens Price (AC-P7). */}
      <FormSection
        title="Sales Order & Lines"
        summary={sectionSummaries.sales_order}
        open={sectionOpen.sales_order}
        onOpenChange={(next) => toggleSection('sales_order', next)}
      >
        <div className="space-y-1.5">
          <Label>Sales Order</Label>
          {/* The shared portal dropzone (D2/D3): a file dropped before the draft
              exists is buffered and shown here as pending; once the draft exists
              (this request already has an id) a drop uploads immediately.
              D-P3: the section-header "Extract lines with AI" button is gone -
              each tile below carries its own Extract action, since one dropped
              file among ten is the common case, not "extract everything". */}
          <AttachmentDropzone
            kind="price_tag_request"
            submissionId={effectiveId ?? null}
            attachments={attachments}
            onChange={setAttachments}
            disabled={saving || submitting || deleting}
            pendingFiles={pendingFiles}
            onPendingFilesChange={setPendingFiles}
            onExtract={(file) => {
              setAiExtractFiles([file]);
              setAiExtractOpen(true);
            }}
          />
        </div>

        <div className="space-y-1.5">
          <Label>Lines</Label>
          {lines.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-6">
              No lines yet.
            </p>
          ) : (
            <div className="overflow-x-auto">
              {/* `table-fixed` on purpose: a product name can run to sixty
                  characters, and with auto layout the Item column swallowed
                  the whole width and pushed Qty and the rest off screen.
                  Fixed columns let the picker's trigger truncate instead, and
                  the min-width keeps every cell usable while the wrapper
                  scrolls on a phone, which is the Purchase Request pattern. */}
              <table className="w-full min-w-[560px] table-fixed text-sm">
                <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
                  <tr>
                    <th className="w-7 px-2 py-2 text-left">#</th>
                    <th className="w-[35%] px-2 py-2 text-left">Item</th>
                    <th className="w-[12%] px-2 py-2 text-left">Qty (tags)</th>
                    <th className="w-[33%] px-2 py-2 text-left">Remarks</th>
                    <th className="w-[20%] px-2 py-2"></th>
                  </tr>
                </thead>
                <tbody>
                  {lines.map((line, index) => (
                    <LineRow
                      key={line.key}
                      line={line}
                      index={index}
                      total={lines.length}
                      fetchItemOptions={fetchItemOptions}
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
          {fieldErrors.lines && (
            <p
              className="text-xs text-destructive"
              data-error-anchor="lines"
            >
              {fieldErrors.lines}
            </p>
          )}
          <Button size="sm" variant="outline" onClick={addLine}>
            <Plus className="size-3.5 mr-1" /> Add line
          </Button>
        </div>
      </FormSection>

      {/* Price - mode first, promotion second (D-P2, owner ruling): Selling
          is never disabled, and its optional Promotion picker lives here,
          not in its own section. Choosing either mode opens Additional
          Information (AC-P8). */}
      <FormSection
        title="Price"
        summary={sectionSummaries.price}
        open={sectionOpen.price}
        onOpenChange={(next) => toggleSection('price', next)}
      >
        <div className="space-y-1.5">
          <Label id="price-mode-label">Price</Label>
          <div
            role="radiogroup"
            aria-labelledby="price-mode-label"
            className="inline-flex items-center rounded-md border p-0.5"
          >
            <button
              type="button"
              role="radio"
              aria-checked={priceMode === 'list'}
              className={cn(
                'rounded px-3 py-1.5 text-sm transition-colors',
                priceMode === 'list'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted',
              )}
              onClick={() => {
                priceModeChosenRef.current = true;
                setPriceMode('list');
                // Switching to List hides Promotion and clears it (D-P2).
                setPromotionId('');
              }}
            >
              List price
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={priceMode === 'selling'}
              className={cn(
                'rounded px-3 py-1.5 text-sm transition-colors',
                priceMode === 'selling'
                  ? 'bg-primary text-primary-foreground'
                  : 'text-muted-foreground hover:bg-muted',
              )}
              onClick={() => {
                priceModeChosenRef.current = true;
                setPriceMode('selling');
              }}
            >
              Selling price
            </button>
          </div>
        </div>

        {priceMode === 'selling' && (
          <div className="space-y-1.5">
            <Label htmlFor="promotion">Promotion (optional)</Label>
            <SearchableSelect
              id="promotion"
              value={promotionId}
              onChange={setPromotionId}
              options={promotionOptions}
              placeholder="Select a promotion (optional)..."
              clearable
            />
          </div>
        )}
      </FormSection>

      {/* Additional Information - Need by and Notes, both optional
          (D-P2b): neither blocks Submit. */}
      <FormSection
        title="Additional Information"
        summary={sectionSummaries.need_by}
        open={sectionOpen.need_by}
        onOpenChange={(next) => toggleSection('need_by', next)}
      >
        <div
          className="space-y-1.5"
          {...(fieldErrors.neededBy
            ? { 'data-error-anchor': 'needed_by' }
            : {})}
        >
          <Label htmlFor="needed_by_date">Need by</Label>
          <Input
            id="needed_by_date"
            type="date"
            value={neededByDate}
            onChange={(e) => setNeededByDate(e.target.value)}
            min={nextBusinessDay()}
          />
          {fieldErrors.neededBy && (
            <p className="text-xs text-destructive">{fieldErrors.neededBy}</p>
          )}
        </div>

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
      </FormSection>

      <AIExtractDialog
        open={aiExtractOpen}
        onOpenChange={(next) => {
          setAiExtractOpen(next);
          // Cleared on close so the next tile's Extract starts fresh - a
          // stale `initialFiles` would re-run extraction on the WRONG file
          // the next time this dialog opens some other way.
          if (!next) setAiExtractFiles(undefined);
        }}
        kind="price_tag_request"
        // No header fields to mirror (D7 review push-back): Customer is a
        // select, not free text, and there is no sales order number field -
        // an empty list here is also what keeps the dialog from claiming
        // "Applied N fields" for fields nothing on this form reads.
        fieldDefs={[]}
        onApply={handleAIExtractApply}
        onExtracted={handleAIExtracted}
        renderRowStatus={(_p, index) => (
          <AIMatchStatusLabel status={aiMatchStatuses[index]} />
        )}
        initialFiles={aiExtractFiles}
      />

      {/* One line saying how much is outstanding, above the button that found it */}
      {(problemCount > 0 || serverMessage) && (
        <div
          className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          data-testid="submit-problem-summary"
        >
          {problemCount > 0 && (
            <p>
              {problemCount} thing{problemCount === 1 ? '' : 's'} need
              {problemCount === 1 ? 's' : ''} attention.
            </p>
          )}
          {serverMessage && <p className="mt-0.5">{serverMessage}</p>}
        </div>
      )}

      {/* Actions */}
      <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
        {/* Delete sits apart from Save and Submit, and asks first. */}
        {!isNew && isDraft && (
          <Button
            variant="outline"
            className="text-destructive sm:mr-auto"
            onClick={() => setShowDeleteDialog(true)}
            disabled={saving || submitting || deleting}
          >
            <Trash2 className="size-4 mr-1" />
            Delete Draft
          </Button>
        )}
        <Button
          variant="outline"
          onClick={handleSaveDraft}
          disabled={saving || submitting || !hasSomethingToSave}
        >
          {saving && <Loader2 className="size-4 mr-1 animate-spin" />}
          Save Draft
        </Button>
        {/* Enabled whenever the form is idle (D48b): a disabled button with no
            explanation is what sent the salesperson looking for the reason. */}
        <Button onClick={handleSubmit} disabled={submitting || saving}>
          {submitting && <Loader2 className="size-4 mr-1 animate-spin" />}
          Submit
        </Button>
      </div>

      <AlertDialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this draft?</AlertDialogTitle>
            <AlertDialogDescription>
              This cannot be undone. The draft and its lines are removed.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDeleteDraft}
              disabled={deleting}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleting ? 'Deleting...' : 'Delete'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
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
  fetchItemOptions: (query: string) => Promise<SearchableSelectOption[]>;
  onItemSelect: (key: string, option: SearchableSelectOption | null) => void;
  onUpdate: (key: string, patch: Partial<DraftLine>) => void;
  onRemove: (key: string) => void;
  onMove: (index: number, direction: 'up' | 'down') => void;
}

/**
 * One row of the lines table, on the Purchase Request pattern in `SubmissionForm`:
 * a cell per field, a trash button, and horizontal scroll on a narrow screen.
 */
function LineRow({
  line,
  index,
  total,
  fetchItemOptions,
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
        <td className="px-2 py-2">
          <Input
            value={line.remarks}
            onChange={(e) => onUpdate(line.key, { remarks: e.target.value })}
            placeholder="Note for this line..."
            aria-label={`Remarks for line ${index + 1}`}
          />
        </td>
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
          <td colSpan={5} className="px-2 pb-2">
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
// AI extract match state (D7)
// ---------------------------------------------------------------------------

/** The "Match" cell the AI extract dialog shows per row (AC-S6-2). */
function AIMatchStatusLabel({ status }: { status: AIMatchStatus | undefined }) {
  switch (status) {
    case 'matched_product':
      return <span className="text-emerald-700">Matched product</span>;
    case 'matched_set':
      return <span className="text-emerald-700">Matched set</span>;
    case 'not_found':
      return <span className="text-destructive">Not found</span>;
    default:
      return <span className="text-muted-foreground">Checking...</span>;
  }
}

// ---------------------------------------------------------------------------
// Design preview (D11)
// ---------------------------------------------------------------------------

/**
 * Fetches the request's real tag sheet design and renders it through
 * `PriceTagProofViewer` - the same `TagSheetRenderer` the CRM designer and the
 * PDF export use, so what the salesperson sees here is what gets printed.
 */
function ProofPreviewSection({
  request,
}: {
  request: PriceTagRequestDetail;
}) {
  const [doc, setDoc] = useState<TagSheetDoc | null>(null);
  const [resolvedData, setResolvedData] = useState<Record<string, ResolvedLineData>>({});
  const [loading, setLoading] = useState(true);
  const [notAvailable, setNotAvailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotAvailable(false);
    getPriceTagDesign(request.id)
      .then((data) => {
        if (cancelled) return;
        if (!data) {
          setNotAvailable(true);
          setDoc(null);
          return;
        }
        const nextResolved: Record<string, ResolvedLineData> = {};
        for (const line of data.lines) {
          nextResolved[line.line_id] = line;
        }
        setResolvedData(nextResolved);
        setDoc(data.doc);
      })
      .catch(() => {
        if (!cancelled) setNotAvailable(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [request.id]);

  if (loading) {
    return (
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Design Preview</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <Skeleton className="h-64 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (notAvailable || !doc) {
    return (
      <Card>
        <CardHeader className="py-3 px-4">
          <CardTitle className="text-base">Design Preview</CardTitle>
        </CardHeader>
        <CardContent className="px-4 pb-4">
          <p className="text-sm text-muted-foreground text-center py-6">
            Design not available yet.
          </p>
        </CardContent>
      </Card>
    );
  }

  return <PriceTagProofViewer doc={doc} resolvedData={resolvedData} />;
}

