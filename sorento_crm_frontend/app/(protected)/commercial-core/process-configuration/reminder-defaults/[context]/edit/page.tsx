'use client';

import { use, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { getReminderDefault, updateReminderDefault } from '../../../services/reminderDefaultsService';

export default function EditReminderDefaultPage({ params }: { params: Promise<{ context: string }> }) {
  const { context: ctxParam } = use(params);
  const context = decodeURIComponent(ctxParam);
  const router = useRouter();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['commercial-reminder-default', context],
    queryFn: () => getReminderDefault(context),
  });
  const [display_name, setName] = useState('');
  const [sort_order, setSort] = useState(0);
  const [ruleText, setRuleText] = useState('{}');

  useEffect(() => {
    if (!data) return;
    setName(data.display_name);
    setSort(data.sort_order);
    setRuleText(JSON.stringify(data.rule || {}, null, 2));
  }, [data]);

  const mut = useMutation({
    mutationFn: () => {
      let rule: Record<string, unknown> = {};
      try {
        rule = JSON.parse(ruleText || '{}') as Record<string, unknown>;
      } catch {
        throw new Error('Rule must be valid JSON');
      }
      return updateReminderDefault(context, { display_name, sort_order, rule });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-reminder-defaults'] });
      toast.success('Saved');
      router.push('/commercial-core/process-configuration/reminder-defaults');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading || !data) return <p className="text-muted-foreground text-sm">Loading…</p>;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Edit reminder ({context})</CardTitle>
      </CardHeader>
      <CardContent className="max-w-lg space-y-4">
        <div>
          <Label>Display name</Label>
          <Input value={display_name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label>Sort order</Label>
          <Input type="number" value={sort_order} onChange={(e) => setSort(parseInt(e.target.value, 10) || 0)} />
        </div>
        <div>
          <Label>Rule (JSON)</Label>
          <Textarea value={ruleText} onChange={(e) => setRuleText(e.target.value)} rows={8} className="font-mono text-sm" />
        </div>
        <div className="flex gap-2">
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            Save
          </Button>
          <Button variant="outline" asChild>
            <Link href="/commercial-core/process-configuration/reminder-defaults">Cancel</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
