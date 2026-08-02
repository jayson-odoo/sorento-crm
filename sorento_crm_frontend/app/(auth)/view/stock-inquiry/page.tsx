'use client';

import { Suspense, useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, ExternalLink, Eye } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { format } from 'date-fns';
import {
  ProductInquiryFormLayout,
  InquiryFormTableRow,
  InquiryReadValue,
} from '@/app/(protected)/procurement-management/stock-inquiries/components/ProductInquiryFormLayout';
import AttachmentPreviewModal, {
  type AttachmentPreviewItem,
} from '@/components/common/AttachmentPreviewModal';

interface StockInquiryViewAttachment {
  id?: string;
  file_name?: string | null;
  original_filename?: string | null;
  file_url?: string | null;
  uploaded_at?: string | null;
  /** 'user' = uploaded by CRM staff, 'contact' = uploaded by the submitting
   *  contact, 'system' = worker-created. Absent/null on legacy rows. */
  uploader_kind?: 'user' | 'contact' | 'system' | null;
  uploaded_by_name?: string | null;
  uploaded_by_role?: 'staff' | 'contact' | 'unknown';
  /** false for staff ('user') uploads - this view has no unlink control at
   *  all today, but the flag is honoured in case one is ever added here. */
  can_unlink?: boolean;
  mime_type?: string | null;
}

interface StockInquiryViewSummary {
  entity_type: string;
  entity_id: string;
  inquiry_number?: string | null;
  salesperson?: string | null;
  product_code?: string | null;
  item_description?: string | null;
  project_customer?: string | null;
  project_name?: string | null;
  quantity?: string | null;
  delivery_date?: string | null;
  remark?: string | null;
  additional_remark?: string | null;
  purchasing_response?: string | null;
  status?: string | null;
  last_responded_at?: string | null;
  last_responded_by?: string | null;
  last_responded_by_name?: string | null;
  rejection_reason?: string | null;
  rejected_at?: string | null;
  rejected_by?: string | null;
  rejected_by_name?: string | null;
  reopen_reason?: string | null;
  reopened_at?: string | null;
  reopened_by?: string | null;
  reopened_by_name?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  portal_url?: string | null;
  attachments?: StockInquiryViewAttachment[] | null;
}

function formatDateTimeStr(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return value;
  }
}

