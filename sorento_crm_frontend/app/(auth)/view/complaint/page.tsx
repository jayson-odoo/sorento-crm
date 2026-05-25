'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, ExternalLink } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';

interface ViewAttachment {
  id?: string;
  file_name?: string | null;
  original_filename?: string | null;
  file_url?: string | null;
  uploaded_at?: string | null;
}

interface ComplaintViewSummary {
  entity_type: string;
  entity_id: string;
  delivery_order_number?: string | null;
  complaint_date?: string | null;
  customer_type?: string | null;
  customer_type_others?: string | null;
  within_warranty?: string | null;
  product_type?: string | null;
  defects_discovered?: string | null;
  complaint_type?: string | null;
  defect_description?: string | null;
  product_code?: string | null;
  quantity?: string | null;
  salesperson?: string | null;
  customer_name?: string | null;
  contact_person?: string | null;
  contact_number?: string | null;
  customer_address?: string | null;
  project_title?: string | null;
  technical_team_response?: string | null;
  status?: string | null;
  last_responded_at?: string | null;
  created_at?: string | null;
  attachments?: ViewAttachment[] | null;
  portal_url?: string | null;
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
      <p className="text-sm font-medium break-words whitespace-pre-wrap">{value}</p>
    </div>
  );
}

function ViewComplaintContent() {
  const searchParams = useSearchParams();
  const token = searchParams?.get('token') ?? '';
  const [summary, setSummary] = useState<ComplaintViewSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(async () => {
    if (!token) {
      setError('Invalid or missing view link.');
      setLoading(false);
      return;
    }
    try {
      const res = await fetch(`/api/v1/public/view/complaint?token=${encodeURIComponent(token)}`);
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
        <h1 className="text-xl sm:text-2xl font-semibold">View Complaint</h1>
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
    ? `/complaint-management/complaints/${summary.entity_id}`
    : null;

  return (
    <div className="min-h-screen max-w-lg mx-auto px-4 py-6 space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold leading-tight">Complaint</h1>
        <div className="flex flex-wrap gap-2 self-start">
          {summary?.portal_url && (
            <Button variant="outline" size="sm" className="shrink-0" asChild>
              <Link href={summary.portal_url}>All my submissions</Link>
            </Button>
          )}
          {viewInSystemPath && (
            <Button variant="outline" size="sm" className="shrink-0" asChild>
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
      <Card className="overflow-hidden">
        <CardHeader className="pb-2">
          <CardTitle className="text-base sm:text-lg">
            {summary?.delivery_order_number ? `DO #${summary.delivery_order_number}` : 'Complaint details'}
          </CardTitle>
        </CardHeader>
        <CardContent className="px-4 sm:px-6 -mt-2 space-y-0">
          <DetailRow label="Delivery order number" value={summary?.delivery_order_number ?? undefined} />
          <DetailRow label="Complaint date" value={summary?.complaint_date ? formatDateStr(summary.complaint_date) : undefined} />
          <DetailRow label="Customer type" value={summary?.customer_type ?? undefined} />
          <DetailRow label="Customer type (other)" value={summary?.customer_type_others ?? undefined} />
          <DetailRow label="Within warranty" value={summary?.within_warranty ?? undefined} />
          <DetailRow label="Product type" value={summary?.product_type ?? undefined} />
          <DetailRow label="Defects discovered" value={summary?.defects_discovered ?? undefined} />
          <DetailRow label="Complaint type" value={summary?.complaint_type ?? undefined} />
          <DetailRow label="Defect description" value={summary?.defect_description ?? undefined} />
          <DetailRow label="Product code" value={summary?.product_code ?? undefined} />
          <DetailRow label="Quantity" value={summary?.quantity ?? undefined} />
          <DetailRow label="Salesperson" value={summary?.salesperson ?? undefined} />
          <DetailRow label="Customer name" value={summary?.customer_name ?? undefined} />
          <DetailRow label="Contact person" value={summary?.contact_person ?? undefined} />
          <DetailRow label="Contact number" value={summary?.contact_number ?? undefined} />
          <DetailRow label="Customer address" value={summary?.customer_address ?? undefined} />
          <DetailRow label="Project title" value={summary?.project_title ?? undefined} />
          <DetailRow label="Technical team response" value={summary?.technical_team_response ?? undefined} />
          <DetailRow label="Status" value={summary?.status ?? undefined} />
          <DetailRow label="Last responded at" value={summary?.last_responded_at ? formatDateTimeStr(summary.last_responded_at) : undefined} />
          <DetailRow label="Created at" value={summary?.created_at ? formatDateTimeStr(summary.created_at) : undefined} />
          {summary?.attachments && summary.attachments.length > 0 && (
            <div className="pt-4 mt-2 border-t border-border">
              <p className="text-xs text-muted-foreground uppercase tracking-wide mb-3">Attachments</p>
              <div className="space-y-2">
                {summary.attachments.map((att) => (
                  <a
                    key={att.id ?? att.file_name}
                    href={att.file_url ?? '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="block text-sm font-medium text-primary hover:underline break-all"
                  >
                    {att.original_filename ?? att.file_name ?? 'Attachment'}
                  </a>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function ViewComplaintPage() {
  return (
    <Suspense fallback={<Skeleton className="h-32 w-full" />}>
      <ViewComplaintContent />
    </Suspense>
  );
}
