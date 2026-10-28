'use client';

/**
 * Portal price tag request form - create / edit / view.
 *
 * Wired to real portal API via `price-tag-request-service.ts`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import {
  AlertCircle,
  ArrowLeft,
  Check,
  Copy,
  Download,
  FileText,
  History,
  Loader2,
  PencilLine,
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
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { DropdownMenuItem } from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { numberFieldError } from '@/lib/number-field';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import { DetailActionsMenu } from '@/components/common/DetailActionsMenu';
import { useIsMobile } from '@/hooks/use-mobile';
import { FormSection } from '@/components/common/FormSection';
import { RevisionHistory } from './RevisionHistory';
import {
  SearchableSelect,
  type SearchableSelectOption,
} from '@/components/common/SearchableSelect';
import {
  priceTagStatusLabel,
  priceTagStatusPillClass,
} from '@/lib/price-tag-status';
import { portalBase, portalDuplicatePath } from '../lib/portal-paths';
import { useRevisionHistory, useReviseSubmission } from '../hooks/useRevisions';
import type {
  PriceTagRequestDetail,
  PriceTagRequestLineInput,
  DebtorOption,
  PriceMode,
  TagItemOption,
} from '../lib/price-tag-request-service';
import {
  lookupDebtors,
  lookupProductCombos,
  lookupLinePricing,
  lookupTagItems,
  getRequest,
  createRequest,
  updateRequest,
  deleteRequest,
  submitRequest,
  approveRequest,
  requestChanges,
  listReviewComments,
  collectRequest,
  downloadPriceTagPdf,
  requestPriceTagExport,
} from '../lib/price-tag-request-service';
import { PriceModeToggle } from '@/components/dealer-kit/PriceModeToggle';
import { PriceTagDesignReview } from '@/components/dealer-kit/PriceTagDesignReview';
import { PriceTagLinesTable } from '@/components/dealer-kit/PriceTagLinesTable';
import { PriceTagLinesView } from '@/components/dealer-kit/PriceTagLinesView';
import {
  usePriceTagLineEditor,
  type PriceTagLineLookups,
} from '@/hooks/usePriceTagLineEditor';
import {
  draftLinesPayload,
  lineToDraft,
  type DraftLine,
} from '@/lib/dealer-kit/price-tag-draft-lines';
import type { ChangeRequestPayload } from '@/lib/dealer-kit/review-comments';
import POCrossCheckViewer from './POCrossCheckViewer';
import { AttachmentDropzone } from './AttachmentDropzone';
import {
  AIExtractDialog,
  type AIExtractApplyPayload,
} from './AIExtractDialog';
import type { AIExtractedProductLine } from '../lib/portal-client';
import {
  uploadAttachment,
  getPriceTagDesign,
  fetchMe,
  fetchSubmissionNeighbours,
  type PortalAttachment,
  type PortalSubmissionNeighbours,
} from '../lib/portal-client';
import { codeWithName } from '@/lib/product-display';

/**
 * The portal's own reads for the shared line editor and proof review
 * (PORTAL-P4-REQUESTS S7b). Called through, never captured, so a module
 * the tests replace is read at call time exactly as before the move.
 */
const PORTAL_LINE_LOOKUPS: PriceTagLineLookups = {
  lookupTagItems: (query) => lookupTagItems(query),
  lookupProductCombos: (productId) => lookupProductCombos(productId),
  lookupLinePricing: (mode, lines) => lookupLinePricing(mode, lines),
};

const PORTAL_DESIGN_CALLS = {
  loadDesign: (id: string) => getPriceTagDesign(id),
  loadReviewComments: (id: string) => listReviewComments(id),
};

/** Where an AI-extracted product line stands against the catalogue lookup
 *  (D7/AC-S6-2), shown in the extract dialog's own result table. */
type AIMatchStatus = 'loading' | 'matched_product' | 'matched_set' | 'not_found' | 'picked';

// ---------------------------------------------------------------------------
// Sections. The draft line, its package rules and its payload live in
// `lib/dealer-kit/price-tag-draft-lines.ts`, the read-only lines table in
// `components/dealer-kit/PriceTagLinesView.tsx`, both shared with the CRM
// request page (PORTAL-P4-REQUESTS S7b).
// ---------------------------------------------------------------------------

// D-P1: the four sections, top to bottom, on both the edit form and the
// read-only view.
type SectionKey = 'customer' | 'sales_order' | 'price' | 'need_by';

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

/** Statuses the real design (D11) is visible at, once one exists to show.
 *  `ready` is retired (r9 D8); the two collection statuses take its place. */
const DESIGN_PREVIEW_STATUSES = new Set([
  'proof_ready',
  'changes_requested',
  'approved',
  'ready_for_collection',
  'collected',
]);

/** r10 S9: a proof is not for printing, so the design preview shows from
 *  `proof_ready` but the download item stays disabled until `approved`. */