function ViewStockInquiryContent() {
  const searchParams = useSearchParams();
  const token = searchParams?.get('token') ?? '';
  const [summary, setSummary] = useState<StockInquiryViewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revisePending, setRevisePending] = useState(false);
  const [reviseSuccess, setReviseSuccess] = useState<string | null>(null);
  const [reviseError, setReviseError] = useState<string | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [staffPreviewOpen, setStaffPreviewOpen] = useState(false);

  const attachments = useMemo(() => summary?.attachments ?? [], [summary?.attachments]);
  const previewItems = useMemo<AttachmentPreviewItem[]>(
    () =>
      attachments.map((att, idx) => ({
        id: att.id ?? String(idx),
        name: att.original_filename ?? att.file_name ?? 'Attachment',
        url: att.file_url ?? '',
      })),
    [attachments],
  );

  // Purchasing's own response attachments - surfaced in the reply banner,
  // scoped away from the contact's own uploads shown in the list below.
  const staffAttachments = attachments.filter((a) => a.uploader_kind === 'user');
  const staffPreviewItems: AttachmentPreviewItem[] = staffAttachments.map((att, idx) => ({
    id: att.id ?? `staff-${idx}`,
    name: att.original_filename ?? att.file_name ?? 'Attachment',
    url: att.file_url ?? '',
  }));

  const fetchSummary = useCallback(async () => {
    if (!token) {
      setError('Invalid or missing view link.');
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/v1/public/view/stock-inquiry?token=${encodeURIComponent(token)}`);
      const data = await res.json();
      if (res.ok) {
        setSummary(data);
        setError(null);
      } else {
        const msg =
          (typeof data.detail === 'object' && data.detail && 'message' in data.detail
            ? (data.detail as { message?: string }).message
            : null) ||
          (typeof data.detail === 'string' ? data.detail : null) ||
          data.message ||
          'This link is invalid.';
        setError(msg);
      }
    } catch {
      setError('Failed to load details.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const handleRevise = useCallback(async () => {
    if (!token) return;
    setRevisePending(true);
    setReviseSuccess(null);
    setReviseError(null);
    try {
      const res = await fetch('/api/v1/public/view/stock-inquiry/revise', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const msg =
          (typeof data.detail === 'object' && data.detail && 'message' in data.detail
            ? (data.detail as { message?: string }).message
            : null) ||
          (typeof data.detail === 'string' ? data.detail : null) ||
          data.message ||
          'Failed to send revise request.';
        setReviseError(msg);
        return;
      }
      setReviseSuccess(data.message || 'Revise request sent successfully.');
    } catch {
      setReviseError('Failed to send revise request.');
    } finally {
      setRevisePending(false);
    }
  }, [token]);

  if (loading) {
    return (
      <div className="min-h-screen max-w-4xl mx-auto px-4 py-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="min-h-screen max-w-4xl mx-auto px-4 py-6 space-y-6">
        <h1 className="text-xl sm:text-2xl font-semibold">View Stock Inquiry</h1>
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      </div>
    );
  }

  const viewInSystemPath = summary?.entity_id
    ? `/procurement-management/stock-inquiries/${summary.entity_id}`
    : null;

  return (
    <div className="min-h-screen max-w-4xl mx-auto px-4 py-6 space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-2 min-w-0">
          {summary?.inquiry_number ? (
            <div className="space-y-1">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Stock inquiry number
              </p>
              <p className="text-2xl sm:text-3xl font-bold tabular-nums tracking-tight break-all">
                {summary.inquiry_number}
              </p>
            </div>
          ) : null}
          <h1 className="text-xl sm:text-2xl font-semibold leading-tight">Stock Inquiry</h1>
        </div>
        <div className="flex flex-wrap gap-2 self-start">
          {summary?.portal_url && (
            <Button variant="outline" size="sm" className="shrink-0 self-start" asChild>
              <Link href={summary.portal_url}>All my submissions</Link>
            </Button>
          )}
          {summary?.status === 'rejected' && (
            <Button onClick={handleRevise} disabled={revisePending}>
              {revisePending ? 'Sending...' : 'Revise'}
            </Button>
          )}
          {viewInSystemPath && (
            <Button variant="outline" size="sm" className="shrink-0 self-start" asChild>
              <Link href={viewInSystemPath}>
                <ExternalLink className="h-4 w-4 mr-2" />
                View in system
              </Link>
            </Button>
          )}
        </div>
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}
      {reviseError && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{reviseError}</AlertTitle>
        </Alert>
      )}
      {reviseSuccess && (
        <Alert>
          <AlertTitle>{reviseSuccess}</AlertTitle>
        </Alert>
      )}
      <ProductInquiryFormLayout>
        <InquiryFormTableRow label="Date">
          <InquiryReadValue empty="—">
            {summary?.created_at
              ? format(new Date(summary.created_at), 'dd/MM/yy')
              : ''}
          </InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Sales person">
          <InquiryReadValue>{summary?.salesperson}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Product code">
          <InquiryReadValue>{summary?.product_code}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Item description" labelClassName="items-start pt-3">
          <InquiryReadValue>{summary?.item_description}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Project customer">
          <InquiryReadValue>{summary?.project_customer}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Project name">
          <InquiryReadValue>{summary?.project_name}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Qty">
          <InquiryReadValue>
            {summary?.quantity != null && summary.quantity !== ''
              ? String(summary.quantity)
              : ''}
          </InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Delivery date">
          <InquiryReadValue>{summary?.delivery_date}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Remark" labelClassName="items-start pt-3">
          <InquiryReadValue>{summary?.remark}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow label="Additional remark" labelClassName="items-start pt-3">
          <InquiryReadValue>{summary?.additional_remark}</InquiryReadValue>
        </InquiryFormTableRow>
        <InquiryFormTableRow
          label="Comment / reply by purchasing"
          labelClassName="items-start pt-3 sm:whitespace-normal"
        >
          <InquiryReadValue>{summary?.purchasing_response}</InquiryReadValue>
          {(summary?.purchasing_response ?? '').trim() && staffAttachments.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <span className="text-xs text-muted-foreground">
                {staffAttachments.length} attachment{staffAttachments.length === 1 ? '' : 's'} from
                purchasing
              </span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setStaffPreviewOpen(true)}
              >
                View attachment{staffAttachments.length === 1 ? '' : 's'} ({staffAttachments.length})
              </Button>
            </div>
          )}
        </InquiryFormTableRow>
        {(summary?.last_responded_at || summary?.last_responded_by) && (
          <>
            <InquiryFormTableRow label="Last responded by">
              <InquiryReadValue empty="—">
                {summary?.last_responded_by_name ?? summary?.last_responded_by}
              </InquiryReadValue>
            </InquiryFormTableRow>
            <InquiryFormTableRow label="Last responded at">
              <InquiryReadValue empty="—">
                {summary?.last_responded_at
                  ? formatDateTimeStr(summary.last_responded_at)
                  : ''}
              </InquiryReadValue>
            </InquiryFormTableRow>
          </>
        )}
        {(summary?.rejected_by ||
          summary?.rejected_at ||
          (summary?.rejection_reason != null && summary.rejection_reason !== '')) && (
          <>
            <InquiryFormTableRow label="Rejected by">
              <InquiryReadValue empty="—">
                {summary?.rejected_by_name ?? summary?.rejected_by}
              </InquiryReadValue>
            </InquiryFormTableRow>
            <InquiryFormTableRow label="Rejected at">
              <InquiryReadValue empty="—">
                {summary?.rejected_at ? formatDateTimeStr(summary.rejected_at) : ''}
              </InquiryReadValue>
            </InquiryFormTableRow>
            <InquiryFormTableRow label="Rejection reason" labelClassName="items-start pt-3">
              <InquiryReadValue>{summary?.rejection_reason}</InquiryReadValue>
            </InquiryFormTableRow>
          </>
        )}
        {((summary?.reopen_reason != null && summary.reopen_reason !== '') ||
          summary?.reopened_at ||
          summary?.reopened_by) && (
          <>
            <InquiryFormTableRow label="Reopen reason" labelClassName="items-start pt-3">
              <InquiryReadValue>{summary?.reopen_reason}</InquiryReadValue>
            </InquiryFormTableRow>
            <InquiryFormTableRow label="Reopened by">
              <InquiryReadValue empty="—">
                {summary?.reopened_by_name ?? summary?.reopened_by}
              </InquiryReadValue>
            </InquiryFormTableRow>
            <InquiryFormTableRow label="Reopened at">
              <InquiryReadValue empty="—">
                {summary?.reopened_at ? formatDateTimeStr(summary.reopened_at) : ''}
              </InquiryReadValue>
            </InquiryFormTableRow>
          </>
        )}
      </ProductInquiryFormLayout>

      {attachments.length > 0 && (
        <div className="rounded-md border border-border bg-background px-4 py-3">
          <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">Attachments</p>
          <div className="space-y-2">
            {attachments.map((att, idx) => {
              const uploader = (att.uploaded_by_name ?? '').trim();
              return (
                <button
                  key={att.id ?? att.file_name ?? idx}
                  type="button"
                  onClick={() => {
                    setPreviewIndex(idx);
                    setPreviewOpen(true);
                  }}
                  className="flex w-full items-start gap-2 text-left"
                >
                  <Eye className="h-4 w-4 shrink-0 mt-0.5 text-primary" />
                  <span>
                    <span className="block text-sm font-medium text-primary hover:underline break-all">
                      {att.original_filename ?? att.file_name ?? 'Attachment'}
                    </span>
                    {uploader && (
                      <span className="block text-xs text-muted-foreground">By {uploader}</span>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {summary && (
        <div className="rounded-md border border-border bg-muted/30 px-4 py-3 text-sm space-y-1">
          <div className="flex flex-wrap gap-x-4 gap-y-1">
            <span className="text-muted-foreground">Status</span>
            <span className="font-medium">{summary.status ?? '—'}</span>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {summary.last_responded_at && (
              <span>Last responded: {formatDateTimeStr(summary.last_responded_at)}</span>
            )}
            {summary.updated_at && (
              <span>Updated: {formatDateTimeStr(summary.updated_at)}</span>
            )}
          </div>
        </div>
      )}

      <AttachmentPreviewModal
        open={previewOpen}
        onOpenChange={setPreviewOpen}
        items={previewItems}
        startIndex={previewIndex}
      />
      <AttachmentPreviewModal
        open={staffPreviewOpen}
        onOpenChange={setStaffPreviewOpen}
        items={staffPreviewItems}
      />
    </div>
  );
}

export default function ViewStockInquiryPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <ViewStockInquiryContent />
    </Suspense>
  );
}
