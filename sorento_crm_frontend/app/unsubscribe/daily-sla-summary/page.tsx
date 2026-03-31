'use client';

import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { apiFetch } from '@/lib/api';

export default function UnsubscribeDailySLASummaryPage() {
  const searchParams = useSearchParams();
  const token = useMemo(() => searchParams.get('token') || '', [searchParams]);
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading');
  const [message, setMessage] = useState('Processing your unsubscribe request...');

  useEffect(() => {
    const run = async () => {
      if (!token) {
        setStatus('error');
        setMessage('Missing unsubscribe token.');
        return;
      }
      try {
        const res = await apiFetch(
          `/api/v1/notifications/preferences/daily-sla-summary/unsubscribe?token=${encodeURIComponent(token)}`,
        );
        const data = (await res.json().catch(() => ({}))) as { message?: string; detail?: string };
        if (!res.ok) {
          throw new Error(data.detail || 'Unable to unsubscribe.');
        }
        setStatus('success');
        setMessage(data.message || 'You have been unsubscribed from daily SLA summary emails.');
      } catch (err) {
        setStatus('error');
        setMessage(err instanceof Error ? err.message : 'Unable to unsubscribe.');
      }
    };
    void run();
  }, [token]);

  return (
    <div className="min-h-screen flex items-center justify-center p-4 bg-muted/20">
      <Card className="w-full max-w-lg">
        <CardHeader>
          <CardTitle>Daily SLA Summary Subscription</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">{message}</p>
          <div className="flex items-center gap-2">
            {status !== 'loading' && (
              <Button asChild variant="outline">
                <Link href="/user-management/account">Manage preferences in system</Link>
              </Button>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
