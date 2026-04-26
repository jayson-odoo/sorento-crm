'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQuery, useQueries } from '@tanstack/react-query';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Container } from '@/components/common/container';
import { TruncatedTextCell } from '@/components/common/TruncatedTextCell';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useHasPermission } from '@/hooks/usePermissions';
import { cn } from '@/lib/utils';
import {
  ArrowLeft,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  Download,
  Eye,
  FileText,
  GitBranch,
  Mail,
  Pencil,
  Printer,
  Trash2,
  Undo2,
  Upload,
} from 'lucide-react';
import AttachmentUploadDialog from '@/app/(protected)/resource-management/attachments/components/AttachmentUploadDialog';
import {
  useUploadAttachment,
  useDownloadAttachment,
  useAttachmentTypesList,
} from '@/app/(protected)/resource-management/attachments/hooks/useAttachments';
import {
  getAttachmentMetadata,
  getAttachmentPreviewUrl,
} from '@/app/(protected)/resource-management/attachments/services/attachmentService';
import type { Attachment } from '@/app/(protected)/resource-management/attachments/types/attachment.types';
import { getAuditLogs } from '@/services/auditService';
import type { AuditLogEntry } from '@/types/audit.types';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  applyMasterQuotationTaskBoardSchedule,
  previewMasterQuotationTaskBoardSchedule,
  duplicateMasterQuotation,
  getCommercialProject,
} from '@/app/(protected)/commercial-management/projects/services/commercialProjectService';
import { getCustomer } from '@/app/(protected)/order-management/customers/services/customerService';
import { parseClientNotesMeta } from '@/app/(protected)/order-management/customers/lib/client-notes';
import type { CommercialProjectTaskBoard } from '@/app/(protected)/commercial-management/projects/types/commercialProject.types';
import { masterQuotationDisplayCode } from '@/app/(protected)/commercial-management/quotations/lib/masterQuotationDisplayCode';
import { CommercialEntityTaskBoard } from '@/app/(protected)/commercial-management/shared/components/CommercialEntityTaskBoard';
import { EntityActivitiesDock } from '@/app/(protected)/commercial-management/shared/components/EntityActivitiesDock';
import { QuotationOrderLinesReadOnly } from '@/app/(protected)/commercial-management/quotation-revisions/components/QuotationOrderLinesReadOnly';
import { QuotationEmailSendDialog } from '@/app/(protected)/commercial-management/quotation-revisions/components/QuotationEmailSendDialog';
import {
  downloadQuotationPdf,
  openQuotationPdfPreview,
} from '@/app/(protected)/commercial-management/quotation-revisions/services/quotationPrintEmailService';
import type { QuotationPricingLineHint } from '@/app/(protected)/commercial-management/quotation-revisions/lib/quotationLinePricing';
const CM = '/api/commercial-management';

function formatAttachmentBytes(bytes: number | null | undefined): string {
  if (bytes == null || Number.isNaN(bytes)) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function uploadCalendarDay(iso: Date | string | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function newLineKey(): string {
  if (typeof globalThis.crypto !== 'undefined' && typeof globalThis.crypto.randomUUID === 'function') {
    return globalThis.crypto.randomUUID();
  }
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

type QuotationStage = { stage_code: string; stage_name: string; is_terminal?: boolean; is_cancelled?: boolean };

type MasterDetail = {
  id: string;
  project_id?: string | null;
  customer_id?: string | null;
  tender_id: string;
  tender_code: string;
  quotation_code: string;
  sales_order_code?: string | null;
  title: string;
  path_role: string;
  quotation_stage?: QuotationStage | null;
  valid_until?: string | null;
  payment_terms?: string | null;
  description?: string | null;
  remark?: string | null;
  quoted_amount?: string | null;
  quoted_currency?: string | null;
  pricing_approval_status?: string;
  current_working_revision_id?: string | null;
  final_selected_revision_id?: string | null;
  /** Shared with projects: `{ tasks: [...] }` — master-level, not revision-scoped. */
  task_board?: CommercialProjectTaskBoard | Record<string, unknown> | null;
  quotation_package_template_id?: string | null;
  quotation_package_template_name?: string | null;
  updated_at?: string;
};

type RevisionRow = {
  id: string;
  revision_number: number;
  revision_notes: string | null;
  is_current_working: boolean;
  is_final_selected: boolean;
  pricing_snapshot: Record<string, unknown>;
  created_at?: string;
  computed_valid_until?: string | null;
  pricing_line_hints?: QuotationPricingLineHint[] | null;
};

type SelectOpt = { code: string; label: string };

type AttachmentRow = { id: string; attachment_id: string; file_name?: string | null };

type OrderLine = {
  _key: string;
  product_id: string;
  product_code?: string;
  brand?: string;
  description?: string;
  product_image_attachment_ids?: string[];
  technical_spec_attachment_ids?: string[];
  is_optional?: boolean;
  qty: string;
  uom_code: string;
  unit_price: string;
  discount_pct: string;
  discount_amt: string;
  tax_rate_code: string;
};

function emptyMeta() {
  return {
    customer_id: '',
    seller_reference: '',
    customer_reference: '',
    customer_label: '',
    project_title: '',
    customer_pic_name: '',
    customer_phone: '',
    customer_email: '',
    customer_attention_to: '',
    issued_on: '',
    salesperson_user_id: '',
    payment_term_code: '',
    notes: '',
    terms_html: '',
    quotation_validity_days: '',
    quotation_package_template_id: '',
    quotation_package_template_name: '',
  };
}

function qualStr(q: Record<string, unknown>, key: string): string {
  const v = q[key];
  if (v == null || v === '') return '';
  return String(v).trim();
}

function parseAttachmentIds(v: unknown): string[] {
  if (!Array.isArray(v)) return [];
  return v.map((x) => String(x)).filter(Boolean);
}

function parseSnapshot(snap: Record<string, unknown> | undefined) {
  const metaRaw = snap?.quotation_meta;
  const meta = typeof metaRaw === 'object' && metaRaw !== null ? { ...emptyMeta(), ...(metaRaw as Record<string, string>) } : emptyMeta();
  const itemsRaw = snap?.order_items;
  const lines: OrderLine[] = [];
  if (Array.isArray(itemsRaw)) {
    for (const row of itemsRaw) {
      if (!row || typeof row !== 'object') continue;
      const r = row as Record<string, unknown>;
      lines.push({
        _key: typeof r._key === 'string' && r._key ? String(r._key) : newLineKey(),
        product_id: String(r.product_id ?? ''),
        product_code: r.product_code != null ? String(r.product_code) : '',
        brand: r.brand != null ? String(r.brand) : '',
        description: r.description != null ? String(r.description) : '',
        product_image_attachment_ids: parseAttachmentIds(r.product_image_attachment_ids),
        technical_spec_attachment_ids: parseAttachmentIds(r.technical_spec_attachment_ids),
        is_optional: Boolean(r.is_optional),
        qty: String(r.qty ?? r.quantity ?? '1'),
        uom_code: String(r.uom_code ?? ''),
        unit_price: String(r.unit_price ?? '0'),
        discount_pct: String(r.discount_pct ?? r.discount_percent ?? ''),
        discount_amt: String(r.discount_amt ?? r.discount_amount ?? ''),
        tax_rate_code: String(r.tax_rate_code ?? ''),
      });
    }
  }
  return { meta, lines };
}

function lineNetAmount(l: OrderLine): number {
  const q = Number(l.qty) || 0;
  const up = Number(l.unit_price) || 0;
  let line = q * up;
  const dp = Number(l.discount_pct) || 0;
  if (dp > 0) line *= 1 - dp / 100;
  const da = Number(l.discount_amt) || 0;
  if (da > 0) line -= da;
  return Math.max(0, line);
}

function lineGross(l: OrderLine): number {
  const q = Number(l.qty) || 0;
  const up = Number(l.unit_price) || 0;
  return Math.max(0, q * up);
}

function lineTotals(lines: OrderLine[]) {
  let sub = 0;
  let gross = 0;
  for (const l of lines) {
    if (l.is_optional) continue;
    gross += lineGross(l);
    sub += lineNetAmount(l);
  }
  return { subtotal: sub, discountTotal: Math.max(0, gross - sub), gross };
}

function formatMoneyAmount(amount: number, currencyCode: string | null | undefined) {
  const code = (currencyCode || 'MYR').toUpperCase();
  try {
    return new Intl.NumberFormat('en-MY', { style: 'currency', currency: code }).format(amount);
  } catch {
    return `${code} ${amount.toFixed(2)}`;
  }
}

function snapshotSubtotal(snap: Record<string, unknown> | undefined): number {
  const { lines } = parseSnapshot(snap);
  return lineTotals(lines).subtotal;
}

/** ISO datetime from API → local calendar YYYY-MM-DD */
function formatRevisionCalendarDate(iso: string | undefined): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 10);
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** Full quotation reference includes revision suffix (e.g. QT-…-3). Working vs historical only affects the "Current" badge, not the label. */
function revisionDisplayCode(quotationCode: string, r: Pick<RevisionRow, 'revision_number'>): string {
  return `${quotationCode}-${r.revision_number}`;
}

const AUDIT_PAGE_SIZE = 15;
const MAX_JSON_DEPTH = 6;

function formatAuditDateTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });
}

/** One table row per changed field (matches Figma columns). */
type AuditTrailFlatRow = {
  id: string;
  user: string;
  action: string;
  field: string;
  oldVal: unknown;
  newVal: unknown;
  changed_at: string;
};

function flattenAuditEntry(row: AuditLogEntry): AuditTrailFlatRow[] {
  const oldV = row.old_values;
  const newV = row.new_values;
  const keys = new Set([
    ...(oldV && typeof oldV === 'object' && !Array.isArray(oldV) ? Object.keys(oldV as object) : []),
    ...(newV && typeof newV === 'object' && !Array.isArray(newV) ? Object.keys(newV as object) : []),
  ]);
  if (keys.size === 0) {
    return [
      {
        id: `${row.id}-entry`,
        user: (row.user_display_name || '').trim() || '—',
        action: row.action,
        field: row.description?.trim() || row.entity_type || 'Change',
        oldVal: oldV ?? null,
        newVal: newV ?? null,
        changed_at: row.changed_at,
      },
    ];
  }
  const orec = oldV && typeof oldV === 'object' && !Array.isArray(oldV) ? (oldV as Record<string, unknown>) : null;
  const nrec = newV && typeof newV === 'object' && !Array.isArray(newV) ? (newV as Record<string, unknown>) : null;
  return Array.from(keys).map((field) => ({
    id: `${row.id}-${field}`,
    user: (row.user_display_name || '').trim() || '—',
    action: row.action,
    field,
    oldVal: orec ? orec[field] : undefined,
    newVal: nrec ? nrec[field] : undefined,
    changed_at: row.changed_at,
  }));
}

