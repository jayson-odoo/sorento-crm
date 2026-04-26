'use client';

import { useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

type ApiErrorBody = { message?: string; detail?: string };

function parseErrorMessage(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object') {
    const o = payload as ApiErrorBody;
    if (typeof o.message === 'string') return o.message;
    if (typeof o.detail === 'string') return o.detail;
  }
  return fallback;
}

export default function SalesOrderProgressionClient() {
  const [tenderCode, setTenderCode] = useState('');
  const [quotationCode, setQuotationCode] = useState('');
  const [revisionNumber, setRevisionNumber] = useState('1');
  const [winResult, setWinResult] = useState<string | null>(null);
  const [winError, setWinError] = useState<string | null>(null);
  const [winLoading, setWinLoading] = useState(false);

  const [closeOutcome, setCloseOutcome] = useState('lost');
  const [closeNotes, setCloseNotes] = useState('');
  const [closeResult, setCloseResult] = useState<string | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);
  const [closeLoading, setCloseLoading] = useState(false);

  async function submitWin() {
    setWinError(null);
    setWinResult(null);
    setWinLoading(true);
    try {
      const rev = parseInt(revisionNumber, 10);
      if (!tenderCode.trim() || !quotationCode.trim() || Number.isNaN(rev) || rev < 1) {
        setWinError('Enter tender code, quotation code, and a valid revision number.');
        return;
      }
      const res = await apiFetch(
        `/api/commercial/tenders/${encodeURIComponent(tenderCode.trim())}/winning-path/progress`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            quotation_code: quotationCode.trim(),
            revision_number: rev,
          }),
        },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setWinError(parseErrorMessage(body, 'Request failed'));
        return;
      }
      setWinResult(
        `Tender ${body.tender_code}: ${body.tender_outcome}. Sales order ${body.sales_order_number} (${body.quotation_code} rev ${body.revision_number}).`,
      );
    } finally {
      setWinLoading(false);
    }
  }

  async function submitClose() {
    setCloseError(null);
    setCloseResult(null);
    setCloseLoading(true);
    try {
      if (!tenderCode.trim()) {
        setCloseError('Enter tender code.');
        return;
      }
      const res = await apiFetch(
        `/api/commercial/tenders/${encodeURIComponent(tenderCode.trim())}/close-outcome`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            tender_outcome: closeOutcome,
            outcome_notes: closeNotes.trim() || null,
          }),
        },
      );
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setCloseError(parseErrorMessage(body, 'Request failed'));
        return;
      }
      setCloseResult(`Tender ${body.tender_code} closed (${body.tender_outcome}).`);
    } finally {
      setCloseLoading(false);
    }
  }

  return (
    <div className="grid gap-6 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>Winning path → sales order</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="tender-code">Tender code</Label>
            <Input
              id="tender-code"
              value={tenderCode}
              onChange={(e) => setTenderCode(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="quotation-code">Quotation code</Label>
            <Input
              id="quotation-code"
              value={quotationCode}
              onChange={(e) => setQuotationCode(e.target.value)}
              autoComplete="off"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="revision">Revision number</Label>
            <Input
              id="revision"
              type="number"
              min={1}
              value={revisionNumber}
              onChange={(e) => setRevisionNumber(e.target.value)}
            />
          </div>
          {winError ? <p className="text-sm text-destructive">{winError}</p> : null}
          {winResult ? <p className="text-sm text-muted-foreground">{winResult}</p> : null}
          <Button type="button" onClick={() => void submitWin()} disabled={winLoading}>
            {winLoading ? 'Submitting…' : 'Progress to sales order'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Close tender (no sales order)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Uses the same tender code as on the left.
          </p>
          <div className="space-y-2">
            <Label>Outcome</Label>
            <Select value={closeOutcome} onValueChange={setCloseOutcome}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="lost">Lost</SelectItem>
                <SelectItem value="withdrawn">Withdrawn</SelectItem>
                <SelectItem value="no_award">No award</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="notes">Notes (optional)</Label>
            <Input
              id="notes"
              value={closeNotes}
              onChange={(e) => setCloseNotes(e.target.value)}
              autoComplete="off"
            />
          </div>
          {closeError ? <p className="text-sm text-destructive">{closeError}</p> : null}
          {closeResult ? <p className="text-sm text-muted-foreground">{closeResult}</p> : null}
          <Button type="button" variant="secondary" onClick={() => void submitClose()} disabled={closeLoading}>
            {closeLoading ? 'Submitting…' : 'Close tender'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
