'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { AlertCircle, CheckCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Input } from '@/components/ui/input';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Skeleton } from '@/components/ui/skeleton';
import { LoaderCircleIcon } from 'lucide-react';

interface ApprovalSummary {
  entity_type: string;
  entity_id: string;
  request_number: string | null;
  request_type: string;
  customer_name: string | null;
  project_title: string | null;
  purpose: string | null;
  requested_by: string | null;
  expires_at: string;
}

const REQUEST_TYPE_LABELS: Record<string, string> = {
  purchase_request: 'Purchase Request',
  sponsorship_form: 'Sponsorship Form',
};

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
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  if (error && !summary) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Approval Link</h1>
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
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold">Approval Complete</h1>
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

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold">{typeLabel} – Approval</h1>
      {error && (
        <Alert variant="destructive">
          <AlertIcon>
            <AlertCircle />
          </AlertIcon>
          <AlertTitle>{error}</AlertTitle>
        </Alert>
      )}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">
            {summary?.request_number ? `#${summary.request_number}` : 'Details'}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {summary?.customer_name && (
            <p><span className="font-medium">Customer:</span> {summary.customer_name}</p>
          )}
          {summary?.project_title && (
            <p><span className="font-medium">Project:</span> {summary.project_title}</p>
          )}
          {summary?.purpose && (
            <p><span className="font-medium">Purpose:</span> {summary.purpose}</p>
          )}
          {summary?.requested_by && (
            <p><span className="font-medium">Requested by:</span> {summary.requested_by}</p>
          )}
          <p className="text-sm text-muted-foreground">
            Link expires: {summary?.expires_at ? new Date(summary.expires_at).toLocaleString() : '—'}
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Your response</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <Label htmlFor="approved_by">Your name (optional)</Label>
            <Input
              id="approved_by"
              value={approvedBy}
              onChange={(e) => setApprovedBy(e.target.value)}
              placeholder="Name"
              className="mt-1"
            />
          </div>
          <div>
            <Label htmlFor="comments">Comments (optional)</Label>
            <Textarea
              id="comments"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Add any comments"
              className="mt-1"
              rows={3}
            />
          </div>
          <div className="flex gap-3 pt-2">
            <Button
              onClick={() => handleSubmit('approved')}
              disabled={submitting}
            >
              {submitting && <LoaderCircleIcon className="animate-spin h-4 w-4 mr-2" />}
              Approve
            </Button>
            <Button
              variant="destructive"
              onClick={() => handleSubmit('rejected')}
              disabled={submitting}
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
