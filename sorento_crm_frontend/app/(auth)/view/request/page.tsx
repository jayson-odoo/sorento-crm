'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { PurchaseRequestSignoffFooter } from '@/app/(protected)/procurement-management/purchase-requests/components/PurchaseRequestSignoffFooter';

interface ViewLineSummary {
  item_code?: string | null;
  quantity?: number | null;
  remark?: string | null;
  unit_price?: number | null;
  total?: number | null;
  sort_order?: number | null;
}

interface ViewSummary {
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
  expires_at?: string | null;
  lines?: ViewLineSummary[] | null;
  grand_total?: number | null;
  approval_status?: string | null;
  requested_at?: string | null;
  approved_at?: string | null;
  approved_by?: string | null;
  approval_comments?: string | null;
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

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === '' || (typeof value === 'string' && value.trim() === '')) return null;
  return (
    <div className="py-2.5 border-b border-border/60 last:border-0">
      <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">{label}</p>
      <p className="text-sm font-medium break-words">{value}</p>
    </div>
  );
}

function ViewRequestContent() {
  const searchParams = useSearchParams();
  const token = searchParams?.get('token') ?? '';
  const [summary, setSummary] = useState<ViewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revisePending, setRevisePending] = useState(false);
  const [reviseSuccess, setReviseSuccess] = useState<string | null>(null);
  const [reviseError, setReviseError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!token) {
      setError('Invalid or missing view link.');
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/v1/public/view/request?token=${encodeURIComponent(token)}`);
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
      const res = await fetch('/api/v1/public/view/request/revise', {
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
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-48 w-full" />
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
        <h1 className="text-xl sm:text-2xl font-semibold">View Request</h1>
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
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
  const isDocLayout = isPr || isSf;

  return (
    <div
      className={`min-h-screen w-full mx-auto px-4 py-6 space-y-6 ${isDocLayout ? 'max-w-full sm:max-w-5xl xl:max-w-6xl' : 'max-w-lg'}`}
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold leading-tight">{typeLabel}</h1>
        <div className="flex flex-wrap gap-2 self-start">
          {summary?.approval_status === 'rejected' && (
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
      <Card className={`overflow-hidden ${isDocLayout ? 'border-2 shadow-sm' : ''}`}>
        {isPr ? (
          <CardContent className="px-5 sm:px-8 py-6 space-y-0">
            <div className="flex flex-wrap gap-2 mb-4">
              <span className="text-xs font-medium text-muted-foreground uppercase tracking-wide">
                {typeLabel}
              </span>
              <span className="text-xs text-muted-foreground">·</span>
              <span className="text-xs font-medium">{approvalStatusLabel(summary?.approval_status)}</span>
            </div>
            <h2 className="text-center text-lg sm:text-xl font-semibold border-b border-border pb-4 mb-6">
              Purchase Request
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Sales Order no.</p>
                <p className="text-sm font-medium">{summary?.request_number ?? '—'}</p>
              </div>
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Date</p>
                <p className="text-sm font-medium">
                  {summary?.request_date ? formatDateStr(summary.request_date) : '—'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Customer Name</p>
                <p className="text-sm font-medium break-words">{summary?.customer_name ?? '—'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Project Title</p>
                <p className="text-sm font-medium break-words">{summary?.project_title ?? '—'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Purpose</p>
                <p className="text-sm font-medium break-words">{summary?.purpose ?? '—'}</p>
              </div>
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">
                  Expected date of delivery
                </p>
                <p className="text-sm font-medium">
                  {summary?.expected_delivery_date
                    ? formatDateStr(summary.expected_delivery_date)
                    : '—'}
                </p>
              </div>
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">
                  Expected date to receive PO
                </p>
                <p className="text-sm font-medium">{poDisplay ?? '—'}</p>
              </div>
            </div>
            {summary?.lines && summary.lines.length > 0 && (
              <div className="pt-6 mt-2 border-t border-border">
                <p className="text-sm font-medium mb-3">Line items</p>
                <div className="overflow-x-auto -mx-1 px-1">
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="w-10">#</TableHead>
                        <TableHead>Item Code</TableHead>
                        <TableHead className="w-24">Qty</TableHead>
                        <TableHead>Remark</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {summary.lines.map((line, idx) => (
                        <TableRow key={idx}>
                          <TableCell>{idx + 1}</TableCell>
                          <TableCell className="font-medium">{line.item_code ?? '—'}</TableCell>
                          <TableCell>{line.quantity != null ? String(line.quantity) : '—'}</TableCell>
                          <TableCell className="text-muted-foreground">{line.remark ?? '—'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              </div>
            )}
            {summary && (
              <PurchaseRequestSignoffFooter request={summary} variant="publicCard" />
            )}
            <DetailRow
              label="Created at"
              value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined}
            />
          </CardContent>
        ) : isSf ? (
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
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-4">
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Sales Order no.</p>
                <p className="text-sm font-medium">{summary?.request_number ?? '—'}</p>
              </div>
              <div className="py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Date</p>
                <p className="text-sm font-medium">
                  {summary?.request_date ? formatDateStr(summary.request_date) : '—'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Customer Name</p>
                <p className="text-sm font-medium break-words">{summary?.customer_name ?? '—'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Delivery Address</p>
                <p className="text-sm font-medium whitespace-pre-wrap break-words">
                  {summary?.delivery_address ?? '—'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Project Title</p>
                <p className="text-sm font-medium break-words">{summary?.project_title ?? '—'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Total Project Value</p>
                <p className="text-sm font-medium">
                  {summary?.total_project_value_text?.trim()
                    ? summary.total_project_value_text
                    : summary?.total_project_value != null
                      ? String(summary.total_project_value)
                      : '—'}
                </p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Sponsor Subject</p>
                <p className="text-sm font-medium break-words">{summary?.sponsor_subject ?? '—'}</p>
              </div>
              <div className="sm:col-span-2 py-2 border-b border-border/60">
                <p className="text-xs text-muted-foreground uppercase tracking-wide mb-0.5">Date of Delivery</p>
                <p className="text-sm font-medium">
                  {summary?.expected_delivery_date
                    ? formatDateStr(summary.expected_delivery_date)
                    : '—'}
                </p>
              </div>
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
                        <TableHead className="w-24">U/P</TableHead>
                        <TableHead className="w-24">Total</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {summary.lines.map((line, idx) => (
                        <TableRow key={idx}>
                          <TableCell>{idx + 1}</TableCell>
                          <TableCell className="font-medium">{line.item_code ?? '—'}</TableCell>
                          <TableCell>{line.quantity != null ? String(line.quantity) : '—'}</TableCell>
                          <TableCell>{line.unit_price != null ? String(line.unit_price) : '—'}</TableCell>
                          <TableCell>{line.total != null ? String(line.total) : '—'}</TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
                {summary.grand_total != null && (
                  <div className="mt-4 flex justify-end">
                    <p className="text-sm font-semibold">Grand Total: {String(summary.grand_total)}</p>
                  </div>
                )}
              </div>
            )}
            {summary && (
              <PurchaseRequestSignoffFooter request={summary} variant="publicCard" />
            )}
            <DetailRow
              label="Created at"
              value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined}
            />
          </CardContent>
        ) : (
          <>
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
              <DetailRow label="Requested by" value={summary?.requested_by ?? undefined} />
              <DetailRow label="Request date" value={summary?.request_date ? formatDateStr(summary.request_date) : undefined} />
              <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined} />
            </CardContent>
          </>
        )}
      </Card>
    </div>
  );
}

export default function ViewRequestPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <ViewRequestContent />
    </Suspense>
  );
}
