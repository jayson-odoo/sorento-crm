'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, CheckCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { LoaderCircleIcon } from 'lucide-react';

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
  if (value == null || value === '') return '—';
  return APPROVAL_STATUS_LABELS[value.toLowerCase()] ?? value;
}

function formatDateStr(value: string | null | undefined): string {
  if (!value) return '—';
  try {
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, { dateStyle: 'medium' });
  } catch {
    return value;
  }
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
            approval_comments: comments || undefined,
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

  return (
    <div className="min-h-screen max-w-lg mx-auto px-4 py-6 sm:py-8 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold leading-tight">{typeLabel} – Approval</h1>
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
      <Card className="overflow-hidden">
        <CardHeader className="pb-2">
          <CardTitle className="text-base sm:text-lg">
            {summary?.request_number ? `Form #${summary.request_number}` : 'Details'}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 sm:px-6 -mt-2 space-y-0">
          <DetailRow label="Type" value={typeLabel} />
          <DetailRow label="Form number" value={summary?.request_number ?? undefined} />
          <DetailRow label="Status" value={approvalStatusLabel(summary?.approval_status)} />
          <DetailRow label="Customer" value={summary?.customer_name ?? undefined} />
          <DetailRow label="Project" value={summary?.project_title ?? undefined} />
          {summary?.request_type === 'purchase_request' && (
            <DetailRow label="Purpose" value={summary?.purpose ?? undefined} />
          )}
          {summary?.request_type === 'sponsorship_form' && (
            <>
              <DetailRow label="Delivery address" value={summary?.delivery_address ?? undefined} />
              <DetailRow
                label="Total project value"
                value={
                  summary?.total_project_value_text?.trim()
                    ? summary.total_project_value_text
                    : summary?.total_project_value != null
                      ? String(summary.total_project_value)
                      : undefined
                }
              />
              <DetailRow label="Sponsor subject" value={summary?.sponsor_subject ?? undefined} />
            </>
          )}
          <DetailRow label="Requested by" value={summary?.requested_by ?? undefined} />
          <DetailRow label="Request date" value={summary?.request_date ? formatDateStr(summary.request_date) : undefined} />
          <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined} />
          <DetailRow label="Expected delivery" value={summary?.expected_delivery_date ? formatDateStr(summary.expected_delivery_date) : undefined} />
          {summary?.request_type === 'purchase_request' && (
            <DetailRow label="Expected PO date" value={poDisplay ?? undefined} />
          )}
          <div className="py-2.5 border-b border-border/60 last:border-0">
            <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Link expires</p>
            <p className="text-sm font-medium">
              {summary?.expires_at ? new Date(summary.expires_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : '—'}
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
                    <p className="text-sm font-medium break-words">{line.item_code ?? '—'}</p>
                    <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Quantity</p>
                    <p className="text-sm font-medium">{line.quantity != null ? String(line.quantity) : '—'}</p>
                    {summary?.request_type === 'sponsorship_form' && (
                      <>
                        {(line.unit_price != null || line.total != null) && (
                          <>
                            <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Unit price</p>
                            <p className="text-sm font-medium">{line.unit_price != null ? String(line.unit_price) : '—'}</p>
                            <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Total</p>
                            <p className="text-sm font-medium">{line.total != null ? String(line.total) : '—'}</p>
                          </>
                        )}
                      </>
                    )}
                    {summary?.request_type === 'purchase_request' && (line.remark != null && String(line.remark).trim() !== '') && (
                      <>
                        <p className="text-xs text-muted-foreground uppercase tracking-wide mt-1.5">Remarks</p>
                        <p className="text-sm font-medium break-words">{line.remark}</p>
                      </>
                    )}
                  </div>
                ))}
              </div>
              {summary?.request_type === 'sponsorship_form' && summary?.grand_total != null && (
                <div className="mt-3 pt-3 border-t border-border">
                  <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Grand total</p>
                  <p className="text-sm font-semibold">{String(summary.grand_total)}</p>
                </div>
              )}
            </div>
          )}
        </CardContent>
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
            <Label htmlFor="comments" className="text-sm">Comments (optional)</Label>
            <Textarea
              id="comments"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Add any comments"
              className="mt-1.5 resize-none"
              rows={3}
            />
          </div>
          <div className="flex flex-col gap-2 pt-2 sm:flex-row sm:gap-3">
            <Button
              onClick={() => handleSubmit('approved')}
              disabled={submitting}
              className="flex-1 sm:flex-none"
            >
              {submitting && <LoaderCircleIcon className="animate-spin h-4 w-4 mr-2" />}
              Approve
            </Button>
            <Button
              variant="destructive"
              onClick={() => handleSubmit('rejected')}
              disabled={submitting}
              className="flex-1 sm:flex-none"
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
