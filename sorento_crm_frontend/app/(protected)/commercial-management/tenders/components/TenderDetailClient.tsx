'use client';

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { toast } from 'sonner';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  closeTender,
  getTenderByCode,
  getTenderMilestones,
  getTenderQuotations,
  getTenderStagesSelect,
  getTenderSummary,
  reopenTender,
  createMilestone,
  updateTender,
} from '../services/tenderService';

type Props = { tenderCode: string };

export default function TenderDetailClient({ tenderCode }: Props) {
  const qc = useQueryClient();
  const [closeOpen, setCloseOpen] = useState(false);
  const [closeOutcome, setCloseOutcome] = useState('lost');
  const [winMqId, setWinMqId] = useState('');
  const [milestoneCode, setMilestoneCode] = useState('');

  const qTender = useQuery({
    queryKey: ['tender', tenderCode],
    queryFn: () => getTenderByCode(tenderCode),
  });
  const qSummary = useQuery({
    queryKey: ['tender-summary', tenderCode],
    queryFn: () => getTenderSummary(tenderCode),
  });
  const qMq = useQuery({
    queryKey: ['tender-quotations', tenderCode],
    queryFn: () => getTenderQuotations(tenderCode),
  });
  const qMilestones = useQuery({
    queryKey: ['tender-milestones', tenderCode],
    queryFn: () => getTenderMilestones(tenderCode),
  });
  const { data: stages = [] } = useQuery({
    queryKey: ['tender-stages-select'],
    queryFn: getTenderStagesSelect,
  });

  const mClose = useMutation({
    mutationFn: () =>
      closeTender(tenderCode, {
        outcome: closeOutcome,
        winning_master_quotation_id: closeOutcome === 'won' ? winMqId || undefined : undefined,
      }),
    onSuccess: () => {
      toast.success('Tender closed');
      setCloseOpen(false);
      void qc.invalidateQueries({ queryKey: ['tender', tenderCode] });
      void qc.invalidateQueries({ queryKey: ['tender-summary', tenderCode] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const mReopen = useMutation({
    mutationFn: () => reopenTender(tenderCode),
    onSuccess: () => {
      toast.success('Tender reopened');
      void qc.invalidateQueries({ queryKey: ['tender', tenderCode] });
      void qc.invalidateQueries({ queryKey: ['tender-summary', tenderCode] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const mSave = useMutation({
    mutationFn: (patch: Parameters<typeof updateTender>[1]) => updateTender(tenderCode, patch),
    onSuccess: () => {
      toast.success('Saved');
      void qc.invalidateQueries({ queryKey: ['tender', tenderCode] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const mAddMilestone = useMutation({
    mutationFn: () => createMilestone(tenderCode, { milestone_code: milestoneCode.trim() }),
    onSuccess: () => {
      toast.success('Milestone added');
      setMilestoneCode('');
      void qc.invalidateQueries({ queryKey: ['tender-milestones', tenderCode] });
      void qc.invalidateQueries({ queryKey: ['tender-summary', tenderCode] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const t = qTender.data;
  if (qTender.isLoading || !t) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }

  const open = t.tender_lifecycle === 'open';

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{t.tender_code}</h2>
          <p className="text-muted-foreground text-sm">{t.title}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" asChild>
            <Link href="/commercial-management/tenders">Back to list</Link>
          </Button>
          {open ? (
            <Button variant="destructive" onClick={() => setCloseOpen(true)}>
              Close tender
            </Button>
          ) : (
            <Button variant="secondary" onClick={() => mReopen.mutate()} disabled={mReopen.isPending}>
              Reopen
            </Button>
          )}
        </div>
      </div>

      <Tabs defaultValue="details">
        <TabsList>
          <TabsTrigger value="details">Details</TabsTrigger>
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="quotations">Quotations</TabsTrigger>
          <TabsTrigger value="milestones">Milestones</TabsTrigger>
        </TabsList>
        <TabsContent value="details">
          <Card>
            <CardHeader>Details</CardHeader>
            <CardContent className="space-y-4 max-w-md">
              <div className="space-y-2">
                <Label>Title</Label>
                <Input
                  defaultValue={t.title}
                  disabled={!open}
                  onBlur={(e) => {
                    if (e.target.value !== t.title) mSave.mutate({ title: e.target.value });
                  }}
                />
              </div>
              <div className="space-y-2">
                <Label>Pipeline stage</Label>
                <Select
                  value={t.pipeline_stage || '__none__'}
                  disabled={!open}
                  onValueChange={(v) => mSave.mutate({ pipeline_stage: v === '__none__' ? '' : v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Stage" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__none__">—</SelectItem>
                    {stages.map((s) => (
                      <SelectItem key={s.stage_code} value={s.stage_code}>
                        {s.stage_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="summary">
          <Card>
            <CardHeader>Summary</CardHeader>
            <CardContent className="text-sm space-y-2">
              {qSummary.data ? (
                <>
                  <p>
                    Pipeline value: {qSummary.data.pipeline_value_amount ?? '—'}{' '}
                    {qSummary.data.pipeline_value_currency || ''}
                  </p>
                  <p>Open pipeline: {qSummary.data.in_open_pipeline ? 'yes' : 'no'}</p>
                  <p>
                    Milestones: {qSummary.data.milestone_achieved} / {qSummary.data.milestone_total}
                  </p>
                  <p>Master quotations: {qSummary.data.master_quotation_count}</p>
                </>
              ) : (
                <p className="text-muted-foreground">Loading…</p>
              )}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="quotations">
          <Card>
            <CardHeader>Quotations</CardHeader>
            <CardContent className="space-y-2">
              {(qMq.data || []).map((q) => (
                <div key={q.quotation_code} className="border-b pb-2 text-sm">
                  <span className="font-medium">{q.quotation_code}</span> — {q.title}{' '}
                  <span className="text-muted-foreground">({q.path_role})</span>
                </div>
              ))}
              {qMq.data?.length === 0 && <p className="text-muted-foreground text-sm">None</p>}
            </CardContent>
          </Card>
        </TabsContent>
        <TabsContent value="milestones">
          <Card>
            <CardHeader>Milestones</CardHeader>
            <CardContent className="space-y-4">
              {open && (
                <div className="flex gap-2 max-w-md">
                  <Input
                    placeholder="Milestone code"
                    value={milestoneCode}
                    onChange={(e) => setMilestoneCode(e.target.value)}
                  />
                  <Button disabled={!milestoneCode.trim() || mAddMilestone.isPending} onClick={() => mAddMilestone.mutate()}>
                    Add
                  </Button>
                </div>
              )}
              <ul className="text-sm space-y-1">
                {(qMilestones.data || []).map((m) => (
                  <li key={m.id}>
                    {m.milestone_code}
                    {m.due_on ? ` — due ${m.due_on}` : ''}
                    {m.achieved_at ? ' (done)' : ''}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      <AlertDialog open={closeOpen} onOpenChange={setCloseOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Close tender</AlertDialogTitle>
            <AlertDialogDescription>
              This sets the commercial outcome and lifecycle. This action cannot be undone from here without reopen.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <div className="space-y-2 py-2">
            <Label>Outcome</Label>
            <Select value={closeOutcome} onValueChange={setCloseOutcome}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="won">Won</SelectItem>
                <SelectItem value="lost">Lost</SelectItem>
                <SelectItem value="cancelled">Cancelled</SelectItem>
                <SelectItem value="no_bid">No bid</SelectItem>
              </SelectContent>
            </Select>
            {closeOutcome === 'won' && (
              <div className="space-y-2">
                <Label>Winning quotation</Label>
                <Select value={winMqId || '__pick__'} onValueChange={(v) => setWinMqId(v === '__pick__' ? '' : v)}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select path" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="__pick__">—</SelectItem>
                    {(qMq.data || []).map((q) => (
                      <SelectItem key={q.id} value={q.id}>
                        {q.quotation_code} — {q.title}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={(e) => {
                e.preventDefault();
                mClose.mutate();
              }}
            >
              Close tender
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
