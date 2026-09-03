'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { formatDateTimeInMalaysia, formatCurrency } from '@/lib/helpers';
import { AlertCircle, CheckCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { LoaderCircleIcon } from 'lucide-react';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from '@/lib/toast';

interface ApprovalLineSummary {
  item_code?: string | null;
  quantity?: number | null;
  remark?: string | null;
  unit_price?: number | null;
  total?: number | null;
  sort_order?: number | null;
}

interface ApprovalSummary {
  entity_type: string;
  entity_id: string;
  request_number: string | null;
  request_type: string;
  customer_name: string | null;
  pic: string | null;
  project_title: string | null;
  purpose: string | null;
  delivery_address?: string | null;
  total_project_value?: number | null;
  total_project_value_text?: string | null;
  sponsor_subject?: string | null;
  requested_by: string | null;
  request_date: string | null;
  created_at: string | null;
  expected_delivery_date: string | null;
  expected_po_date: string | null;
  expected_po_date_text: string | null;
  expires_at: string;
  lines?: ApprovalLineSummary[] | null;
  grand_total?: number | null;
  approval_status?: string | null;
  approver_display_name?: string | null;
  approver_email?: string | null;
}

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

const APPROVAL_STATUS_LABELS: Record<string, string> = {
  draft: 'Draft',
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
};

function approvalStatusLabel(value: string | null | undefined): string {
  if (value == null || value === '') return '-';
  return APPROVAL_STATUS_LABELS[value.toLowerCase()] ?? value;
}

function formatDateStr(value: string | null | undefined): string {
  if (!value) return '-';
  try {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { dateStyle: 'medium' });
  } catch {
    return value;
  }
}

/** Single detail row for mobile-friendly stacking */
function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === '' || (typeof value === 'string' && value.trim() === '')) return null;
  return (
    <div className="py-2.5 border-b border-border/60 last:border-0">
      <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">{label}</p>
      <p className="text-sm font-medium break-words">{value}</p>
    </div>
  );
}

