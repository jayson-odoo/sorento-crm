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
import { getCheckpointTemplate, updateCheckpointTemplate } from '../../../services/checkpointTemplateService';

export default function EditCheckpointPage({ params }: { params: Promise<{ checkpointCode: string }> }) {
  const { checkpointCode } = use(params);
  const code = decodeURIComponent(checkpointCode);
  const router = useRouter();
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['commercial-checkpoint-template', code],
    queryFn: () => getCheckpointTemplate(code),
  });
  const [name, setName] = useState('');
  const [sort_order, setSort] = useState(0);
  const [is_active, setActive] = useState(true);

  useEffect(() => {
    if (!data) return;
    setName(data.name);
    setSort(data.sort_order);
    setActive(data.is_active);
  }, [data]);

  const mut = useMutation({
    mutationFn: () => updateCheckpointTemplate(code, { name, sort_order, is_active }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-checkpoint-templates'] });
      toast.success('Saved');
      router.push('/commercial-core/process-configuration/tender-checkpoint-templates');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (isLoading || !data) return <p className="text-muted-foreground text-sm">Loading…</p>;

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
          <Label>Sort order</Label>
          <Input type="number" value={sort_order} onChange={(e) => setSort(parseInt(e.target.value, 10) || 0)} />
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={is_active} onCheckedChange={setActive} id="ck2-active" />
          <Label htmlFor="ck2-active">Active</Label>
        </div>
        <div className="flex gap-2">
          <Button onClick={() => mut.mutate()} disabled={mut.isPending}>
            Save
          </Button>
          <Button variant="outline" asChild>
            <Link href="/commercial-core/process-configuration/tender-checkpoint-templates">Cancel</Link>
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