function JsonValueDisplay({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (depth > MAX_JSON_DEPTH) {
    return <span className="text-muted-foreground">…</span>;
  }
  if (value === null || value === undefined) {
    return <span className="text-[#99a1af]">—</span>;
  }
  const t = typeof value;
  if (t === 'string' || t === 'number' || t === 'boolean') {
    return <span className="break-words text-[#101828]">{String(value)}</span>;
  }
  if (Array.isArray(value)) {
    if (value.length === 0) {
      return <span className="text-muted-foreground">[]</span>;
    }
    const allPlainObjects = value.every(
      (v) => v !== null && typeof v === 'object' && !Array.isArray(v),
    );
    if (allPlainObjects) {
      const keys = Array.from(new Set(value.flatMap((o) => Object.keys(o as object))));
      return (
        <div className="max-h-48 overflow-auto rounded border border-[#e5e7eb]">
          <table className="w-full border-collapse text-left text-xs">
            <thead>
              <tr className="border-b border-[#e5e7eb] bg-[#f9fafb]">
                {keys.map((k) => (
                  <th key={k} className="whitespace-nowrap px-2 py-1 font-medium text-[#4a5565]">
                    {k}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {value.map((item, i) => (
                <tr key={i} className="border-b border-[#e5e7eb] last:border-0">
                  {keys.map((k) => (
                    <td key={k} className="max-w-[200px] px-2 py-1 align-top">
                      <JsonValueDisplay value={(item as Record<string, unknown>)[k]} depth={depth + 1} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    }
    return (
      <ul className="list-disc space-y-1 ps-4">
        {value.map((item, i) => (
          <li key={i}>
            <JsonValueDisplay value={item} depth={depth + 1} />
          </li>
        ))}
      </ul>
    );
  }
  const entries = Object.entries(value as Record<string, unknown>);
  if (entries.length === 0) {
    return <span className="text-muted-foreground">{'{}'}</span>;
  }
  return (
    <div className="max-h-56 overflow-auto rounded border border-[#e5e7eb] bg-white">
      <table className="w-full border-collapse text-left text-xs">
        <tbody>
          {entries.map(([k, v]) => (
            <tr key={k} className="border-b border-[#e5e7eb] last:border-0">
              <td className="max-w-[min(140px,30vw)] shrink-0 bg-[#f9fafb] px-2 py-1 align-top font-medium text-[#4a5565]">
                {k}
              </td>
              <td className="min-w-[120px] px-2 py-1 align-top">
                <JsonValueDisplay value={v} depth={depth + 1} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AuditValueCell({ value, tone }: { value: unknown; tone: 'old' | 'new' }) {
  if (value === null || value === undefined) {
    return <span className="text-[#99a1af]">—</span>;
  }
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return (
      <span
        className={cn('break-words', tone === 'old' ? 'text-[#4a5565]' : 'text-[#101828]')}
      >
        {String(value)}
      </span>
    );
  }
  return (
    <div className="min-w-[140px] max-w-md">
      <JsonValueDisplay value={value} />
    </div>
  );
}

type MetaState = ReturnType<typeof emptyMeta>;

function QuotationDocumentRow({
  attachmentId,
  fileName,
  meta,
  canEdit,
  onUnlink,
  onPreview,
  onDownload,
  downloadPending,
}: {
  attachmentId: string;
  fileName: string | null | undefined;
  meta: Attachment | undefined;
  canEdit: boolean;
  onUnlink: () => void;
  onPreview: () => void;
  onDownload: () => void;
  downloadPending: boolean;
}) {
  const displayName = meta?.original_filename || fileName || attachmentId;
  const size = formatAttachmentBytes(meta?.file_size_bytes ?? null);
  const uploader = (meta?.uploaded_by_user?.name || '').trim() || meta?.uploaded_by?.trim() || '—';
  const day = uploadCalendarDay(meta?.uploaded_at);

  return (
    <div className="flex min-h-[72px] items-center justify-between gap-3 border-b border-[#e5e7eb] px-4 py-3 last:border-b-0">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex size-10 shrink-0 items-center justify-center rounded-[14px] bg-[#ffe2e2] text-[#e7000b]">
          <FileText className="size-5" aria-hidden />
        </div>
        <div className="min-w-0">
          <button
            type="button"
            className="block max-w-full truncate text-left text-sm text-[#101828] hover:underline"
            onClick={onPreview}
          >
            {displayName}
          </button>
          <p className="text-xs text-[#4a5565]">
            {size} • Uploaded by {uploader} on {day}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 rounded-[10px] text-[#4a5565] hover:text-[#0a0a0a]"
          title="Preview"
          onClick={onPreview}
        >
          <Eye className="size-4" />
        </Button>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="size-8 rounded-[10px] text-[#4a5565] hover:text-[#0a0a0a]"
          title="Download"
          disabled={downloadPending}
          onClick={onDownload}
        >
          <Download className="size-4" />
        </Button>
        {canEdit ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-8 rounded-[10px] text-[#e7000b] hover:bg-red-50 hover:text-[#e7000b]"
            title="Remove from quotation"
            onClick={onUnlink}
          >
            <Trash2 className="size-4" />
          </Button>
        ) : null}
      </div>
    </div>
  );
}

export default function QuotationRevisionsPage() {
  const router = useRouter();
  const { status } = useSession();
  const searchParams = useSearchParams();
  const searchParamsKey = useMemo(() => searchParams.toString(), [searchParams]);
  const projectIdFromUrl = searchParams.get('project');
  const hasDeepLink = !!(searchParams.get('tender') && searchParams.get('quotation'));
  const canViewMasterQuotations = useHasPermission('commercial_core.master_quotations.view');
  const canEditMaster = useHasPermission('commercial_core.master_quotations.edit');
  const canAddMasterQuotation = useHasPermission('commercial_core.master_quotations.add');
  const canEditRevision = useHasPermission('commercial_core.quotation_revisions.edit');

  const [tenderCode, setTenderCode] = useState('');
  const [quotationCode, setQuotationCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [mainTab, setMainTab] = useState('overview');
  const [overviewSubTab, setOverviewSubTab] = useState<'orderLines' | 'internalNotes'>('orderLines');
  const [showOrderLineUnitCost, setShowOrderLineUnitCost] = useState(true);
  const [bootstrapError, setBootstrapError] = useState<string | null>(null);

  const [master, setMaster] = useState<MasterDetail | null>(null);
  const [taskBoard, setTaskBoard] = useState<CommercialProjectTaskBoard>({ tasks: [] });
  const [revisions, setRevisions] = useState<RevisionRow[]>([]);
  const [selectedRevisionId, setSelectedRevisionId] = useState<string | null>(null);

  const [meta, setMeta] = useState<MetaState>(() => emptyMeta());
  const [lines, setLines] = useState<OrderLine[]>([]);

  const [paymentTerms, setPaymentTerms] = useState<SelectOpt[]>([]);
  const [uoms, setUoms] = useState<SelectOpt[]>([]);
  const [taxRates, setTaxRates] = useState<SelectOpt[]>([]);
  const [mqStages, setMqStages] = useState<SelectOpt[]>([]);
  const [users, setUsers] = useState<{ id: string; name: string | null; email: string }[]>([]);

  const [masterAttachRows, setMasterAttachRows] = useState<AttachmentRow[]>([]);
  const [revAttachRows, setRevAttachRows] = useState<AttachmentRow[]>([]);
  const [masterLinkAttId, setMasterLinkAttId] = useState('');
  const [revLinkAttId, setRevLinkAttId] = useState('');
  const [uploadMasterOpen, setUploadMasterOpen] = useState(false);
  const [uploadRevOpen, setUploadRevOpen] = useState(false);
  const [docMasterDrag, setDocMasterDrag] = useState(false);
  const [docRevDrag, setDocRevDrag] = useState(false);
  /** 1-based index into `revAttachRows` for document carousel (Documents tab). */
  const [documentsNavIndex, setDocumentsNavIndex] = useState(1);
  const docRowRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const [quotationPdfLoading, setQuotationPdfLoading] = useState(false);
  const [quotationEmailOpen, setQuotationEmailOpen] = useState(false);

  const [auditEntries, setAuditEntries] = useState<AuditLogEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);
  const [historyPage, setHistoryPage] = useState(1);

  useEffect(() => {
    const t = searchParams.get('tender');
    const q = searchParams.get('quotation');
    if (t) setTenderCode(t);
    if (q) setQuotationCode(q);
  }, [searchParams]);

  const loadSelects = useCallback(async () => {
    const [ptRes, txRes, uomRes, stRes, uRes] = await Promise.all([
      apiFetch('/api/v1/commercial/process-config/settings/payment-terms/select'),
      apiFetch('/api/v1/commercial/process-config/settings/tax-rates/select'),
      apiFetch('/api/v1/master-data/units-of-measure/select'),
      apiFetch('/api/v1/commercial/process-config/master-quotation-stages/select'),
      apiFetch('/api/user-management/users/select'),
    ]);
    if (ptRes.ok) {
      const j = (await ptRes.json()) as { data: SelectOpt[] };
      setPaymentTerms(j.data ?? []);
    }
    if (txRes.ok) {
      const j = (await txRes.json()) as { data: SelectOpt[] };
      setTaxRates(j.data ?? []);
    }
    if (uomRes.ok) {
      const raw = (await uomRes.json()) as Array<{ uom_code: string; uom_name: string }>;
      setUoms(
        (raw ?? []).map((r) => ({
          code: r.uom_code,
          label: r.uom_name ? `${r.uom_name} (${r.uom_code})` : r.uom_code,
        })),
      );
    }
    if (stRes.ok) {
      const j = (await stRes.json()) as { data: SelectOpt[] };
      setMqStages(j.data ?? []);
    }
    if (uRes.ok) {
      const raw = (await uRes.json()) as unknown;
      const arr = Array.isArray(raw) ? raw : (raw as { data?: unknown[] })?.data;
      if (Array.isArray(arr)) {
        setUsers(
          arr.map((x: unknown) => {
            const o = x as Record<string, unknown>;
            return {
              id: String(o.id ?? o.user_id ?? ''),
              name: (o.name as string) ?? null,
              email: String(o.email ?? ''),
            };
          }).filter((u) => u.id),
        );
      }
    }
  }, []);

  useEffect(() => {
    void loadSelects();
  }, [loadSelects]);

  const refreshMasterAttachmentLinks = useCallback(
    async (masterId: string) => {
      if (!canViewMasterQuotations) {
        setMasterAttachRows([]);
        return;
      }
      const mRes = await apiFetch(`${CM}/master-quotations/${masterId}/attachment-links`);
      if (!mRes.ok) {
        setMasterAttachRows([]);
        return;
      }
      const raw = (await mRes.json()) as Array<{
        id: string;
        attachment_id: string;
        file_name?: string | null;
        original_filename?: string | null;
      }>;
      setMasterAttachRows(
        raw.map((x) => ({
          id: x.id,
          attachment_id: x.attachment_id,
          file_name: x.file_name ?? x.original_filename ?? null,
        })),
      );
    },
    [canViewMasterQuotations],
  );

  const loadRevisionAttachments = useCallback(async (revisionId: string) => {
    const res = await apiFetch(`${CM}/quotation-revisions/${revisionId}/attachment-links`);
    if (!res.ok) {
      setRevAttachRows([]);
      return;
    }
    const data = (await res.json()) as AttachmentRow[];
    setRevAttachRows(data);
  }, []);

  const load = async (override?: { tender?: string; quotation?: string }) => {
    const tc = (override?.tender ?? tenderCode).trim();
    const qc = (override?.quotation ?? quotationCode).trim();
    if (!tc || !qc) {
      toast.error('Enter tender code and quotation code.');
      return;
    }
    setLoading(true);
    setBootstrapError(null);
    try {
      const encT = encodeURIComponent(tc);
      const encQ = encodeURIComponent(qc);
      const dRes = await apiFetch(`${CM}/tenders/by-code/${encT}/master-quotations/by-code/${encQ}`);
      if (!dRes.ok) {
        const msg = 'Could not load this quotation.';
        toast.error(msg);
        setBootstrapError(msg);
        setMaster(null);
        setRevisions([]);
        setMasterAttachRows([]);
        setRevAttachRows([]);
        return;
      }
      const detail = (await dRes.json()) as MasterDetail;
      setMaster(detail);
      void refreshMasterAttachmentLinks(detail.id);

      const rRes = await apiFetch(`${CM}/master-quotations/${detail.id}/revisions`);
      if (!rRes.ok) {
        toast.error('Failed to load revisions.');
        setRevisions([]);
        return;
      }
      const revs = (await rRes.json()) as RevisionRow[];
      setRevisions(revs);
      const working = detail.current_working_revision_id;
      const pick = working && revs.some((r) => r.id === working) ? working : revs.length ? revs[revs.length - 1].id : null;
      setSelectedRevisionId(pick);
      if (pick) {
        const rev = revs.find((r) => r.id === pick);
        const { meta: m, lines: ln } = parseSnapshot(rev?.pricing_snapshot as Record<string, unknown>);
        setMeta(m);
        setLines(ln.length ? ln : []);
      } else {
        setMeta(emptyMeta());
        setLines([]);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to load quotation.';
      toast.error(msg);
      setBootstrapError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!master) {
      setTaskBoard({ tasks: [] });
      return;
    }
    const tb = master.task_board;
    setTaskBoard(
      tb && typeof tb === 'object' ? (tb as CommercialProjectTaskBoard) : { tasks: [] },
    );
  }, [master]);

  useEffect(() => {
    setDocumentsNavIndex(1);
  }, [selectedRevisionId]);

  useEffect(() => {
    const n = revAttachRows.length;
    setDocumentsNavIndex((prev) => {
      if (n === 0) return 1;
      return Math.min(Math.max(prev, 1), n);
    });
  }, [revAttachRows.length]);

  useEffect(() => {
    const n = revAttachRows.length;
    if (n === 0) return;
    const idx = Math.min(Math.max(documentsNavIndex, 1), n);
    const row = revAttachRows[idx - 1];
    if (!row) return;
    const el = docRowRefs.current.get(row.attachment_id);
    requestAnimationFrame(() => {
      el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    });
  }, [documentsNavIndex, revAttachRows]);

  const persistMasterTaskBoard = useCallback(
    async (next: CommercialProjectTaskBoard) => {
      if (!master?.id || !canEditMaster) return;
      const mid = master.id;
      setTaskBoard(next);
      try {
        const res = await apiFetch(`${CM}/master-quotations/${mid}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_board: next }),
        });
        if (!res.ok) {
          toast.error('Could not save tasks.');
          const rec = await apiFetch(`${CM}/master-quotations/${mid}`);
          if (rec.ok) setMaster((await rec.json()) as MasterDetail);
          return;
        }
        const d = (await res.json()) as MasterDetail;
        setMaster(d);
      } catch {
        toast.error('Could not save tasks.');
        const rec = await apiFetch(`${CM}/master-quotations/${mid}`);
        if (rec.ok) setMaster((await rec.json()) as MasterDetail);
      }
    },
    [master?.id, canEditMaster],
  );

  useEffect(() => {
    const t = searchParams.get('tender');
    const q = searchParams.get('quotation');
    if (t && q && status === 'authenticated') {
      void load({ tender: t, quotation: q });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load when URL query or auth changes only
  }, [status, searchParamsKey]);

  const selectedRevision = useMemo(
    () => revisions.find((r) => r.id === selectedRevisionId) ?? null,
    [revisions, selectedRevisionId],
  );

  const nextStageLabel = useMemo(() => {
    if (!master?.quotation_stage) return null;
    const cur = master.quotation_stage.stage_code;
    const idx = mqStages.findIndex((s) => s.code === cur);
    if (idx < 0 || idx >= mqStages.length - 1) return null;
    return mqStages[idx + 1]?.label ?? mqStages[idx + 1]?.code ?? null;
  }, [master, mqStages]);

  const previousStageLabel = useMemo(() => {
    if (!master?.quotation_stage) return null;
    const cur = master.quotation_stage.stage_code;
    const idx = mqStages.findIndex((s) => s.code === cur);
    if (idx <= 0) return null;
    return mqStages[idx - 1]?.label ?? mqStages[idx - 1]?.code ?? null;
  }, [master, mqStages]);

  const atTerminal = !!master?.quotation_stage?.is_terminal;
  const onPrintQuotationPdf = useCallback(async () => {
    if (!selectedRevisionId) return;
    setQuotationPdfLoading(true);
    try {
      await downloadQuotationPdf(selectedRevisionId);
      toast.success('PDF downloaded');
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'PDF failed');
    } finally {
      setQuotationPdfLoading(false);
    }
  }, [selectedRevisionId]);
  const onPreviewQuotationPdf = useCallback(async () => {
    if (!selectedRevisionId) return;
    setQuotationPdfLoading(true);
    try {
      await openQuotationPdfPreview(selectedRevisionId);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Preview failed');
    } finally {
      setQuotationPdfLoading(false);
    }
  }, [selectedRevisionId]);
  const moveDisabled = !canEditMaster || !master || atTerminal || !nextStageLabel;

  const primaryStageActionLabel = useMemo(() => {
    if (!master) return '—';
    if (atTerminal) return 'Final stage';
    if (!nextStageLabel) return 'No next stage';
    return nextStageLabel;
  }, [master, atTerminal, nextStageLabel]);

  const canOpenEditQuotation = canEditMaster && canEditRevision && !atTerminal;
  const showQuotationOutputMenu = atTerminal && !!selectedRevisionId && canViewMasterQuotations;
  const showStageMenu =
    (canEditMaster && !!previousStageLabel) ||
    canEditRevision ||
    canAddMasterQuotation ||
    (canEditMaster && showQuotationOutputMenu);
  const showOutputMenuSeparator =
    showQuotationOutputMenu &&
    (canAddMasterQuotation ||
      (!!canEditMaster && !!previousStageLabel) ||
      canOpenEditQuotation ||
      canEditRevision);

  const editQuotationHref = useMemo(() => {
    const p = new URLSearchParams();
    const tc = (searchParams.get('tender') || tenderCode).trim();
    const qc = (searchParams.get('quotation') || quotationCode).trim();
    if (!tc || !qc) return '#';
    p.set('tender', tc);
    p.set('quotation', qc);
    const proj = searchParams.get('project') || projectIdFromUrl;
    if (proj) p.set('project', proj);
    return `/commercial-management/quotation-revisions/edit?${p.toString()}`;
  }, [searchParams, tenderCode, quotationCode, projectIdFromUrl]);

  const duplicateQuotation = useCallback(async () => {
    if (!master?.id) return;
    try {
      const dup = await duplicateMasterQuotation(master.id);
      const label = masterQuotationDisplayCode({
        quotation_code: dup.quotation_code,
        current_working_revision_number: 1,
      });
      toast.success(`Quotation ${label} copied successfully`);
      const proj = dup.project_id ?? projectIdFromUrl ?? searchParams.get('project');
      const q = new URLSearchParams();
      q.set('tender', dup.tender_code);
      q.set('quotation', dup.quotation_code);
      if (proj) q.set('project', String(proj));
      router.push(`/commercial-management/quotation-revisions?${q.toString()}`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Failed to duplicate quotation');
    }
  }, [master?.id, projectIdFromUrl, router, searchParams]);

  useEffect(() => {
    if (!selectedRevision) return;
    const { meta: m, lines: ln } = parseSnapshot(selectedRevision.pricing_snapshot as Record<string, unknown>);
    setMeta(m);
    setLines(ln.length ? ln : []);
  }, [selectedRevisionId, selectedRevision]);

  useEffect(() => {
    if (!selectedRevisionId) {
      setRevAttachRows([]);
      return;
    }
    void loadRevisionAttachments(selectedRevisionId);
  }, [selectedRevisionId, loadRevisionAttachments]);

  useEffect(() => {
    const pid = searchParams.get('project');
    if (!master?.project_id || !pid) return;
    if (master.project_id !== pid) {
      toast.warning('This quotation is not linked to the project from this link.');
    }
  }, [master?.project_id, searchParamsKey, searchParams]);

  useEffect(() => {
    if (!master || mainTab !== 'history') return;
    let cancelled = false;
    void (async () => {
      setAuditLoading(true);
      try {
        const mqLogs = await getAuditLogs({
          entity_type: 'commercial_master_quotation',
          entity_id: master.id,
          limit: 100,
        });
        const revParts = await Promise.all(
          revisions.map((r) =>
            getAuditLogs({
              entity_type: 'commercial_quotation_revision',
              entity_id: r.id,
              limit: 100,
            }).catch(() => ({
              data: [] as AuditLogEntry[],
              pagination: { total: 0, page: 1, limit: 100 },
              empty: true,
            })),
          ),
        );
        if (cancelled) return;
        const merged = [...mqLogs.data, ...revParts.flatMap((x) => x.data)].sort(
          (a, b) => new Date(b.changed_at).getTime() - new Date(a.changed_at).getTime(),
        );
        setAuditEntries(merged);
      } catch {
        if (!cancelled) toast.error('Could not load history.');
      } finally {
        if (!cancelled) setAuditLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [master, mainTab, revisions]);

  const auditFlatRows = useMemo(() => auditEntries.flatMap(flattenAuditEntry), [auditEntries]);

  const historyPageCount = Math.max(1, Math.ceil(auditFlatRows.length / AUDIT_PAGE_SIZE) || 1);

  const paginatedAuditRows = useMemo(() => {
    const start = (historyPage - 1) * AUDIT_PAGE_SIZE;
    return auditFlatRows.slice(start, start + AUDIT_PAGE_SIZE);
  }, [auditFlatRows, historyPage]);

  useEffect(() => {
    setHistoryPage(1);
  }, [auditEntries.length, master?.id]);

  useEffect(() => {
    setHistoryPage((p) => Math.min(p, historyPageCount));
  }, [historyPageCount]);

  const linkMasterAttachment = async () => {
    if (!master || !masterLinkAttId.trim()) return;
    const res = await apiFetch(`${CM}/master-quotations/${master.id}/attachment-links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attachment_id: masterLinkAttId.trim() }),
    });
    if (!res.ok) {
      toast.error('Link failed.');
      return;
    }
    toast.success('Linked.');
    setMasterLinkAttId('');
    void refreshMasterAttachmentLinks(master.id);
  };

  const unlinkMasterAttachment = async (linkId: string) => {
    if (!master) return;
    const res = await apiFetch(`${CM}/master-quotations/${master.id}/attachment-links/${linkId}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      toast.error('Unlink failed.');
      return;
    }
    toast.success('Removed.');
    void refreshMasterAttachmentLinks(master.id);
  };

  const linkRevisionAttachment = async () => {
    if (!selectedRevisionId || !revLinkAttId.trim()) return;
    const res = await apiFetch(`${CM}/quotation-revisions/${selectedRevisionId}/attachment-links`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ attachment_id: revLinkAttId.trim() }),
    });
    if (!res.ok) {
      toast.error('Link failed.');
      return;
    }
    toast.success('Linked.');
    setRevLinkAttId('');
    void loadRevisionAttachments(selectedRevisionId);
  };

  const unlinkRevisionAttachment = async (linkId: string) => {
    if (!selectedRevisionId) return;
    const res = await apiFetch(
      `${CM}/quotation-revisions/${selectedRevisionId}/attachment-links/${linkId}`,
      { method: 'DELETE' },
    );
    if (!res.ok) {
      toast.error('Unlink failed.');
      return;
    }
    toast.success('Unlinked.');
    void loadRevisionAttachments(selectedRevisionId);
  };

  const advanceStage = async () => {
    if (!master || moveDisabled) return;
    const res = await apiFetch(`${CM}/master-quotations/${master.id}/advance-stage`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast.error((err as { detail?: string }).detail || 'Could not advance stage');
      return;
    }
    toast.success('Stage updated.');
    const d = (await res.json()) as MasterDetail;
    setMaster((prev) => (prev ? { ...prev, ...d } : d));
    await load();
  };

  const retreatStage = async () => {
    if (!master || !previousStageLabel) return;
    const res = await apiFetch(`${CM}/master-quotations/${master.id}/retreat-stage`, { method: 'POST' });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast.error((err as { detail?: string }).detail || 'Could not go to previous stage');
      return;
    }
    toast.success('Stage updated.');
    const d = (await res.json()) as MasterDetail;
    setMaster((prev) => (prev ? { ...prev, ...d } : d));
    await load();
  };

  const createRevision = async (opts?: { copyFromRevisionId?: string | null }) => {
    if (!master) return;
    const copyFrom =
      opts?.copyFromRevisionId !== undefined
        ? opts.copyFromRevisionId
        : master.current_working_revision_id ?? undefined;
    const res = await apiFetch(`${CM}/master-quotations/${master.id}/revisions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...(copyFrom ? { copy_from_revision_id: copyFrom } : {}),
      }),
    });
    if (!res.ok) {
      toast.error('Could not create revision.');
      return;
    }
    toast.success('Revision created.');
    await load();
  };

  /** Point working copy at an existing revision (no new row). Requires master quotation edit permission. */
  const restoreVersionAsWorking = async (revisionId: string) => {
    if (!master || !canEditMaster) return;
    const res = await apiFetch(`${CM}/master-quotations/${master.id}/current-revision`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ revision_id: revisionId }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      toast.error((err as { detail?: string }).detail || 'Could not set current revision.');
      return;
    }
    toast.success('Current revision updated.');
    await load();
  };

  const totals = lineTotals(lines);

  const quotationDisplayLabel = useMemo(() => {
    if (!master) return '';
    if (selectedRevision) return `${master.quotation_code}-${selectedRevision.revision_number}`;
    const wrNum = revisions.find((r) => r.id === master.current_working_revision_id)?.revision_number;
    if (wrNum != null) return `${master.quotation_code}-${wrNum}`;
    return master.quotation_code;
  }, [master, selectedRevision, revisions]);

  const effectiveProjectId = master?.project_id || projectIdFromUrl || '';

  const { data: projectCtx } = useQuery({
    queryKey: ['commercial-project-ctx', effectiveProjectId],
    queryFn: () => getCommercialProject(effectiveProjectId),
    enabled: Boolean(effectiveProjectId && master),
  });
  const customerIdForQuotation = (
    meta.customer_id ||
    master?.customer_id ||
    projectCtx?.customer_id ||
    ''
  )
    .trim();
  const { data: customerCtx } = useQuery({
    queryKey: ['quotation-customer-ctx', customerIdForQuotation],
    queryFn: () => getCustomer(customerIdForQuotation),
    enabled: Boolean(customerIdForQuotation),
  });

  const deliveryAddressLine = useMemo(() => {
    const parts = [
      projectCtx?.address_line_1,
      projectCtx?.address_line_2,
      projectCtx?.postcode,
      projectCtx?.city,
      projectCtx?.state,
      projectCtx?.country,
    ]
      .map((x) => (x || '').trim())
      .filter(Boolean);
    return parts.length ? parts.join(', ') : '—';
  }, [
    projectCtx?.address_line_1,
    projectCtx?.address_line_2,
    projectCtx?.postcode,
    projectCtx?.city,
    projectCtx?.state,
    projectCtx?.country,
  ]);

  const paymentTermLabel = useMemo(() => {
    if (meta.payment_term_code) {
      return paymentTerms.find((p) => p.code === meta.payment_term_code)?.label ?? meta.payment_term_code;
    }
    const t = (master?.payment_terms || '').trim();
    return t || '—';
  }, [meta.payment_term_code, paymentTerms, master?.payment_terms]);

  const clientDisplay = useMemo(() => {
    const fromMeta = meta.customer_label?.trim();
    if (fromMeta) return fromMeta;
    const fromCustomerCtx = customerCtx?.customer_name?.trim();
    if (fromCustomerCtx) return fromCustomerCtx;
    const fromProject = projectCtx?.customer_name?.trim();
    if (fromProject) return fromProject;
    return meta.customer_label?.trim() || '—';
  }, [customerCtx?.customer_name, projectCtx?.customer_name, meta.customer_label]);
  const customerNotesMeta = useMemo(() => parseClientNotesMeta(customerCtx?.notes), [customerCtx?.notes]);
  const clientPhoneDisplay = (meta.customer_phone || customerCtx?.phone_number || '').trim() || '—';
  const clientEmailDisplay = (meta.customer_email || customerCtx?.email || '').trim() || '—';
  const attentionToDisplay =
    (meta.customer_attention_to || meta.customer_pic_name || customerNotesMeta.picName || '').trim() || '—';
  const projectDisplayTitle = (projectCtx?.title || meta.project_title || '').trim() || effectiveProjectId || '—';
  const sellerReferenceDisplay = (meta.seller_reference || '').trim() || '—';
  const customerReferenceDisplay = (meta.customer_reference || '').trim() || '—';

  const validThrough = master?.valid_until ? String(master.valid_until).slice(0, 10) : '';
  const validityOk = useMemo(() => {
    if (!validThrough) return null;
    const t = new Date(validThrough + 'T12:00:00');
    if (Number.isNaN(t.getTime())) return null;
    return t >= new Date(new Date().toDateString());
  }, [validThrough]);

  const sortedRevisions = useMemo(
    () => [...revisions].sort((a, b) => b.revision_number - a.revision_number),
    [revisions],
  );

  const revisionValidThrough = useMemo(() => {
    if (!selectedRevision) return '';
    if (selectedRevision.computed_valid_until) {
      return String(selectedRevision.computed_valid_until).slice(0, 10);
    }
    return validThrough;
  }, [selectedRevision, validThrough]);

  const validityOkForRevision = useMemo(() => {
    if (!revisionValidThrough) return null;
    const t = new Date(revisionValidThrough + 'T12:00:00');
    if (Number.isNaN(t.getTime())) return null;
    return t >= new Date(new Date().toDateString());
  }, [revisionValidThrough]);

  const showDocumentsTab = !!master && (canViewMasterQuotations || canEditRevision);

  const { data: attachmentTypes = [] } = useAttachmentTypesList();
  const defaultAttachmentTypeId = attachmentTypes[0]?.id ?? '';

  const uploadMutation = useUploadAttachment();
  const downloadMutation = useDownloadAttachment();

  const linkedAttachmentIds = useMemo(
    () => Array.from(new Set([...masterAttachRows, ...revAttachRows].map((r) => r.attachment_id))),
    [masterAttachRows, revAttachRows],
  );

  const metadataQueries = useQueries({
    queries: linkedAttachmentIds.map((id) => ({
      queryKey: ['attachment-metadata', id],
      queryFn: () => getAttachmentMetadata(id),
      enabled: Boolean(master && id && mainTab === 'documents'),
      staleTime: 60_000,
    })),
  });

  const attachmentMetaById = useMemo(() => {
    const map = new Map<string, Attachment>();
    linkedAttachmentIds.forEach((id, i) => {
      const data = metadataQueries[i]?.data;
      if (data) map.set(id, data);
    });
    return map;
  }, [linkedAttachmentIds, metadataQueries]);

  const handlePreviewAttachment = useCallback(async (attachmentId: string) => {
    try {
      const url = await getAttachmentPreviewUrl(attachmentId);
      if (url) window.open(url, '_blank');
    } catch {
      toast.error('Could not open preview.');
    }
  }, []);

  const handleDownloadAttachmentFile = useCallback(
    async (attachmentId: string, filename: string) => {
      try {
        const blob = await downloadMutation.mutateAsync(attachmentId);
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename || 'download';
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
      } catch {
        // mutation shows toast
      }
    },
    [downloadMutation],
  );

  const processUploadAndLinkMaster = useCallback(
    async (files: FileList | File[]) => {
      if (!master) return;
      const list = Array.from(files);
      if (list.length === 0) return;
      if (!defaultAttachmentTypeId) {
        toast.error('No attachment type is configured. Use Browse Files to choose a type.');
        return;
      }
      for (const file of list) {
        try {
          const att = await uploadMutation.mutateAsync({
            file,
            attachmentTypeId: defaultAttachmentTypeId,
            accessLevels: ['dealer', 'end_user'],
          });
          const res = await apiFetch(`${CM}/master-quotations/${master.id}/attachment-links`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attachment_id: att.id }),
          });
          if (!res.ok) {
            toast.error(`Could not link ${file.name}.`);
          } else {
            toast.success(`Linked ${file.name}`);
          }
        } catch {
          toast.error(`Upload failed for ${file.name}`);
        }
      }
      void refreshMasterAttachmentLinks(master.id);
    },
    [master, defaultAttachmentTypeId, uploadMutation, refreshMasterAttachmentLinks],
  );

  const processUploadAndLinkRevision = useCallback(
    async (files: FileList | File[]) => {
      if (!selectedRevisionId) {
        toast.error('Select a revision on the Revisions tab first.');
        return;
      }
      const list = Array.from(files);
      if (list.length === 0) return;
      if (!defaultAttachmentTypeId) {
        toast.error('No attachment type is configured. Use Browse Files to choose a type.');
        return;
      }
      const revId = selectedRevisionId;
      for (const file of list) {
        try {
          const att = await uploadMutation.mutateAsync({
            file,
            attachmentTypeId: defaultAttachmentTypeId,
            accessLevels: ['dealer', 'end_user'],
          });
          const res = await apiFetch(`${CM}/quotation-revisions/${revId}/attachment-links`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attachment_id: att.id }),
          });
          if (!res.ok) {
            toast.error(`Could not link ${file.name}.`);
          } else {
            toast.success(`Linked ${file.name}`);
          }
        } catch {
          toast.error(`Upload failed for ${file.name}`);
        }
      }
      void loadRevisionAttachments(revId);
    },
    [selectedRevisionId, defaultAttachmentTypeId, uploadMutation, loadRevisionAttachments],
  );

  const quotationsListingHref = '/commercial-management/quotations';

  if (status === 'loading') {
    return (
      <Container width="fluid">
        <p className="text-muted-foreground text-sm">Loading…</p>
      </Container>
    );
  }

  return (
    <Container width="fluid">
      {hasDeepLink && loading && !master ? (
        <div className="space-y-6 py-6">
          <Skeleton className="h-10 w-2/3 max-w-lg" />
          <Skeleton className="h-12 w-full max-w-3xl" />
          <Skeleton className="h-72 w-full rounded-2xl" />
        </div>
      ) : null}

      {hasDeepLink && !loading && !master && bootstrapError ? (
        <div className="border-destructive/30 bg-destructive/5 rounded-lg border p-6 text-sm">
          <p className="font-medium text-destructive">{bootstrapError}</p>
          <Button type="button" className="mt-4" variant="outline" onClick={() => void load()}>
            Retry
          </Button>
        </div>
      ) : null}

      {!hasDeepLink ? (
        <div className="mt-4 flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <Label>Tender code</Label>
            <Input value={tenderCode} onChange={(e) => setTenderCode(e.target.value)} className="w-48" />
          </div>
          <div className="grid gap-1">
            <Label>Quotation code</Label>
            <Input value={quotationCode} onChange={(e) => setQuotationCode(e.target.value)} className="w-48" />
          </div>
          <Button type="button" onClick={() => void load()} disabled={loading}>
            Load
          </Button>
        </div>
      ) : null}

      {master ? (
        <div className="relative mt-2 space-y-6">
          <div className="overflow-x-hidden rounded-lg border border-[#e5e7eb] bg-[#f9fafb] px-6 py-4">
            <div className="flex flex-col gap-4 xl:flex-row xl:flex-nowrap xl:items-start xl:justify-between xl:gap-6">
              <div className="flex min-w-0 flex-1 items-start gap-3">
                <Button
                  type="button"
                  variant="ghost"
                  size="icon"
                  className="mt-0.5 shrink-0"
                  onClick={() => router.push(quotationsListingHref)}
                  aria-label="Back to quotations list"
                >
                  <ArrowLeft className="size-5" />
                </Button>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-2xl font-medium tracking-tight text-[#0a0a0a]">
                      {master.sales_order_code && master.quotation_stage?.is_terminal && !master.quotation_stage?.is_cancelled
                        ? `Sales Order: ${master.sales_order_code}`
                        : `Quotation: ${quotationDisplayLabel}`}
                    </h1>
                    {master.quotation_stage ? (
                      <Badge
                        variant="secondary"
                        className="shrink-0 rounded-full border-0 bg-[#f3f4f6] px-3 py-1 font-normal text-[#364153]"
                      >
                        {master.quotation_stage.stage_name}
                      </Badge>
                    ) : null}
                  </div>
                  {master.sales_order_code && master.quotation_stage?.is_terminal && !master.quotation_stage?.is_cancelled && (
                    <p className="mt-0.5 text-sm text-[#6a7282]">
                      Quotation ref: {quotationDisplayLabel}
                    </p>
                  )}
                </div>
              </div>
              {canEditMaster || canAddMasterQuotation || showQuotationOutputMenu ? (
                <div className="flex w-full min-w-0 shrink-0 justify-stretch sm:justify-end xl:w-auto">
                  {canEditMaster ? (
                    <div className="flex min-w-0 w-full max-w-full gap-0 overflow-visible rounded-[14px] shadow-sm sm:inline-flex sm:w-max sm:flex-none">
                      <Button
                        type="button"
                        disabled={moveDisabled}
                        onClick={() => void advanceStage()}
                        title={primaryStageActionLabel}
                        className={cn(
                          // Button primitive defaults include whitespace-nowrap — override so long stage names wrap / show fully
                          '!inline-flex !h-auto !min-h-10 !whitespace-normal !break-words px-4 py-2.5 text-center text-base font-medium leading-snug text-white hover:bg-[#e7000b]/90 disabled:opacity-50',
                          'min-w-0 flex-1 border-0 bg-[#e7000b] sm:max-w-none sm:flex-none sm:px-5',
                          showStageMenu ? 'rounded-none rounded-s-[14px]' : 'rounded-[14px]',
                        )}
                      >
                        {primaryStageActionLabel}
                      </Button>
                      {showStageMenu ? (
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button
                              type="button"
                              aria-label="More actions"
                              className="!whitespace-nowrap h-auto min-h-10 shrink-0 self-stretch rounded-none rounded-e-[14px] border-0 border-l border-white/25 bg-[#e7000b] px-3 text-white hover:bg-[#e7000b]/90"
                            >
                              <ChevronDown className="size-4" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            {canAddMasterQuotation ? (
                              <DropdownMenuItem className="gap-2" onClick={() => void duplicateQuotation()}>
                                <Copy className="size-4" />
                                Duplicate quotation
                              </DropdownMenuItem>
                            ) : null}
                            {canEditMaster && previousStageLabel ? (
                              <DropdownMenuItem className="gap-2" onClick={() => void retreatStage()}>
                                <Undo2 className="size-4" />
                                Back to {previousStageLabel}
                              </DropdownMenuItem>
                            ) : null}
                            {canOpenEditQuotation ? (
                              <DropdownMenuItem asChild>
                                <Link href={editQuotationHref} className="flex cursor-pointer items-center gap-2">
                                  <Pencil className="size-4" />
                                  Edit quotation
                                </Link>
                              </DropdownMenuItem>
                            ) : null}
                            {canEditRevision ? (
                              <DropdownMenuItem className="gap-2" onClick={() => void createRevision()}>
                                <GitBranch className="size-4" />
                                Revise
                              </DropdownMenuItem>
                            ) : null}
                            {showOutputMenuSeparator ? <DropdownMenuSeparator /> : null}
                            {showQuotationOutputMenu ? (
                              <>
                                <DropdownMenuItem
                                  className="gap-2"
                                  disabled={quotationPdfLoading}
                                  onClick={() => void onPreviewQuotationPdf()}
                                >
                                  <Eye className="size-4" />
                                  {quotationPdfLoading ? 'Preparing preview…' : 'Preview PDF'}
                                </DropdownMenuItem>
                                <DropdownMenuItem
                                  className="gap-2"
                                  disabled={quotationPdfLoading}
                                  onClick={() => void onPrintQuotationPdf()}
                                >
                                  <Printer className="size-4" />
                                  {quotationPdfLoading ? 'Preparing PDF…' : 'Print PDF'}
                                </DropdownMenuItem>
                                {canEditMaster ? (
                                  <DropdownMenuItem className="gap-2" onClick={() => setQuotationEmailOpen(true)}>
                                    <Mail className="size-4" />
                                    Send email
                                  </DropdownMenuItem>
                                ) : null}
                              </>
                            ) : null}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      ) : null}
                    </div>
                  ) : canAddMasterQuotation ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          className="inline-flex h-auto min-h-10 items-center gap-2 rounded-[14px] border-0 bg-[#e7000b] px-5 py-2.5 text-base font-medium text-white hover:bg-[#e7000b]/90"
                        >
                          Actions
                          <ChevronDown className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem className="gap-2" onClick={() => void duplicateQuotation()}>
                          <Copy className="size-4" />
                          Duplicate quotation
                        </DropdownMenuItem>
                        {showQuotationOutputMenu ? (
                          <>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              className="gap-2"
                              disabled={quotationPdfLoading}
                              onClick={() => void onPreviewQuotationPdf()}
                            >
                              <Eye className="size-4" />
                              {quotationPdfLoading ? 'Preparing preview…' : 'Preview PDF'}
                            </DropdownMenuItem>
                            <DropdownMenuItem
                              className="gap-2"
                              disabled={quotationPdfLoading}
                              onClick={() => void onPrintQuotationPdf()}
                            >
                              <Printer className="size-4" />
                              {quotationPdfLoading ? 'Preparing PDF…' : 'Print PDF'}
                            </DropdownMenuItem>
                          </>
                        ) : null}
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : showQuotationOutputMenu ? (
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button
                          type="button"
                          className="inline-flex h-auto min-h-10 items-center gap-2 rounded-[14px] border-0 bg-[#e7000b] px-5 py-2.5 text-base font-medium text-white hover:bg-[#e7000b]/90"
                        >
                          Actions
                          <ChevronDown className="size-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          className="gap-2"
                          disabled={quotationPdfLoading}
                          onClick={() => void onPreviewQuotationPdf()}
                        >
                          <Eye className="size-4" />
                          {quotationPdfLoading ? 'Preparing preview…' : 'Preview PDF'}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="gap-2"
                          disabled={quotationPdfLoading}
                          onClick={() => void onPrintQuotationPdf()}
                        >
                          <Printer className="size-4" />
                          {quotationPdfLoading ? 'Preparing PDF…' : 'Print PDF'}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  ) : null}
                </div>
              ) : null}
            </div>
          </div>

          <Tabs value={mainTab} onValueChange={setMainTab} className="w-full">
            <TabsList className="mt-5 flex h-auto w-full flex-wrap justify-start gap-6 rounded-none border-0 border-b border-[#e5e7eb] bg-transparent px-6 pb-0 pt-0">
              <TabsTrigger
                value="overview"
                className="rounded-none border-0 border-b-2 border-transparent px-0 pb-2 text-base font-medium text-[#4a5565] data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none"
              >
                Overview
              </TabsTrigger>
              <TabsTrigger
                value="tasks"
                className="rounded-none border-0 border-b-2 border-transparent px-0 pb-2 text-base font-medium text-[#4a5565] data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none"
              >
                Tasks
              </TabsTrigger>
              <TabsTrigger
                value="revisions"
                className="rounded-none border-0 border-b-2 border-transparent px-0 pb-2 text-base font-medium text-[#4a5565] data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none"
              >
                Revisions
              </TabsTrigger>
              <TabsTrigger
                value="history"
                className="rounded-none border-0 border-b-2 border-transparent px-0 pb-2 text-base font-medium text-[#4a5565] data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none"
              >
                History
              </TabsTrigger>
              {showDocumentsTab ? (
                <TabsTrigger
                  value="documents"
                  className="rounded-none border-0 border-b-2 border-transparent px-0 pb-2 text-base font-medium text-[#4a5565] data-[state=active]:border-[#e7000b] data-[state=active]:bg-transparent data-[state=active]:text-[#e7000b] data-[state=active]:shadow-none"
                >
                  Documents
                </TabsTrigger>
              ) : null}
            </TabsList>
            <TabsContent value="overview" className="mt-6 space-y-6 px-6">
              <div className="rounded-2xl border border-[#e5e7eb] bg-white p-6 shadow-sm">
                <h2 className="mb-4 text-lg font-medium text-[#0a0a0a]">Quotation Information</h2>
                <div className="grid gap-6 md:grid-cols-3">
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Client</p>
                    {customerIdForQuotation ? (
                      <Link
                        href={`/order-management/customers/${encodeURIComponent(customerIdForQuotation)}`}
                        className="mt-2 inline-block font-medium text-[#e7000b] hover:underline"
                      >
                        {clientDisplay}
                      </Link>
                    ) : (
                      <p className="mt-2 font-medium text-[#101828]">{clientDisplay}</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Project</p>
                    {effectiveProjectId ? (
                      <TruncatedTextCell
                        text={projectDisplayTitle}
                        dialogTitle="Project title"
                        renderLabel={(label) => (
                          <Link
                            href={`/commercial-management/projects/${encodeURIComponent(effectiveProjectId)}`}
                            className="mt-2 block min-w-0 font-medium text-[#e7000b] hover:underline"
                          >
                            {label}
                          </Link>
                        )}
                      />
                    ) : (
                      <p className="mt-2 text-[#101828]">—</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Seller reference</p>
                    <p className="mt-2 text-[#101828]">{sellerReferenceDisplay}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Customer reference</p>
                    <p className="mt-2 text-[#101828]">{customerReferenceDisplay}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Attention to</p>
                    <p className="mt-2 text-[#101828]">{attentionToDisplay}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Client telephone</p>
                    <p className="mt-2 text-[#101828]">{clientPhoneDisplay}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Client email</p>
                    <p className="mt-2 text-[#101828]">{clientEmailDisplay}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Quotation template</p>
                    {master.quotation_package_template_id ? (
                      <Link
                        href={`/commercial-core/process-configuration?tab=quotations&qtpl=${encodeURIComponent(master.quotation_package_template_id)}`}
                        className="mt-2 inline-block font-medium text-[#e7000b] hover:underline"
                      >
                        {master.quotation_package_template_name?.trim() || master.quotation_package_template_id}
                      </Link>
                    ) : (
                      <p className="mt-2 text-[#101828]">—</p>
                    )}
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Order Date</p>
                    <p className="mt-2 text-[#101828]">
                      {meta.issued_on?.slice(0, 10) || '—'}
                    </p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Payment Term</p>
                    <p className="mt-2 text-[#101828]">{paymentTermLabel}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Validity Period (Days)</p>
                    <p className="mt-2 text-[#101828]">{meta.quotation_validity_days?.trim() || '—'}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Valid Until</p>
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span className="text-[#101828]">{validThrough || '—'}</span>
                      {validityOk === true ? (
                        <span className="rounded-full bg-[#dcfce7] px-2 py-0.5 text-xs font-normal text-[#008236]">Valid</span>
                      ) : null}
                      {validityOk === false ? (
                        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">Expired</span>
                      ) : null}
                    </div>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-[#4a5565]">Assigned Salesperson</p>
                    <p className="mt-2 text-[#101828]">
                      {meta.salesperson_user_id
                        ? (() => {
                            const u = users.find((x) => x.id === meta.salesperson_user_id);
                            return (u?.name || '').trim() || u?.email || meta.salesperson_user_id;
                          })()
                        : '—'}
                    </p>
                  </div>
                  <div className="md:col-span-3">
                    <p className="text-sm font-medium text-[#4a5565]">Delivery Address</p>
                    <p className="mt-2 text-[#101828]">{deliveryAddressLine || '—'}</p>
                  </div>
                </div>
              </div>

              <div className="overflow-hidden rounded-2xl border border-[#e5e7eb] bg-white shadow-sm">
                <div className="border-b border-[#e5e7eb] px-6 pt-4">
                  <Tabs value={overviewSubTab} onValueChange={(v) => setOverviewSubTab(v as 'orderLines' | 'internalNotes')}>
                    <TabsList className="h-auto w-full justify-start gap-8 rounded-none border-0 bg-transparent p-0">
                      <TabsTrigger
                        value="orderLines"
                        className="rounded-none border-b-2 border-transparent px-0 pb-3 text-base font-medium data-[state=active]:border-[#e7000b] data-[state=active]:text-[#e7000b]"
                      >
                        Order Lines
                      </TabsTrigger>
                      <TabsTrigger
                        value="internalNotes"
                        className="rounded-none border-b-2 border-transparent px-0 pb-3 text-base font-medium data-[state=active]:border-[#e7000b] data-[state=active]:text-[#e7000b]"
                      >
                        Internal Notes
                      </TabsTrigger>
                    </TabsList>
                  </Tabs>
                </div>

                {overviewSubTab === 'internalNotes' ? (
                  <div className="p-6">
                    <div className="prose prose-sm max-w-none min-h-[120px] rounded-xl border border-[#e5e7eb] p-4 text-[#0a0a0a] [&_p]:my-1">
                      {meta.notes?.trim() ? (
                        <div dangerouslySetInnerHTML={{ __html: meta.notes }} />
                      ) : (
                        <p className="text-muted-foreground text-sm">No internal notes.</p>
                      )}
                    </div>
                  </div>
                ) : (
                  <div className="space-y-6 p-6">
                    {selectedRevision ? (
                      <>
                        <QuotationOrderLinesReadOnly
                          lines={lines}
                          uoms={uoms}
                          taxRates={taxRates}
                          quotedCurrency={master?.quoted_currency}
                          pricingLineHints={selectedRevision.pricing_line_hints ?? null}
                          totals={totals}
                          showUnitCost={showOrderLineUnitCost}
                          onToggleUnitCost={() => setShowOrderLineUnitCost((s) => !s)}
                          emptyMessage="No order lines."
                        />

                        <div className="border-t border-[#e5e7eb] pt-6">
                          <h3 className="mb-2 text-sm font-medium text-[#0a0a0a]">Terms &amp; Conditions</h3>
                          {meta.terms_html?.trim() ? (
                            <div
                              className="prose prose-sm max-w-none text-[#0a0a0a] [&_li]:my-0 [&_ol]:my-2 [&_p]:my-1 [&_ul]:my-2"
                              dangerouslySetInnerHTML={{ __html: meta.terms_html }}
                            />
                          ) : (
                            <p className="text-muted-foreground text-sm">No terms specified.</p>
                          )}
                        </div>
                      </>
                    ) : (
                      <p className="text-muted-foreground text-sm">Select a revision on the Revisions tab.</p>
                    )}
                  </div>
                )}
              </div>
            </TabsContent>

            <TabsContent value="tasks" className="mt-6 px-6">
              <CommercialEntityTaskBoard
                storageKey={`commercial-mq-${master.id}`}
                taskBoard={taskBoard}
                onPersist={(next) => void persistMasterTaskBoard(next)}
                canEdit={canEditMaster}
                tasksGroupLabel="Quotation tasks"
                activitiesParent={{ variant: 'master_quotation', parentId: master.id }}
                scheduleBaselineStartDate={projectCtx?.start_date || null}
                onPreviewSchedule={(body) => previewMasterQuotationTaskBoardSchedule(master.id, body)}
                onApplySchedule={(body) => applyMasterQuotationTaskBoardSchedule(master.id, body)}
              />
            </TabsContent>

            <TabsContent value="revisions" className="mt-6 px-6">

              <div className="flex flex-col gap-6 lg:flex-row lg:items-stretch">
                <div className="w-full shrink-0 lg:max-w-[416px]">
                  <div className="rounded-2xl border border-[#e5e7eb] bg-white p-4 shadow-sm">
                    <h3 className="mb-4 text-sm font-medium text-[#0a0a0a]">Revision History</h3>
                    {sortedRevisions.length === 0 ? (
                      <p className="text-muted-foreground text-sm">No revisions loaded.</p>
                    ) : (
                      <div className="flex max-h-[min(520px,70vh)] flex-col gap-2 overflow-y-auto pe-1">
                        {sortedRevisions.map((r) => {
                          const isSel = selectedRevisionId === r.id;
                          const amt = formatMoneyAmount(snapshotSubtotal(r.pricing_snapshot), master?.quoted_currency);
                          const created = formatRevisionCalendarDate(r.created_at);
                          const label = revisionDisplayCode(master!.quotation_code, r);
                          return (
                            <button
                              key={r.id}
                              type="button"
                              onClick={() => setSelectedRevisionId(r.id)}
                              className={cn(
                                'w-full rounded-[14px] border p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#e7000b]',
                                r.is_current_working
                                  ? 'border-[#ffc9c9] bg-[#fef2f2]'
                                  : 'border-[#e5e7eb] bg-white hover:bg-muted/40',
                                isSel && 'ring-2 ring-[#e7000b] ring-offset-2',
                              )}
                            >
                              <div className="flex items-start justify-between gap-2">
                                <span className="font-medium text-[#e7000b]">{label}</span>
                                <div className="flex shrink-0 flex-wrap justify-end gap-1">
                                  {r.is_current_working ? (
                                    <span className="rounded-full bg-[#dcfce7] px-2 py-0.5 text-xs font-medium text-[#008236]">
                                      Current
                                    </span>
                                  ) : null}
                                  {r.is_final_selected ? (
                                    <span className="rounded-full bg-[#f3f4f6] px-2 py-0.5 text-xs font-normal text-[#364153]">
                                      Final
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                              <p className="mt-1 text-xs font-medium leading-4 text-[#4a5565]">{created || '—'}</p>
                              <p className="mt-0.5 text-xs font-medium leading-4 text-[#6a7282]">{amt}</p>
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>

                <div className="min-w-0 flex-1">
                  <div className="rounded-2xl border border-[#e5e7eb] bg-white p-6 shadow-sm">
                    {selectedRevision && master ? (
                      <>
                        <div className="mb-6 flex flex-col gap-1 border-b border-[#e5e7eb] pb-6">
                          <h2 className="text-lg font-medium tracking-tight text-[#0a0a0a]">
                            {revisionDisplayCode(master.quotation_code, selectedRevision)}
                          </h2>
                          <p className="text-sm text-[#4a5565]">
                            Created on {formatRevisionCalendarDate(selectedRevision.created_at) || '—'}
                          </p>
                          <div className="mt-4 flex flex-wrap gap-2">
                            {canEditMaster ? (
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                title="Use this snapshot as the current working revision (does not create a new version)"
                                disabled={selectedRevision.is_current_working}
                                onClick={() => void restoreVersionAsWorking(selectedRevision.id)}
                              >
                                Restore version
                              </Button>
                            ) : null}
                          </div>
                        </div>

                        <div className="grid gap-6 md:grid-cols-3">
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Client</p>
                            {customerIdForQuotation ? (
                              <Link
                                href={`/order-management/customers/${encodeURIComponent(customerIdForQuotation)}`}
                                className="mt-2 inline-block font-medium text-[#e7000b] hover:underline"
                              >
                                {clientDisplay}
                              </Link>
                            ) : (
                              <p className="mt-2 font-medium text-[#101828]">{clientDisplay}</p>
                            )}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Status</p>
                            <div className="mt-2">
                              {master.quotation_stage ? (
                                <span className="inline-flex rounded-full bg-[#f3f4f6] px-3 py-1 text-xs font-normal text-[#364153]">
                                  {master.quotation_stage.stage_name}
                                </span>
                              ) : (
                                <span className="text-[#101828]">—</span>
                              )}
                            </div>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Total Amount</p>
                            <p className="mt-2 text-[#101828]">
                              {formatMoneyAmount(totals.subtotal, master.quoted_currency)}
                            </p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Project</p>
                            {effectiveProjectId ? (
                              <TruncatedTextCell
                                text={projectDisplayTitle}
                                dialogTitle="Project title"
                                renderLabel={(label) => (
                                  <Link
                                    href={`/commercial-management/projects/${encodeURIComponent(effectiveProjectId)}`}
                                    className="mt-2 block min-w-0 font-medium text-[#e7000b] hover:underline"
                                  >
                                    {label}
                                  </Link>
                                )}
                              />
                            ) : (
                              <p className="mt-2 text-[#101828]">—</p>
                            )}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Seller reference</p>
                            <p className="mt-2 text-[#101828]">{sellerReferenceDisplay}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Customer reference</p>
                            <p className="mt-2 text-[#101828]">{customerReferenceDisplay}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Attention to</p>
                            <p className="mt-2 text-[#101828]">{attentionToDisplay}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Client telephone</p>
                            <p className="mt-2 text-[#101828]">{clientPhoneDisplay}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Client email</p>
                            <p className="mt-2 text-[#101828]">{clientEmailDisplay}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Order Date</p>
                            <p className="mt-2 text-[#101828]">{meta.issued_on?.slice(0, 10) || '—'}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Payment Term</p>
                            <p className="mt-2 text-[#101828]">{paymentTermLabel}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Validity Period (Days)</p>
                            <p className="mt-2 text-[#101828]">{meta.quotation_validity_days?.trim() || '—'}</p>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Valid Until</p>
                            <div className="mt-2 flex flex-wrap items-center gap-2">
                              <span className="text-[#101828]">{revisionValidThrough || '—'}</span>
                              {validityOkForRevision === true ? (
                                <span className="rounded-full bg-[#dcfce7] px-2 py-0.5 text-xs font-normal text-[#008236]">
                                  Valid
                                </span>
                              ) : null}
                              {validityOkForRevision === false ? (
                                <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-900">
                                  Expired
                                </span>
                              ) : null}
                            </div>
                          </div>
                          <div>
                            <p className="text-sm font-medium text-[#4a5565]">Assigned Salesperson</p>
                            <p className="mt-2 text-[#101828]">
                              {meta.salesperson_user_id
                                ? (() => {
                                    const u = users.find((x) => x.id === meta.salesperson_user_id);
                                    return (u?.name || '').trim() || u?.email || meta.salesperson_user_id;
                                  })()
                                : '—'}
                            </p>
                          </div>
                          <div className="md:col-span-3">
                            <p className="text-sm font-medium text-[#4a5565]">Delivery Address</p>
                            <p className="mt-2 text-[#101828]">{deliveryAddressLine || '—'}</p>
                          </div>
                        </div>

                        <div className="mt-8 border-t border-[#e5e7eb] pt-6">
                          <h3 className="mb-4 text-sm font-medium text-[#0a0a0a]">Order Lines</h3>
                          <QuotationOrderLinesReadOnly
                            lines={lines}
                            uoms={uoms}
                            taxRates={taxRates}
                            quotedCurrency={master.quoted_currency}
                            pricingLineHints={selectedRevision.pricing_line_hints ?? null}
                            totals={totals}
                            showUnitCost={showOrderLineUnitCost}
                            onToggleUnitCost={() => setShowOrderLineUnitCost((s) => !s)}
                            emptyMessage="No order lines in this revision."
                          />
                        </div>

                        <div className="mt-8 border-t border-[#e5e7eb] pt-6">
                          <h3 className="mb-3 text-sm font-medium text-[#0a0a0a]">Internal Notes</h3>
                          <div className="prose prose-sm max-w-none min-h-[80px] rounded-xl border border-[#e5e7eb] bg-[#f9fafb] p-4 text-[#0a0a0a] [&_p]:my-1">
                            {meta.notes?.trim() ? (
                              <div dangerouslySetInnerHTML={{ __html: meta.notes }} />
                            ) : (
                              <p className="text-muted-foreground text-sm">No internal notes in this revision.</p>
                            )}
                          </div>
                        </div>
                      </>
                    ) : (
                      <p className="text-muted-foreground text-sm">Select a revision from the list to preview.</p>
                    )}
                  </div>
                </div>
              </div>
            </TabsContent>

            {showDocumentsTab ? (
              <TabsContent value="documents" className="mt-6 space-y-6 px-6">
                <div className="flex flex-col gap-8">
                  <div className="space-y-6">
                    <div
                      role={canEditRevision && selectedRevisionId ? 'button' : undefined}
                      tabIndex={canEditRevision && selectedRevisionId ? 0 : undefined}
                      onClick={() => {
                        if (canEditRevision && selectedRevisionId) setUploadRevOpen(true);
                      }}
                      onKeyDown={(e) => {
                        if (!canEditRevision || !selectedRevisionId) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          setUploadRevOpen(true);
                        }
                      }}
                      onDragOver={(e) => {
                        e.preventDefault();
                        if (canEditRevision && selectedRevisionId) setDocRevDrag(true);
                      }}
                      onDragLeave={() => setDocRevDrag(false)}
                      onDrop={(e) => {
                        e.preventDefault();
                        setDocRevDrag(false);
                        if (!canEditRevision || !selectedRevisionId) return;
                        void processUploadAndLinkRevision(e.dataTransfer.files);
                      }}
                      className={cn(
                        'flex min-h-[200px] flex-col items-center justify-center rounded-2xl border-2 border-dashed bg-white px-6 py-10 transition-colors md:min-h-[276px]',
                        canEditRevision && selectedRevisionId
                          ? 'cursor-pointer border-[#d1d5dc] hover:border-[#e7000b]/40'
                          : 'cursor-not-allowed border-[#e5e7eb] opacity-70',
                        docRevDrag && canEditRevision && selectedRevisionId && 'border-[#e7000b] bg-[#fef2f2]/60',
                      )}
                    >
                      <Upload className="mb-4 size-12 shrink-0 text-[#6a7282]" aria-hidden />
                      <h3 className="mb-2 text-center text-lg font-medium text-[#0a0a0a]">Upload Documents</h3>
                      <p className="mb-2 text-center text-sm text-[#4a5565]">
                        Drag and drop files here, or click to browse
                      </p>
                      <p className="mb-6 text-center text-xs text-[#6a7282]">
                        Applies to revision {selectedRevision?.revision_number ?? '—'} (select on the Revisions tab)
                      </p>
                      {canEditRevision && selectedRevisionId ? (
                        <Button
                          type="button"
                          className="rounded-[14px] bg-[#e7000b] px-6 hover:bg-[#e7000b]/90"
                          onClick={(e) => {
                            e.stopPropagation();
                            setUploadRevOpen(true);
                          }}
                        >
                          Browse Files
                        </Button>
                      ) : (
                        <p className="text-muted-foreground max-w-md text-center text-xs">
                          {!selectedRevisionId
                            ? 'Select a revision on the Revisions tab to upload documents here.'
                            : 'You do not have permission to upload revision documents.'}
                        </p>
                      )}
                    </div>

                    {selectedRevisionId && revAttachRows.length > 0 ? (
                      <div className="flex items-center justify-center gap-4 py-1">
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="size-10 shrink-0 rounded-full border-[#d1d5dc] bg-white shadow-sm"
                          aria-label="Previous document"
                          disabled={documentsNavIndex <= 1}
                          onClick={() => setDocumentsNavIndex((i) => Math.max(1, i - 1))}
                        >
                          <ChevronLeft className="size-5 text-[#101828]" />
                        </Button>
                        <p className="min-w-[4.5rem] text-center text-sm font-semibold tabular-nums tracking-tight text-[#101828]">
                          {Math.min(documentsNavIndex, revAttachRows.length)} / {revAttachRows.length}
                        </p>
                        <Button
                          type="button"
                          variant="outline"
                          size="icon"
                          className="size-10 shrink-0 rounded-full border-[#d1d5dc] bg-white shadow-sm"
                          aria-label="Next document"
                          disabled={documentsNavIndex >= revAttachRows.length}
                          onClick={() =>
                            setDocumentsNavIndex((i) => Math.min(revAttachRows.length, i + 1))
                          }
                        >
                          <ChevronRight className="size-5 text-[#101828]" />
                        </Button>
                      </div>
                    ) : null}

                    <div className="overflow-hidden rounded-2xl border border-[#e5e7eb] bg-white">
                      <div className="border-b border-[#e5e7eb] px-4 py-4">
                        <p className="text-sm font-medium text-[#0a0a0a]">
                          Uploaded documents ({revAttachRows.length})
                        </p>
                        <p className="mt-1 text-xs text-[#6a7282]">
                          Working revision {selectedRevision ? `(${revisionDisplayCode(master!.quotation_code, selectedRevision)})` : ''}
                        </p>
                      </div>
                      {!selectedRevisionId ? (
                        <p className="text-muted-foreground px-4 py-10 text-center text-sm">
                          Select a revision on the Revisions tab to see its documents.
                        </p>
                      ) : revAttachRows.length === 0 ? (
                        <p className="text-muted-foreground px-4 py-10 text-center text-sm">No files linked for this revision.</p>
                      ) : (
                        <div className="max-h-[min(420px,50vh)] overflow-y-auto">
                          {revAttachRows.map((r, rowIdx) => {
                            const meta = attachmentMetaById.get(r.attachment_id);
                            const downloadName = meta?.original_filename || r.file_name || 'download';
                            const isActive = rowIdx === documentsNavIndex - 1;
                            return (
                              <div
                                key={r.id}
                                ref={(el) => {
                                  const id = r.attachment_id;
                                  if (el) docRowRefs.current.set(id, el);
                                  else docRowRefs.current.delete(id);
                                }}
                                className={cn(
                                  isActive && 'bg-[#fef2f2]/90 ring-1 ring-inset ring-[#fecaca]',
                                )}
                              >
                                <QuotationDocumentRow
                                  attachmentId={r.attachment_id}
                                  fileName={r.file_name}
                                  meta={meta}
                                  canEdit={!!canEditRevision}
                                  downloadPending={downloadMutation.isPending}
                                  onUnlink={() => void unlinkRevisionAttachment(r.id)}
                                  onPreview={() => void handlePreviewAttachment(r.attachment_id)}
                                  onDownload={() =>
                                    void handleDownloadAttachmentFile(r.attachment_id, downloadName)
                                  }
                                />
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              </TabsContent>
            ) : null}

            <TabsContent value="history" className="mt-6 px-6">
              <div className="overflow-hidden rounded-2xl border border-[#e5e7eb] bg-white">
                <div className="flex h-[53px] items-center justify-between border-b border-[#e5e7eb] px-4 py-4">
                  <h3 className="text-sm font-medium text-[#0a0a0a]">Audit Trail</h3>
                  <p className="text-xs text-[#6a7282]">
                    Total {auditFlatRows.length} record{auditFlatRows.length === 1 ? '' : 's'}
                  </p>
                </div>

                {auditLoading ? (
                  <div className="px-4 py-8">
                    <p className="text-muted-foreground text-sm">Loading history…</p>
                  </div>
                ) : auditFlatRows.length === 0 ? (
                  <div className="border-t border-transparent px-4 py-10 text-center">
                    <p className="text-muted-foreground text-sm">No audit entries yet for this quotation.</p>
                  </div>
                ) : (
                  <>
                    <div className="max-h-[min(445px,55vh)] overflow-auto">
                      <Table>
                        <TableHeader>
                          <TableRow className="border-b border-[#e5e7eb] bg-[#f9fafb] hover:bg-[#f9fafb]">
                            <TableHead className="h-10 min-w-[120px] text-xs font-medium text-[#4a5565]">User</TableHead>
                            <TableHead className="h-10 min-w-[88px] text-xs font-medium text-[#4a5565]">Action</TableHead>
                            <TableHead className="h-10 min-w-[100px] text-xs font-medium text-[#4a5565]">Field</TableHead>
                            <TableHead className="h-10 min-w-[160px] text-xs font-medium text-[#4a5565]">
                              Old Value
                            </TableHead>
                            <TableHead className="h-10 min-w-[160px] text-xs font-medium text-[#4a5565]">
                              New Value
                            </TableHead>
                            <TableHead className="h-10 min-w-[140px] text-xs font-medium text-[#4a5565]">Date</TableHead>
                          </TableRow>
                        </TableHeader>
                        <TableBody>
                          {paginatedAuditRows.map((r) => (
                            <TableRow
                              key={r.id}
                              className="border-b border-[#e5e7eb] font-normal [&>td]:py-3 [&>td]:align-top"
                            >
                              <TableCell className="text-sm text-[#101828]">{r.user}</TableCell>
                              <TableCell className="text-sm font-normal uppercase text-[#4a5565]">{r.action}</TableCell>
                              <TableCell className="max-w-[200px] break-words text-sm text-[#4a5565]">{r.field}</TableCell>
                              <TableCell className="text-sm">
                                <AuditValueCell value={r.oldVal} tone="old" />
                              </TableCell>
                              <TableCell className="text-sm">
                                <AuditValueCell value={r.newVal} tone="new" />
                              </TableCell>
                              <TableCell className="whitespace-nowrap text-sm text-[#4a5565]">
                                {formatAuditDateTime(r.changed_at)}
                              </TableCell>
                            </TableRow>
                          ))}
                        </TableBody>
                      </Table>
                    </div>

                    <div className="flex h-[67px] flex-wrap items-center justify-between gap-3 border-t border-[#e5e7eb] px-4 py-4">
                      <p className="text-sm text-[#4a5565]">
                        Page {historyPage} of {historyPageCount}
                      </p>
                      <div className="flex gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-9 rounded-[10px] border-[#d1d5dc] px-4"
                          disabled={historyPage <= 1}
                          onClick={() => setHistoryPage((p) => Math.max(1, p - 1))}
                        >
                          Previous
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className="h-9 rounded-[10px] border-[#d1d5dc] px-4"
                          disabled={historyPage >= historyPageCount}
                          onClick={() => setHistoryPage((p) => Math.min(historyPageCount, p + 1))}
                        >
                          Next
                        </Button>
                      </div>
                    </div>
                  </>
                )}
              </div>
            </TabsContent>

          </Tabs>

          <EntityActivitiesDock variant="master_quotation" entityId={master.id} canPost={canEditMaster} />
        </div>
      ) : !hasDeepLink ? (
        <p className="text-muted-foreground mt-6 text-sm">Enter a tender and quotation above, or open a quotation from the pipeline or project.</p>
      ) : null}

      <AttachmentUploadDialog
        open={uploadMasterOpen}
        onOpenChange={setUploadMasterOpen}
        onSuccess={async (attId) => {
          if (!attId || !master) return;
          const res = await apiFetch(`${CM}/master-quotations/${master.id}/attachment-links`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attachment_id: attId }),
          });
          if (res.ok) {
            toast.success('File linked to this master quotation.');
            void refreshMasterAttachmentLinks(master.id);
          } else {
            toast.error('File uploaded but could not be linked. Use the attachment id in the field above.');
          }
        }}
      />
      <AttachmentUploadDialog
        open={uploadRevOpen}
        onOpenChange={setUploadRevOpen}
        onSuccess={async (attId) => {
          if (!attId || !selectedRevisionId) {
            toast.error('Select a revision on the Revisions tab, then try again.');
            return;
          }
          const res = await apiFetch(`${CM}/quotation-revisions/${selectedRevisionId}/attachment-links`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ attachment_id: attId }),
          });
          if (res.ok) {
            toast.success('File linked to this revision.');
            void loadRevisionAttachments(selectedRevisionId);
          } else {
            toast.error('File uploaded but could not be linked.');
          }
        }}
      />
      <QuotationEmailSendDialog
        open={quotationEmailOpen}
        onOpenChange={setQuotationEmailOpen}
        revisionId={selectedRevisionId}
      />
    </Container>
  );
}