function ApprovalContent() {
  const searchParams = useSearchParams();
  const token = searchParams?.get('token') ?? '';
  const [summary, setSummary] = useState<ApprovalSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState<boolean | null>(null);
  const [approvedBy, setApprovedBy] = useState('');
  const [comments, setComments] = useState('');
  const [commentsError, setCommentsError] = useState<string | null>(null);
  const commentsRef = useRef<HTMLTextAreaElement | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!token) {
      setError('Invalid or missing approval link.');
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/v1/public/approval/summary?token=${encodeURIComponent(token)}`);
      const data = await res.json();
      if (res.ok) {
        setSummary(data);
        setError(null);
        const prefill = data.approver_display_name ?? data.approver_email ?? '';
        if (prefill) setApprovedBy(prefill);
      } else {
        setError(data.detail || data.message || 'This link is invalid or has expired.');
      }
    } catch {
      setError('Failed to load approval details.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    fetchSummary();
  }, [fetchSummary]);

  const handleSubmit = async (action: 'approved' | 'rejected') => {
    if (!token) return;
    const trimmedComments = comments.trim();
    if (action === 'rejected' && !trimmedComments) {
      const msg = 'Please enter a reason for rejection before clicking Reject.';
      setCommentsError(msg);
      toast.error(msg);
      commentsRef.current?.focus();
      commentsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }
    setCommentsError(null);
    setSubmitting(true);
    try {
      const res = await fetch(
        `/api/v1/public/approval/submit?token=${encodeURIComponent(token)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            approved_by: approvedBy || undefined,
            approval_comments:
              action === 'rejected' ? trimmedComments : trimmedComments || undefined,
          }),
        },
      );
      const data = await res.json();
      if (res.ok) {
        setDone(true);
      } else {
        setError(data.detail || data.message || 'Submission failed.');
      }
    } catch {
      setError('Submission failed.');
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
        <h1 className="text-xl sm:text-2xl font-semibold">Approval Link</h1>
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
        <p className="text-sm text-muted-foreground">
          This link may have expired or already been used. Please request a new approval link if needed.
        </p>
      </div>
    );
  }

  if (done) {
    return (
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
        <h1 className="text-xl sm:text-2xl font-semibold">Approval Complete</h1>
        <Alert className="border-green-200 bg-green-50 text-green-900">
          <AlertIcon>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </AlertIcon>
          <AlertTitle>Your response has been recorded successfully.</AlertTitle>
        </Alert>
        <p className="text-sm text-muted-foreground">
          You can close this window.
        </p>
      </div>
    );
  }

  const typeLabel = REQUEST_TYPE_LABELS[summary?.request_type ?? ''] ?? summary?.request_type ?? 'Request';

  const poDisplay = summary?.expected_po_date_text?.trim() || (summary?.expected_po_date ? formatDateStr(summary.expected_po_date) : null);

  const viewInSystemPath =
    summary?.entity_id && summary?.request_type
      ? summary.request_type === 'sponsorship_form'
        ? `/procurement-management/sponsorship-forms/${summary.entity_id}`
        : `/procurement-management/purchase-requests/${summary.entity_id}`
      : null;

  const isPr = summary?.request_type === 'purchase_request';
  const isSf = summary?.request_type === 'sponsorship_form';

  return (
    <div
      className={`min-h-screen w-full mx-auto px-4 py-6 sm:py-8 space-y-6 ${isPr || isSf ? 'max-w-full sm:max-w-5xl xl:max-w-6xl' : 'max-w-lg'}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold leading-tight">{typeLabel} - Approval</h1>
        {viewInSystemPath && (
          <Button variant="outline" size="sm" className="shrink-0" asChild>
            <Link href={viewInSystemPath}>
              <ExternalLink className="h-4 w-4 mr-2" />
              View in system
            </Link>
          </Button>
        )}
      </div>
      {error && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}
      <Card className={`overflow-hidden ${isPr || isSf ? 'border-2 shadow-sm' : ''}`}>
        {isSf ? (
          <CardContent className="px-5 sm:px-8 py-6 space-y-0">
            <div className="flex flex-wrap gap-2 mb-4">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {typeLabel}
              </span>
              <span className="text-xs text-muted-foreground">·</span>
              <span className="text-xs font-medium">{approvalStatusLabel(summary?.approval_status)}</span>
            </div>
            <h2 className="text-center text-lg sm:text-xl font-semibold border-b border-border pb-4 mb-6">
              Project Sales Sponsorship Form
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4 [&>div]:min-w-0 [&_p]:break-words">
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Sponsorship form number</p>
                <p className="text-sm font-medium">{summary?.request_number ?? '-'}</p>
              </div>
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Date</p>
                <p className="text-sm font-medium">
                  {summary?.request_date ? formatDateStr(summary.request_date) : '-'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Customer Name</p>
                <p className="text-sm font-medium break-words">{summary?.customer_name ?? '-'}</p>
              </div>
              <div>
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">PIC</p>
                <p className="text-sm font-medium break-words">{summary?.pic ?? '-'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Delivery Address</p>
                <p className="text-sm font-medium whitespace-pre-wrap break-words">
                  {summary?.delivery_address ?? '-'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Project Title</p>
                <p className="text-sm font-medium break-words">{summary?.project_title ?? '-'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Total Project Value</p>
                <p className="text-sm font-medium">
                  {summary?.total_project_value_text?.trim()
                    ? summary.total_project_value_text
                    : summary?.total_project_value != null
                      ? String(summary.total_project_value)
                      : '-'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Sponsor Subject</p>
                <p className="text-sm font-medium break-words">{summary?.sponsor_subject ?? '-'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Date of Delivery</p>
                <p className="text-sm font-medium">
                  {summary?.expected_delivery_date
                    ? formatDateStr(summary.expected_delivery_date)
                    : '-'}
                </p>
              </div>
            </div>
            <DetailRow label="Requested by" value={summary?.requested_by ?? undefined} />
            <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeInMalaysia(summary.created_at) : undefined} />
            <div className="py-2.5 border-b border-border/60">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Link expires</p>
              <p className="text-sm font-medium">
                {summary?.expires_at ? new Date(summary.expires_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '-'}
              </p>
            </div>
            {summary?.lines && summary.lines.length > 0 && (
              <div className="pt-6 mt-2 border-t border-border">
                <p className="text-sm font-medium mb-3">Line items</p>
                <div className="overflow-x-auto -mx-1 px-1">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-10">NO.</TableHead>
                        <TableHead>Item Code</TableHead>
                        <TableHead className="w-20">Qty</TableHead>
                        <TableHead className="w-24 text-right">U/P</TableHead>
                        <TableHead className="w-24 text-right">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {summary.lines.map((line, idx) => (
                        <TableRow key={idx}>
                          <TableCell>{idx + 1}</TableCell>
                          <TableCell className="font-medium">{line.item_code ?? '-'}</TableCell>
                          <TableCell>{line.quantity != null ? String(line.quantity) : '-'}</TableCell>
                          <TableCell className="text-right">{line.unit_price != null ? formatCurrency(line.unit_price) : '-'}</TableCell>
                          <TableCell className="text-right">{line.total != null ? formatCurrency(line.total) : '-'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {summary.grand_total != null && (
                  <div className="mt-4 flex justify-end">
                    <p className="text-sm font-semibold">Grand Total: {formatCurrency(summary.grand_total)}</p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        ) : (
          <>
            <CardHeader className="pb-2">
              <CardTitle className="text-base sm:text-lg">
                {isPr && summary?.request_number
                  ? `Purchase request number ${summary.request_number}`
                  : isSf && summary?.request_number
                    ? `Sponsorship form number ${summary.request_number}`
                    : summary?.request_number
                      ? `Form #${summary.request_number}`
                      : 'Details'}
              </CardTitle>
            </CardHeader>
            <CardContent className="px-4 sm:px-6 -mt-2 space-y-0">
              <DetailRow label="Type" value={typeLabel} />
              <DetailRow
                label={isPr ? 'Purchase request number' : isSf ? 'Sponsorship form number' : 'Form number'}
                value={summary?.request_number ?? undefined}
              />
              <DetailRow label="Status" value={approvalStatusLabel(summary?.approval_status)} />
              <DetailRow label="Customer" value={summary?.customer_name ?? undefined} />
              <DetailRow label="PIC" value={summary?.pic ?? undefined} />
              <DetailRow label="Project" value={summary?.project_title ?? undefined} />
              {isPr && <DetailRow label="Purpose" value={summary?.purpose ?? undefined} />}
              <DetailRow label="Requested by" value={summary?.requested_by ?? undefined} />
              <DetailRow
                label={isPr ? 'Date' : 'Request date'}
                value={summary?.request_date ? formatDateStr(summary.request_date) : undefined}
              />
              <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeInMalaysia(summary.created_at) : undefined} />
              <DetailRow
                label={isPr ? 'Expected date of delivery' : 'Expected delivery'}
                value={summary?.expected_delivery_date ? formatDateStr(summary.expected_delivery_date) : undefined}
              />
              {isPr && <DetailRow label="Expected date to receive PO" value={poDisplay ?? undefined} />}
              <div className="py-2.5 border-b border-border/60 last:border-0">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Link expires</p>
                <p className="text-sm font-medium">
                  {summary?.expires_at ? new Date(summary.expires_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '-'}
                </p>
              </div>
              {summary?.lines && summary.lines.length > 0 && (
                <div className="pt-4 mt-2 border-t border-border">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">Line items</p>
                  <div className="space-y-3">
                    {summary.lines.map((line, idx) => (
                      <div
                        key={idx}
                        className="rounded-md border border-border/60 bg-muted/30 p-3 space-y-1.5"
                      >
                        <p className="text-xs text-muted-foreground uppercase tracking-wide">Product</p>
                        <p className="text-sm font-medium break-words">{line.item_code ?? '-'}</p>
                        <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Quantity</p>
                        <p className="text-sm font-medium">{line.quantity != null ? String(line.quantity) : '-'}</p>
                        {isPr && (line.remark != null && String(line.remark).trim() !== '') && (
                          <>
                            <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Remarks</p>
                            <p className="text-sm font-medium break-words">{line.remark}</p>
                          </>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </>
        )}
      </Card>

      <Card className="overflow-hidden">
        <CardHeader className="pb-2">
          <CardTitle className="text-base sm:text-lg">Your response</CardTitle>
        </CardHeader>
        <CardContent className="px-4 sm:px-6 -mt-2 space-y-4">
          <div>
            <Label htmlFor="approved_by" className="text-sm">Your name (optional)</Label>
            <Input
              id="approved_by"
              value={approvedBy}
              onChange={(e) => setApprovedBy(e.target.value)}
              placeholder="Name"
              className="mt-1.5"
            />
          </div>
          <div>
            <Label htmlFor="comments" className="text-sm">
              Comments <span className="text-destructive" aria-hidden>*</span>
              <span className="ml-1 text-xs font-normal text-muted-foreground">(required when rejecting)</span>
            </Label>
            <p id="comments-hint" className="text-xs text-muted-foreground mt-1">
              Optional when approving. Required when rejecting.
            </p>
            <Textarea
              ref={commentsRef}
              id="comments"
              value={comments}
              onChange={(e) => {
                setComments(e.target.value);
                if (commentsError && e.target.value.trim()) setCommentsError(null);
              }}
              placeholder="Add notes, or your reason if rejecting"
              className={`mt-1.5 resize-none ${commentsError ? 'border-destructive ring-1 ring-destructive' : ''}`}
              rows={3}
              aria-describedby="comments-hint comments-error"
              aria-invalid={commentsError ? true : undefined}
            />
            {commentsError && (
              <p id="comments-error" className="mt-1 text-xs text-destructive">
                {commentsError}
              </p>
            )}
          </div>
          <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:gap-3">
            <Button
              onClick={() => handleSubmit('approved')}
              disabled={submitting}
              className="flex-1 sm:flex-none min-h-11 sm:min-h-10 text-base sm:text-sm font-semibold"
            >
              {submitting && <LoaderCircleIcon className="animate-spin h-4 w-4 mr-2" />}
              Approve
            </Button>
            <Button
              variant="destructive"
              onClick={() => handleSubmit('rejected')}
              disabled={submitting}
              className="flex-1 sm:flex-none min-h-11 sm:min-h-10 text-base sm:text-sm font-semibold"
            >
              Reject
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

export default function ApprovalPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <ApprovalContent />
    </Suspense>
  );
}
