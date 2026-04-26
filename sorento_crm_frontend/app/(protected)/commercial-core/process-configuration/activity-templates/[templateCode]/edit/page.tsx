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
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { getActivityTemplate, updateActivityTemplate } from '../../../services/activityTemplateService';

export default function EditActivityTemplatePage({ params }: { params: Promise<{ templateCode: string }> }) {
  const { templateCode } = use(params);
  const code = decodeURIComponent(templateCode);
  const router = useRouter();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['commercial-activity-template', code],
    queryFn: () => getActivityTemplate(code),
  });
  const [name, setName] = useState('');
  const [description, setDesc] = useState('');
  const [sort_order, setSort] = useState(0);
  const [is_active, setActive] = useState(true);
  const [payloadText, setPayloadText] = useState('{}');

  useEffect(() => {
    if (!data) return;
    setName(data.name);
    setDesc(data.description || '');
    setSort(data.sort_order);
    setActive(data.is_active);
    setPayloadText(JSON.stringify(data.payload || {}, null, 2));
  }, [data]);

  const mut = useMutation({
    mutationFn: () => {
      let payload: Record<string, unknown> = {};
      try {
        payload = JSON.parse(payloadText || '{}') as Record<string, unknown>;
      } catch {
        throw new Error('Payload must be valid JSON');
      }
      return updateActivityTemplate(code, { name, description: description || undefined, sort_order, is_active, payload });
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates'] });
      void qc.invalidateQueries({ queryKey: ['commercial-activity-template', code] });
      toast.success('Saved');
      router.push('/commercial-core/process-configuration/activity-templates');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading || !data) {
    return <p className="text-muted-foreground text-sm">Loading…</p>;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Edit {code}</CardTitle>
      </CardHeader>
      <CardContent className="max-w-lg space-y-4">
        <div>
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label>Description</Label>
          <Input value={description} onChange={(e) => setDesc(e.target.value)} />
        </div>
        <div>
          <Label>Sort order</Label>
          <Input type="number" value={sort_order} onChange={(e) => setSort(parseInt(e.target.value, 10) || 0)} />
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={is_active} onCheckedChange={setActive} id="at2-active" />
          <Label htmlFor="at2-active">Active</Label>
        </div>
        <div>
          <Label>Payload (JSON)</Label>
          <Textarea value={payloadText} onChange={(e) => setPayloadText(e.target.value)} rows={8} className="font-mono text-sm" />
        </div>
        <div className="flex gap-2">
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            Save
          </Button>
          <Button variant="outline" asChild>
            <Link href="/commercial-core/process-configuration/activity-templates">Cancel</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