const DOWNLOAD_AVAILABLE_STATUSES = new Set([
  'approved',
  'ready_for_collection',
  'collected',
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

/**
 * S4 (code review): a `line:<index>` refusal - PARTS_NEED_COMBO and
 * INVALID_PART read the same `detail` shape (`app/services/price_tag_request_
 * service.py`, both `422`s naming `line:<index>`) - also toasts "Line N:
 * <message>" so the salesperson sees which line failed even before the
 * inline row highlight scrolls into view. Both Save Draft and Submit call
 * this the same way; neither branches on `code`, since the field vocabulary
 * is what both codes share.
 */
function lineErrorToast(fields: string[], message: string): void {
  const lineField = fields.find((f) => f.startsWith('line:'));
  if (!lineField) return;
  const index = Number(lineField.slice('line:'.length));
  if (!Number.isInteger(index)) return;
  toast.error(`Line ${index + 1}: ${message}`);
}

/** Bring the first complaint into view, after the render that drew it. */
function scrollToFirstProblem(): void {
  setTimeout(() => {
    // A test can tear jsdom down inside these 50 ms; never reach a document that is gone.
    if (typeof document === 'undefined') return;
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
  // Owner ruling after #948: List price / Promotion / Selling price are real
  // table columns on desktop, not a `colSpan` sub-row. Below the existing
  // sidebar breakpoint they still stack under the Item cell instead, reusing
  // the app's own mobile check rather than a bespoke `md:` media query.
  const isMobile = useIsMobile();

  // ---- Data fetching state ----
  const [loading, setLoading] = useState(!isNew);
  // AC-L4: a deep link this contact cannot see 403s the load below
  // (`FORM_TYPE_NOT_VISIBLE`) - held separately from the field-level toasts
  // the save/submit actions already use, so it can suppress the form itself.
  const [loadError, setLoadError] = useState<string | null>(null);
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

  // ---- Form state ----
  const [debtorCode, setDebtorCode] = useState('');
  // Header price mode (D5): replaces the per-line "Promo price" switch.
  // Selling requires a promotion, so clearing the promotion while Selling is
  // chosen flips the control back to List price.
  const [priceMode, setPriceMode] = useState<PriceMode>('list');
  const [neededByDate, setNeededByDate] = useState('');
  const [notes, setNotes] = useState('');
  const [lines, setLines] = useState<DraftLine[]>([]);
  const [attachments, setAttachments] = useState<PortalAttachment[]>([]);
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  // The Sales Order box's accept list, off `/me` (see the /me effect below).
  const [attachmentExtensions, setAttachmentExtensions] = useState<string[] | undefined>();

  // ---- AI extract sales order lines (D7, per-file per D-P3) ----
  const [aiExtractOpen, setAiExtractOpen] = useState(false);
  // Set the moment a tile's own Extract action is tapped, so the dialog opens
  // straight on that one file's results (D-P3) instead of the upload stage.
  const [aiExtractFiles, setAiExtractFiles] = useState<File[] | undefined>(
    undefined,
  );
  // Per-row match state for the CURRENT extraction, keyed by the row's own
  // trimmed/lowercased product_code (review round 2) rather than its index -
  // the dialog lets a row be removed before Apply (D-P4), which shortens the
  // array Apply hands back without shortening an index-keyed lookup, so every
  // match after the removed row read the wrong entry. A code is stable
  // across that removal; an index is not. Populated as each code resolves so
  // the dialog can show "Not found" before Apply is even clicked (AC-S6-2),
  // and read again by the apply handler so it never re-looks-up what this
  // already knows.
  const [aiMatchStatuses, setAiMatchStatuses] = useState<Record<string, AIMatchStatus>>({});
  const aiMatchesRef = useRef<Record<string, TagItemOption | null>>({});
  // AI-EXTRACT-DYM: the "did you mean" suggestion the user picked per code
  // (product id), keyed like `aiMatchStatuses`. Empty after every extraction:
  // nothing is picked for the user.
  const [aiPicks, setAiPicks] = useState<Record<string, string>>({});
  const normalizeAiCode = (raw: string | null | undefined) => (raw ?? '').trim().toLowerCase();


  // ---- Delete draft ----
  const [deleting, setDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  // ---- Read-only view: Download PDF (D19/S2). The attachment preview
  // modal is the read-only AttachmentDropzone's own (D-P5) - no separate
  // state needed here anymore. ----
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  // r10 S9: true from the click that queues an export (never asked yet, or
  // the last one failed) until the poll sees it finish - the demo caught
  // three approved requests whose auto-export had failed with nothing on
  // the portal able to ask for a second one.
  const [exportPending, setExportPending] = useState(false);
  const [collecting, setCollecting] = useState(false);
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
  // Set by a Save / Submit that found a bad quantity or price; rows then show their sentence live.
  const [showNumberErrors, setShowNumberErrors] = useState(false);

  // A draft is `portal_draft_at`, not a status: a draft's status is `new`, the
  // same status a submitted request keeps until marketing claims it. Checking
  // the status for 'draft' matched nothing, so re-opening a saved draft showed
  // the read-only page instead of the form.
  const isDraft = Boolean(request?.portal_draft_at);
  const isEditable = isNew || isDraft;
  // R3-1: no post-submit Edit any more - a submitted request is read-only,
  // and a change goes through the revision engine instead. `reviseMode` only
  // ever turns on via the header gear's own Revise item (same hooks
  // `SubmissionForm` reads for the legacy kinds), never from status/draft
  // state directly, so Cancel puts the read view back with no round trip.
  // r10 S1 (owner: "always i print myself, qty ignore"): the portal no
  // longer asks - every request the portal creates prints self. The CRM
  // keeps its own office control (Q7); this constant is what every payload
  // below sends.
  const printBy = 'self' as const;
  const [reviseMode, setReviseMode] = useState(false);
  const [reviseReason, setReviseReason] = useState('');
  const showEditForm = isEditable || reviseMode;
  const isProofReady = request?.status === 'proof_ready';
  // The design preview shows for longer than the approve/request-changes
  // actions do (D11/AC-S4-4): once approved the salesperson can still look
  // at what they approved, but Approve/Request Changes only make sense while
  // the design is actually waiting on them.
  const showDesignPreview = !!request && DESIGN_PREVIEW_STATUSES.has(request.status);
  // r10 S9: what the gear's Download PDF item reads. `latest_export_status`
  // is the source of truth once the server sends it; a request created
  // before r10 falls back to today's yes/no.
  const canDownloadPdf = !!request && DOWNLOAD_AVAILABLE_STATUSES.has(request.status);
  const exportStatus: 'ready' | 'pending' | 'failed' | null =
    request?.latest_export_status ?? (request?.has_completed_export ? 'ready' : null);
  const exportPreparing = exportPending || exportStatus === 'pending';
  // The id to save/flush against: the route param when one exists, else
  // whatever a create call in THIS session already answered with.
  const effectiveId = requestId ?? createdRequestId ?? undefined;
  // R3-1/AC-R7: same generic revision hooks SubmissionForm reads for the
  // legacy kinds, rather than a second revise mechanism. Review round 3:
  // the policy is read straight off the re-fetched request's own `revision`
  // block (same as SubmissionForm's `detail?.revision`) rather than a
  // SECOND GET through `useRevisionPolicy` - `_detail_body` already carries
  // it on every `getRequest` response.
  const revisionPolicy = request?.revision ?? null;
  // R3-5: the one-line revision status, same wording SubmissionForm's own
  // header line uses - review round 3 folds the price tag header into the
  // SAME one muted truncating line, rather than its own separate blocked-
  // reason sentence under a bold doc-number + colored pill.
  const revisionStatusText = revisionPolicy
    ? revisionPolicy.allowed
      ? `${revisionPolicy.remaining} of ${revisionPolicy.max} revisions left`
      : (revisionPolicy.blocked_reason ?? null)
    : null;
  const { revise, submitting: revising } = useReviseSubmission(
    'price_tag_request',
    effectiveId,
  );
  // AC-R7: same history hook/component SubmissionForm reads for the legacy
  // kinds - the generic revision routes already serve price_tag_request
  // (R3-1's ADAPTERS entry), this is just the FE surface catching up.
  const revisionHistory = useRevisionHistory('price_tag_request', effectiveId);

  // Portal record navigation (review round 3), same as SubmissionForm: same
  // kind, newest first, token-scoped to the contact's own requests.
  const [neighbours, setNeighbours] =
    useState<PortalSubmissionNeighbours | null>(null);
  useEffect(() => {
    if (!requestId) {
      setNeighbours(null);
      return;
    }
    let cancelled = false;
    fetchSubmissionNeighbours('price_tag_request', requestId)
      .then((n) => {
        if (!cancelled) setNeighbours(n);
      })
      .catch(() => {
        if (!cancelled) setNeighbours(null);
      });
    return () => {
      cancelled = true;
    };
  }, [requestId]);

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
  // must not itself open Additional Information on a blank new form, and the
  // Price section's own collapsed summary (AC-P9, review round 2) must stay
  // empty until then too. Real state, not a ref: the summary has to re-render
  // off it, and a ref mutation alone never does.
  const [priceModeChosen, setPriceModeChosen] = useState(false);

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
    if (!priceModeChosen) return;
    if (priceMode === 'list' || priceMode === 'selling') {
      openSectionOnce('need_by');
    }
  }, [priceMode, priceModeChosen, openSectionOnce]);

  const selectedDebtorName = useMemo(
    () => debtors.find((d) => d.code === debtorCode)?.name ?? null,
    [debtors, debtorCode],
  );
  const fileCount = attachments.length + pendingFiles.length;

  // Collapsed-header one-liners (AC-P9); empty sections show none. D1: the
  // summary no longer names a single promotion - each line may carry its
  // own now.
  const sectionSummaries: Record<SectionKey, string | null> = {
    customer: selectedDebtorName,
    sales_order:
      lines.length > 0 || fileCount > 0
        ? `${lines.length} line${lines.length === 1 ? '' : 's'}, ${fileCount} file${fileCount === 1 ? '' : 's'}`
        : null,
    price: !priceModeChosen ? null : priceMode === 'selling' ? 'Selling price' : 'List price',
    need_by:
      neededByDate || notes.trim()
        ? [neededByDate || null, notes.trim() ? 'notes' : null]
            .filter(Boolean)
            .join(' - ')
        : null,
  };

  // Shared by the load effect and Cancel (D-P6): both put the form's field
  // state back to what the loaded request itself says, so Cancel needs no
  // round trip and Save + re-`getRequest` needs no separate mapping.
  const applyRequestFieldsFrom = useCallback((data: PriceTagRequestDetail) => {
    setDebtorCode(data.debtor_code ?? '');
    setPriceMode(data.price_mode ?? 'list');
    setPriceModeChosen(true);
    setNeededByDate(data.needed_by_date ?? '');
    setNotes(data.notes ?? '');
    setLines(data.lines.map(lineToDraft));
    setAttachments(data.attachments ?? []);
  }, []);

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
    // D1: promotions are no longer looked up for the whole request - each
    // line asks `lookupLinePricing` for the ones that cover IT (S1 effect
    // below).
  }, []);

  // D7 r3 (PLAN-portal-forms-market-segment): a `/new` page makes no request
  // of its own to check visibility - it reads `visible_form_types` off the
  // same `/me` payload every other portal page already fetches, and renders
  // the same inline blocked message the edit page's real 403 uses below.
  // The server remains the enforcement; this only avoids an empty form.
  // ATTACH-ACCEPT: the same `/me` carries the Sales Order box's accept list,
  // so it is read on an existing draft too; the visibility check stays /new.
  useEffect(() => {
    let cancelled = false;
    fetchMe()
      .then((c) => {
        if (cancelled) return;
        setAttachmentExtensions(c.attachment_allowed_extensions);
        if (
          isNew &&
          Array.isArray(c.visible_form_types) &&
          !c.visible_form_types.includes('price_tag_request')
        ) {
          setLoadError('Price Tag Request is not available for your account.');
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isNew]);

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
        // A loaded request already has a real price mode, not the blank
        // form's resting default - so a later mode click is free to act on
        // it (AC-P8). Also open every section that already holds a value
        // directly (AC-P11): a `setPriceMode('list')` here is a no-op when
        // the mode was already 'list' at mount, so the reactive rule alone
        // would never see it change and never fire.
        applyRequestFieldsFrom(data);
        if (data.debtor_code) openSectionOnce('sales_order');
        if (data.lines.length > 0) openSectionOnce('price');
        openSectionOnce('need_by');
      })
      .catch((e) => {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : 'Failed to load request');
        }
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

  // ---- Lines: Item pick, packages and parts, line pricing (D1/D2/D4, S1/S2) ----
  // Shared with the CRM request page (PORTAL-P4-REQUESTS S7b); the portal's own
  // lookups go in, through the portal token.
  const lineEditor = usePriceTagLineEditor({
    lines,
    setLines,
    priceMode,
    lookups: PORTAL_LINE_LOOKUPS,
  });

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
        setPriceMode(data.price_mode ?? 'list');
        setPriceModeChosen(true);
        setNeededByDate(data.needed_by_date ?? '');
        setNotes(data.notes ?? '');
        // A duplicate's lines are new, unsaved rows with no identity of
        // their own yet (nit, review round 2) - the source request's own
        // line ids have no business surviving as this draft's React keys.
        setLines(
          data.lines.map((l) => ({
            ...lineToDraft(l),
            key: `dup-${Math.random().toString(36).slice(2, 10)}`,
          })),
        );
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

  // ---- AI extract sales order lines (D7, D3 of the AI-extract-resolver
  // plan) ----
  //
  // The extract already resolved each code through the shared entity
  // resolver server-side (D1/D2) - `match` / `product_id` / `product_set_id`
  // ride on the payload, so every row is read directly off it, no lookup, no
  // 'loading' state (AC-S1-6, AC-S1-7). One matcher, on the server; the form
  // keeps none of its own - a row with no exact match, or with `match`
  // absent entirely, reads as "not_found".
  const handleAIExtracted = useCallback(
    (products: AIExtractedProductLine[]) => {
      aiMatchesRef.current = {};
      const statuses: Record<string, AIMatchStatus> = {};

      products.forEach((p) => {
        const code = normalizeAiCode(p.product_code);
        if (p.match === 'product' && p.product_id) {
          aiMatchesRef.current[code] = {
            kind: 'product',
            id: p.product_id,
            code: p.product_code ?? code,
            name: p.product_name || p.product_code || code,
          };
          statuses[code] = 'matched_product';
        } else if (p.match === 'product_set' && p.product_set_id) {
          aiMatchesRef.current[code] = {
            kind: 'product_set',
            id: p.product_set_id,
            code: p.product_code ?? code,
            name: p.product_name || p.product_code || code,
          };
          statuses[code] = 'matched_set';
        } else {
          aiMatchesRef.current[code] = null;
          statuses[code] = 'not_found';
        }
      });

      setAiMatchStatuses(statuses);
      setAiPicks({});
    },
    [],
  );

  /** AI-EXTRACT-DYM: the user confirms (or clears) one suggestion for a row
   *  with no match. A pick reads exactly like a matched product from here on,
   *  so Apply needs no branch of its own; a clear puts the row back to
   *  not found. */
  const handleAIPick = useCallback(
    (p: AIExtractedProductLine, productId: string) => {
      const code = normalizeAiCode(p.product_code);
      const pick = (p.suggestions ?? []).find((s) => s.product_id === productId);
      aiMatchesRef.current[code] = pick
        ? {
            kind: 'product',
            id: pick.product_id,
            code: pick.product_code,
            name: pick.product_name || pick.product_code,
          }
        : null;
      setAiMatchStatuses((prev) => ({ ...prev, [code]: pick ? 'picked' : 'not_found' }));
      setAiPicks((prev) => {
        const next = { ...prev };
        if (pick) next[code] = pick.product_id;
        else delete next[code];
        return next;
      });
    },
    [],
  );

  /** Apply = append one line per matched row (D7). unit_price is shown in the
   *  dialog only and is never stored (ADR 0008) - no field in `DraftLine`
   *  reads it. Reads the SAME matches `handleAIExtracted` already resolved,
   *  rather than looking every code up a second time. */
  const handleAIExtractApply = useCallback(
    (payload: AIExtractApplyPayload) => {
      const matches = aiMatchesRef.current;
      const notFoundCodes: string[] = [];
      // R3-7: a matched row whose product/set is already on the request -
      // an existing line, or an earlier row in this SAME batch - merges
      // into it (quantity summed, remarks joined) instead of adding a
      // second line the server would refuse (DUPLICATE_LINE).
      const merged: DraftLine[] = lines.map((l) => ({ ...l }));
      let addedCount = 0;
      let mergedCount = 0;
      payload.productLines.forEach((p) => {
        const code = (p.product_code ?? '').trim();
        const match = matches[normalizeAiCode(code)];
        if (!match) {
          if (code) notFoundCodes.push(code);
          return;
        }
        // r10 S2 (owner: "qty ignore"): quantity is how many TAGS the
        // salesperson wants, which the document never says - the extract
        // never sets it, and a second sighting of the same code merging in
        // is not a second tag either.
        const qty = 1;
        const existingIndex = merged.findIndex((l) =>
          match.kind === 'product'
            ? l.product_id === match.id
            : l.product_set_id === match.id,
        );
        if (existingIndex >= 0) {
          const existing = merged[existingIndex];
          merged[existingIndex] = {
            ...existing,
            remarks: [existing.remarks, p.notes]
              .filter((v) => v && v.trim())
              .join('; '),
          };
          mergedCount += 1;
          return;
        }
        merged.push({
          key: `draft-${Date.now()}-${merged.length}-${Math.random().toString(36).slice(2, 8)}`,
          line_type: match.kind,
          product_id: match.kind === 'product' ? match.id : null,
          product_set_id: match.kind === 'product_set' ? match.id : null,
          name: match.name || match.code,
          code: match.code,
          quantity: qty,
          included_accessories: '',
          remarks: p.notes ?? '',
          guard_error: null,
          combo_id: null,
          combos: [],
          combos_loaded: false,
          host_guarded: false,
          parts: [],
          promotion_id: null,
          promotion_locked: false,
          manual_sell_price: null,
          pricing: null,
        });
        addedCount += 1;
      });
      if (addedCount > 0 || mergedCount > 0) {
        setLines(merged);
        const parts: string[] = [];
        if (addedCount > 0) {
          parts.push(`${addedCount} line${addedCount === 1 ? '' : 's'}`);
        }
        if (mergedCount > 0) {
          parts.push(
            `${mergedCount} merged into existing line${mergedCount === 1 ? '' : 's'}`,
          );
        }
        toast.success(`Added ${parts.join(', ')} from the sales order.`);
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
    },
    [lines],
  );

  // ---- What there is to save, and what Submit still needs (D48) ----

  /** Save Draft asks for one thing only: that there is something to save. A
   *  dropped PO file with nothing else filled in still counts (AC-S1-2) - it is
   *  parked in `pendingFiles` waiting on a draft id to upload to, and Save Draft
   *  is the only way to give it one. */
  const hasSomethingToSave =
    !!debtorCode ||
    !!neededByDate ||
    notes.trim().length > 0 ||
    lines.length > 0 ||
    pendingFiles.length > 0;

  /** AC-S2-8: the shared payload builder, so the portal and the CRM request
  *  page send the same line shape (`draftLinesPayload`). */
  const payloadLines = (): PriceTagRequestLineInput[] => draftLinesPayload(lines);

  // AC-P10: a failed Submit opens the first offending section, top to bottom,
  // so the inline error it just set is visible rather than sitting inside a
  // section still collapsed from a moment ago. `toggleSection` (not
  // `openSectionOnce`) because this must fire every time, even for a section
  // the reader already closed by hand.
  const openSectionForProblems = useCallback(
    (
      fields: {
        debtor?: string;
        neededBy?: string;
        lines?: string;
      },
      hasRowProblems: boolean,
    ) => {
      if (fields.debtor) {
        toggleSection('customer', true);
      } else if (fields.lines || hasRowProblems) {
        toggleSection('sales_order', true);
      } else if (fields.neededBy) {
        toggleSection('need_by', true);
      }
    },
    [toggleSection],
  );

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
      openSectionForProblems(next, rows.size > 0);
      return Object.keys(next).length + rows.size;
    },
    [openSectionForProblems],
  );

  /** Everything Submit can see wrong from here, reported at once. Need by is
   *  optional (D-P2b) - only a server refusal can still name it, until the
   *  backend rule drops too. */
  const collectProblems = useCallback(() => {
    const next: {
      debtor?: string;
      neededBy?: string;
      lines?: string;
    } = {};
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

  /** A blank or invalid quantity / manual price stops the send; the rows say which. */
  const numbersInvalid = useCallback(() => {
    const bad = lines.some(
      (l) =>
        numberFieldError(l.quantity, { min: 1, integer: true }) !== undefined ||
        numberFieldError(l.manual_sell_price, { min: 0.01, optional: true }) !== undefined,
    );
    if (bad) {
      setShowNumberErrors(true);
      toggleSection('sales_order', true);
    }
    return bad;
  }, [lines, toggleSection]);

  // ---- Save draft (D48a: validates nothing but the numbers it would send) ----
  const handleSaveDraft = useCallback(async () => {
    if (numbersInvalid()) return;
    setSaving(true);
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      const payload = {
        debtor_code: debtorCode || null,
        debtor_name: debtorCode ? (debtor?.name ?? debtorCode) : null,
        needed_by_date: neededByDate || null,
        notes: notes || null,
        price_mode: priceMode,
        print_by: printBy,
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
      // S4 (code review): the same `line:<index>` -> row mapping Submit uses
      // (`applyFieldErrors`), so a reopened draft whose product lost its
      // combo (or any other row-scoped refusal, PARTS_NEED_COMBO and
      // INVALID_PART alike) is named on the ROW here too, not just a generic
      // toast with no way back to which line it was about.
      const message = e instanceof Error ? e.message : 'Failed to save draft';
      const named = errorFields(e);
      const placed = named.length > 0 ? applyFieldErrors(named, message) : 0;
      if (placed > 0) {
        lineErrorToast(named, message);
        scrollToFirstProblem();
      } else {
        toast.error(message);
      }
    } finally {
      setSaving(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numbersInvalid, effectiveId, debtorCode, debtors, priceMode, neededByDate, notes, lines, flushPendingFiles, router, slug, applyFieldErrors]);

  // ---- Revise (R3-1): sent through the portal revision engine, never the
  // retired post-submit PUT. A reason is required; the same zero-line/
  // set-guard/duplicate-product bar Submit runs is enforced server side
  // inside the revise transaction (apply_lines), so a client-side pre-check
  // here only saves a round trip on the one case that is free to check
  // (zero lines) - the rest surfaces as the server's own sentence. ----
  const handleSubmitRevision = useCallback(async () => {
    if (!effectiveId) return;
    if (!reviseReason.trim()) {
      toast.error('Tell us what changed and why.');
      return;
    }
    if (numbersInvalid()) return;
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      await revise({
        reason: reviseReason.trim(),
        expectedRevisionNo: request?.revision_no ?? 0,
        fields: {
          debtor_code: debtorCode || null,
          debtor_name: debtorCode ? (debtor?.name ?? debtorCode) : null,
          needed_by_date: neededByDate || null,
          notes: notes || null,
          price_mode: priceMode,
          // Live finding, PT-202609-0013: Save Draft and Submit both carry the
          // print choice and this payload did not, so revising a request
          // silently dropped who prints it.
          print_by: printBy,
        },
        products: payloadLines(),
      });
      // Review round 3: a file added while composing the revision sat in
      // `pendingFiles` with nowhere to flush to (the request already exists,
      // so it never goes through `handleSaveDraft`'s create-then-flush path) -
      // same call Save Draft / Submit already make, before the request the
      // policy will re-check moves on to its post-revision status.
      await flushPendingFiles(effectiveId);
      const fresh = await getRequest(effectiveId);
      if (fresh) {
        setRequest(fresh);
        applyRequestFieldsFrom(fresh);
      }
      // Review round 3: the lineage and the policy the header/gear read both
      // changed under this revision - reload the one GET that changed
      // (revisions), and `fresh.revision` (just re-fetched above) already IS
      // the refreshed policy, so nothing else needs asking again.
      revisionHistory.reload();
      setReviseMode(false);
      setReviseReason('');
      toast.success('Revision sent');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to send revision');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numbersInvalid, effectiveId, reviseReason, revise, debtorCode, debtors, priceMode, neededByDate, notes, request, applyRequestFieldsFrom, flushPendingFiles, revisionHistory]);

  const handleCancelRevise = useCallback(async () => {
    setReviseMode(false);
    setReviseReason('');
    setPendingFiles([]);
    if (!effectiveId) return;
    try {
      const fresh = await getRequest(effectiveId);
      if (fresh) {
        setRequest(fresh);
        applyRequestFieldsFrom(fresh);
      }
    } catch {
      // The read view already fell back to the pre-revise `request` snapshot
      // above; a failed re-fetch leaves that in place rather than erroring
      // out of a Cancel, which is not a save the reader needs told about.
    }
  }, [effectiveId, applyRequestFieldsFrom]);

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
      openSectionForProblems(next, emptyRows.length > 0);
      scrollToFirstProblem();
      return;
    }
    if (numbersInvalid()) return;

    setSubmitting(true);
    setServerMessage(null);
    setFieldErrors({});
    setLines((prev) => prev.map((l) => ({ ...l, guard_error: null })));
    try {
      const debtor = debtors.find((d) => d.code === debtorCode);
      const payload = {
        debtor_code: debtorCode,
        debtor_name: debtor?.name ?? debtorCode,
        // Review round 2: an empty date input is '', not omitted - sent as
        // null, same as the other two payload builders here, never as ''.
        needed_by_date: neededByDate || null,
        notes: notes || null,
        price_mode: priceMode,
        print_by: printBy,
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
        lineErrorToast(named, message);
        scrollToFirstProblem();
      } else {
        setServerMessage(message);
        toast.error(message);
      }
    } finally {
      setSubmitting(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [numbersInvalid, collectProblems, applyFieldErrors, openSectionForProblems, effectiveId, debtorCode, debtors, priceMode, neededByDate, notes, lines, flushPendingFiles, router, slug]);

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

  // ---- Mark collected (r9 D8): the salesperson has the tags ----
  const handleCollect = useCallback(async () => {
    if (!requestId) return;
    setCollecting(true);
    try {
      await collectRequest(requestId);
      toast.success('Marked collected');
      const data = await getRequest(requestId);
      if (data) setRequest(data);
    } catch {
      toast.error('Failed to mark this collected');
    } finally {
      setCollecting(false);
    }
  }, [requestId]);

  // ---- Request changes (r9 D5) ----
  //
  // No dialog and no free-text-only path any more: the pins ARE the change
  // request, and Send posts the whole round in one call.
  const handleSendChanges = useCallback(
    async (payload: ChangeRequestPayload) => {
      if (!requestId) return;
      try {
        await requestChanges(requestId, payload);
        toast.success(
          payload.comments.length === 1
            ? 'Change request sent'
            : `${payload.comments.length} change requests sent`,
        );
        router.push(`${portalBase(slug)}?type=price_tag_request`);
      } catch (error) {
        // Re-thrown, not swallowed: the Design section clears its pins on a
        // resolved promise, so a refused Send used to take the whole round
        // with it and leave the salesperson to place five pins again.
        toast.error(
          error instanceof Error
            ? error.message
            : 'Failed to send the change requests',
        );
        throw error;
      }
    },
    [requestId, router, slug],
  );

  // ---- Download PDF (D19): the request's latest completed tag sheet export.
  // r10 S9: a READY export streams exactly as before; anything else (never
  // asked, or the last attempt failed) queues one instead of sitting behind
  // a dead button - the demo caught three approved requests stuck that way
  // because Approve's own auto-export had failed with no retry. ----
  const streamDownload = useCallback(async () => {
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

  const handleDownloadPdf = useCallback(async () => {
    if (!requestId) return;
    if (exportStatus === 'ready') {
      await streamDownload();
      return;
    }
    // Never asked yet, or the last export failed: queue (or re-queue) one
    // and let the poll below pick it up.
    setExportPending(true);
    try {
      await requestPriceTagExport(requestId);
    } catch (e) {
      setExportPending(false);
      toast.error(e instanceof Error ? e.message : 'Failed to queue the PDF export');
    }
  }, [requestId, exportStatus, streamDownload]);

  // Poll every 5 s while an export is preparing; stream it the moment the
  // refetched request says ready, surface a toast on failed.
  //
  // AC-S9-8: gated on `exportPreparing`, not the LOCAL `exportPending` alone -
  // a request that loads (or refreshes) already `pending` on the server (a
  // reload mid-export, or a second tab that queued it) must also poll, not
  // just show the right label and then sit dead.
  useEffect(() => {
    if (!exportPreparing || !requestId) return;
    let cancelled = false;
    const timer = setInterval(() => {
      getRequest(requestId)
        .then((fresh) => {
          if (cancelled || !fresh) return;
          setRequest(fresh);
          const status =
            fresh.latest_export_status ?? (fresh.has_completed_export ? 'ready' : null);
          if (status === 'ready') {
            setExportPending(false);
            void streamDownload();
          } else if (status === 'failed') {
            setExportPending(false);
            toast.error('PDF export failed. Try again.');
          }
        })
        .catch(() => {
          // A transient failure to poll is not itself a failed export -
          // the next tick tries again.
        });
    }, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [exportPreparing, requestId, streamDownload]);

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

  // AC-L4: show the server's message and a way back - no crash, no empty
  // form rendered underneath it.
  if (loadError) {
    return (
      <div className="w-full max-w-3xl mx-auto px-3 pt-4 pb-4 space-y-3">
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{loadError}</AlertTitle>
        </Alert>
        <Button variant="outline" onClick={() => router.push(portalBase(slug))}>
          Back to your forms
        </Button>
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
  if (request && !showEditForm) {
    // AC-R7: same tab shape SubmissionForm gives the legacy kinds - Revisions
    // becomes its own tab once this type has revisions on (the generic
    // revision routes already serve price_tag_request via R3-1's ADAPTERS
    // entry; this is just the FE surface catching up).
    const revisionsTabbed = revisionPolicy?.enabled === true;

    const detailsContent = (
      <>
        <div className="space-y-1">
          {/* Review round 3: Status moves out of the header into a labeled
              row here, same as the stock inquiry page - the header now
              carries only the one muted truncating line (doc number,
              revision status, neighbour counter). */}
          <div className="flex items-center gap-2">
            <span className="text-sm text-muted-foreground">Status:</span>
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

        {/* Ready to pick up (r9 D8): the one thing the salesperson can do
            here, said where the status is said. */}
        {request.status === 'ready_for_collection' && (
          <div className="flex flex-col gap-2 rounded-lg border p-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-sm">
              {request.ready_for_collection_at
                ? `Ready to collect since ${new Date(request.ready_for_collection_at).toLocaleDateString()}`
                : 'Ready to collect'}
            </p>
            <Button
              size="sm"
              disabled={collecting}
              onClick={() => void handleCollect()}
              data-testid="portal-mark-collected"
            >
              {collecting ? (
                <Loader2 className="size-4 mr-1 animate-spin" />
              ) : (
                <Check className="size-4 mr-1" />
              )}
              Mark collected
            </Button>
          </div>
        )}

        {/* The design comes FIRST from `proof_ready` onward (r9 D3): it is what
            the salesperson opened the request to look at, and their own
            answers below it are the reference, not the headline. It shows for
            longer than the review actions do (D11/AC-S4-4). */}
        {showDesignPreview && (
          <PriceTagDesignReview
            request={request}
            reviewable={isProofReady}
            onApprove={handleApprove}
            onSend={handleSendChanges}
            download={{
              available: exportStatus === 'ready',
              pending: downloadingPdf,
              onDownload: () => void handleDownloadPdf(),
            }}
            loadDesign={PORTAL_DESIGN_CALLS.loadDesign}
            loadReviewComments={PORTAL_DESIGN_CALLS.loadReviewComments}
          />
        )}

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
          {/* Sales Order - D-P5: the same dropzone the form uses, in
              `readOnly` mode - same tiles, same ordering, same preview
              modal, but no drop area, no paste, no remove, no per-tile
              Extract. Nothing here is actionable until Edit is tapped. */}
          <div className="space-y-1.5">
            <Label>Sales Order</Label>
            <AttachmentDropzone
              kind="price_tag_request"
              submissionId={request.id}
              attachments={attachments}
              onChange={() => {}}
              readOnly
            />
          </div>

          {/* Lines: same table the edit form uses, cells read-only. Owner
              ruling after #948: List price / Promotion / Selling price are
              real table columns on desktop here too, not a `colSpan`
              sub-row - same `isMobile`-exclusive stack under the Item cell
              below the mobile breakpoint as the editable table uses. */}
          <div className="space-y-1.5">
            <Label>Lines ({request.lines.length})</Label>
            {request.lines.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-6">
                No lines.
              </p>
            ) : (
              <PriceTagLinesView
                lines={request.lines}
                priceMode={request.price_mode ?? 'list'}
                isMobile={isMobile}
              />
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
          {/* D1: a promotion is per LINE now (see the Lines table above) -
              there is no single request-level promotion to name here any
              more. */}
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

        {isProofReady && (
          /* Same `attachments` state the Sales Order card above reads (not
             `request.attachments`, which is only ever the snapshot from the
             initial fetch) - one source, so the two can never show a different
             file list for the same request. */
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
        )}
      </>
    );

    const revisionHistoryCard = (
      <RevisionHistory
        entries={revisionHistory.entries}
        loading={revisionHistory.loading}
        error={revisionHistory.error}
        currentAttachments={attachments}
      />
    );

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
          <div className="flex min-w-0 items-center gap-2">
            {/* R3-5/review round 3: the SAME one muted truncating line the
                legacy kinds' header carries - doc number, revision status
                (budget or blocked reason), neighbour counter - beside the
                gear rather than a separate bold heading + colored pill. */}
            {(request.doc_number || revisionStatusText || neighbours) && (
              <span className="min-w-0 truncate text-sm text-muted-foreground">
                {request.doc_number}
                {revisionStatusText && (
                  <>
                    {request.doc_number && <span aria-hidden> · </span>}
                    <span className="text-xs text-muted-foreground/70">
                      {revisionStatusText}
                    </span>
                  </>
                )}
                {neighbours && (
                  <>
                    {(request.doc_number || revisionStatusText) && (
                      <span aria-hidden> · </span>
                    )}
                    <span className="text-xs text-muted-foreground/70">
                      {neighbours.position} / {neighbours.total}
                    </span>
                  </>
                )}
              </span>
            )}
            {/* R3-1/AC-R7: no Edit after submit - a submitted request is
                read-only exactly like a stock inquiry, and a change goes
                through the revision engine instead. ONE gear: Duplicate,
                Download PDF (disabled with a reason until a completed
                export exists), and Revise when the policy allows it.
                Controlled open state so the menu closes itself once the
                download settles, instead of sitting open with a stale item
                until an outside click. */}
            <DetailActionsMenu
              ariaLabel="Price tag request actions"
              open={gearOpen}
              onOpenChange={setGearOpen}
            >
              <DropdownMenuItem
                disabled={!canDownloadPdf || exportPreparing || downloadingPdf}
                onSelect={(event) => {
                  event.preventDefault();
                  void handleDownloadPdf();
                }}
              >
                {downloadingPdf || exportPreparing ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Download className="size-4" />
                )}
                <span>
                  {!canDownloadPdf
                    ? 'Available after approval'
                    : downloadingPdf
                      ? 'Downloading...'
                      : exportPreparing
                        ? 'Preparing your PDF'
                        : exportStatus === 'failed'
                          ? 'PDF failed, try again'
                          : 'Download PDF'}
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
              {revisionPolicy?.allowed && (
                <DropdownMenuItem
                  onSelect={(event) => {
                    event.preventDefault();
                    setGearOpen(false);
                    setReviseMode(true);
                    setReviseReason('');
                  }}
                >
                  <PencilLine className="size-4" />
                  Revise
                </DropdownMenuItem>
              )}
            </DetailActionsMenu>
          </div>
        </div>

        {revisionsTabbed ? (
          <Tabs defaultValue="details">
            {/* Same underlined strip the office detail pages use, and the
                same tab shape SubmissionForm gives the legacy kinds (AC-R7) -
                a record's tabs look the same whichever side of the system,
                and whichever portal form, you are on. */}
            <TabsList variant="line" className="mb-5 w-full justify-start">
              <TabsTrigger value="details">
                <FileText />
                <span>Details</span>
              </TabsTrigger>
              <TabsTrigger value="revisions">
                <History />
                <span>Revisions</span>
              </TabsTrigger>
            </TabsList>
            <TabsContent value="details" className="m-0 space-y-4">
              {detailsContent}
            </TabsContent>
            <TabsContent value="revisions" className="m-0">
              {revisionHistoryCard}
            </TabsContent>
          </Tabs>
        ) : (
          <>
            {detailsContent}
            {revisionHistoryCard}
          </>
        )}
      </div>
    );
  }

  // ---- Edit / create form ----
  return (
    <div className="w-full max-w-5xl mx-auto px-3 pt-4 pb-8 space-y-4">
      {reviseMode && request ? (
        // R3-1: revise mode is the SAME header as the read view - the one
        // muted truncating line (review round 3) - with Cancel / Submit
        // revision where the gear's Revise item was, not a bare heading and
        // a second action row at the bottom of the page.
        <>
          <div className="flex items-center justify-between gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => router.push(`${portalBase(slug)}?type=price_tag_request`)}
            >
              <ArrowLeft className="size-4 mr-1" /> Back
            </Button>
            <div className="flex items-center gap-2">
              <Button variant="outline" onClick={handleCancelRevise} disabled={revising}>
                Cancel
              </Button>
              <Button onClick={handleSubmitRevision} disabled={revising}>
                {revising && <Loader2 className="size-4 mr-1 animate-spin" />}
                Submit revision
              </Button>
            </div>
          </div>
          {(request.doc_number || neighbours) && (
            <span className="min-w-0 truncate text-sm text-muted-foreground">
              {request.doc_number}
              {neighbours && (
                <>
                  {request.doc_number && <span aria-hidden> · </span>}
                  <span className="text-xs text-muted-foreground/70">
                    {neighbours.position} / {neighbours.total}
                  </span>
                </>
              )}
            </span>
          )}
          {/* Review round 3: the reason field in a card matching the
              FormSection rhythm (same border/padding), not a bare label +
              textarea floating between the header and the sections. */}
          <Card className="space-y-1.5 px-4 py-4">
            <Label htmlFor="revision_reason">Reason</Label>
            <Textarea
              id="revision_reason"
              value={reviseReason}
              onChange={(e) => setReviseReason(e.target.value)}
              placeholder="What changed, and why?"
              rows={3}
            />
          </Card>
        </>
      ) : (
        <>
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
        </>
      )}

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
            placeholder="Drop the sales order here, paste a screenshot, or"
            allowedExtensions={attachmentExtensions}
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
            <PriceTagLinesTable
              lines={lines}
              priceMode={priceMode}
              isMobile={isMobile}
              editor={lineEditor}
              showNumberErrors={showNumberErrors}
            />
          )}
          {fieldErrors.lines && (
            <p
              className="text-xs text-destructive"
              data-error-anchor="lines"
            >
              {fieldErrors.lines}
            </p>
          )}
          <Button size="sm" variant="outline" onClick={lineEditor.addLine}>
            <Plus className="size-3.5 mr-1" /> Add line
          </Button>
        </div>
      </FormSection>

      {/* Price - mode only (D1/AC-S1-3, owner ruling 15 Sep): Selling is
          never disabled; its Promotion picker moved onto each line in the
          table above (AC-S1-3), one line can no longer share a single
          request-level promotion with another. Choosing either mode opens
          Additional Information (AC-P8). */}
      <FormSection
        title="Price"
        titleId="price-section-title"
        summary={sectionSummaries.price}
        open={sectionOpen.price}
        onOpenChange={(next) => toggleSection('price', next)}
      >
        <div className="space-y-1.5">
          {/* No repeated "Price" label here - the section title already
              says it (review round 1). */}
          <PriceModeToggle
            value={priceMode}
            labelledBy="price-section-title"
            onChange={(mode) => {
              setPriceModeChosen(true);
              setPriceMode(mode);
              // Direct call (review round 2): `setPriceMode('list')` is a
              // no-op on a fresh form (priceMode is already 'list'), so
              // React bails out of re-rendering and the auto-open effect
              // keyed on `priceMode` never reruns - Additional Information
              // must still open on this click either way (AC-P8).
              openSectionOnce('need_by');
            }}
          />
        </div>
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
        renderRowStatus={(p) => (
          <AIMatchCell
            product={p}
            status={aiMatchStatuses[normalizeAiCode(p.product_code)]}
            picked={aiPicks[normalizeAiCode(p.product_code)] ?? ''}
            onPick={handleAIPick}
          />
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

      {/* Actions - R3-1: a revision (reviseMode, never a draft or new form
          here - see `showEditForm`) has its Cancel / Submit revision in the
          header above, same spot the read view's Revise gear item sat - not
          a second action row down here, and never Delete. Everything else
          (a draft or a brand new form) keeps Save Draft / Submit. */}
      {!reviseMode && (
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
      )}

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
    case 'picked':
      return <span className="text-emerald-700">Matched (picked)</span>;
    default:
      return <span className="text-muted-foreground">Checking...</span>;
  }
}

/** AI-EXTRACT-DYM: a row with no match but with "did you mean" suggestions
 *  adds a picker under its status. Nothing is pre-selected; the row only
 *  becomes a line once the user picks one. */
function AIMatchCell({
  product,
  status,
  picked,
  onPick,
}: {
  product: AIExtractedProductLine;
  status: AIMatchStatus | undefined;
  picked: string;
  onPick: (product: AIExtractedProductLine, productId: string) => void;
}) {
  const suggestions = product.suggestions ?? [];
  if ((status !== 'not_found' && status !== 'picked') || suggestions.length === 0) {
    return <AIMatchStatusLabel status={status} />;
  }
  return (
    <div className="flex min-w-48 flex-col gap-1">
      <AIMatchStatusLabel status={status} />
      <SearchableSelect
        value={picked}
        onChange={(v) => onPick(product, v)}
        options={suggestions.map((s) => ({
          value: s.product_id,
          label: codeWithName(s.product_code, s.product_name),
        }))}
        placeholder="Did you mean?"
        aria-label={`Did you mean, for ${product.product_code ?? 'this row'}`}
        size="sm"
        wrapOptions
        clearable
      />
    </div>
  );
}

