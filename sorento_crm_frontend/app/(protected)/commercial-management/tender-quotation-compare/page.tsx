'use client';

import { useCallback, useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
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
import { Badge } from '@/components/ui/badge';

type CompareRow = {
  tender_code: string;
  quotation_code: string;
  title: string;
  path_role: string;
  quotation_stage: { stage_code: string; stage_name: string; is_terminal: boolean };
  owner?: { user_code: string; name: string | null } | null;
  salesperson_name?: string | null;
  quoted_amount: string | null;
  quoted_currency: string | null;
  updated_at: string;
};

export default function TenderQuotationComparePage() {
  const [tenderCode, setTenderCode] = useState('');
  const [rows, setRows] = useState<CompareRow[]>([]);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    const tc = tenderCode.trim();
    if (!tc) {
      toast.error('Enter a tender code.');
      return;
    }
    setLoading(true);
    try {
      const enc = encodeURIComponent(tc);
      const res = await apiFetch(
        `/api/commercial-management/tenders/by-code/${enc}/master-quotations/compare`,
      );
      if (!res.ok) {
        toast.error('Could not load quotations for this tender.');
        setRows([]);
        return;
      }
      const data = (await res.json()) as CompareRow[];
      setRows(data);
    } finally {
      setLoading(false);
    }
  }, [tenderCode]);

  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>Tender quotation comparison</ToolbarTitle>
        </ToolbarHeading>
      </Toolbar>

      <div className="flex flex-col gap-6 py-4">
        <div className="grid gap-4 md:grid-cols-2 md:items-end max-w-xl">
          <div className="space-y-2">
            <Label htmlFor="tender-code">Tender code</Label>
            <Input
              id="tender-code"
              value={tenderCode}
              onChange={(e) => setTenderCode(e.target.value)}
              placeholder="e.g. T-ABC12345"
            />
          </div>
          <Button onClick={() => void load()} disabled={loading}>
            Load
          </Button>
        </div>

        {rows.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Quotation</TableHead>
                <TableHead>Title</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead>Owner</TableHead>
                <TableHead>Salesperson</TableHead>
                <TableHead>Amount</TableHead>
                <TableHead>Updated</TableHead>
                <TableHead className="text-right">Open</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((r) => (
                <TableRow key={`${r.tender_code}-${r.quotation_code}`}>
                  <TableCell className="font-medium">{r.quotation_code}</TableCell>
                  <TableCell>{r.title}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{r.quotation_stage.stage_name}</Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {r.owner?.name || r.owner?.user_code || '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {r.salesperson_name || '—'}
                  </TableCell>
                  <TableCell className="text-sm">
                    {r.quoted_amount != null && r.quoted_currency
                      ? `${r.quoted_amount} ${r.quoted_currency}`
                      : '—'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-sm">
                    {new Date(r.updated_at).toLocaleString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="outline" size="sm" asChild>
                      <Link
                        href={`/commercial-management/quotation-revisions?tender=${encodeURIComponent(r.tender_code)}&quotation=${encodeURIComponent(r.quotation_code)}`}
                      >
                        Workspace
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </div>
    </Container>
  );
}
