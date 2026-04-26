'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { createCheckpointTemplate } from '../../services/checkpointTemplateService';

export default function NewCheckpointPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [checkpoint_code, setCode] = useState('');
  const [name, setName] = useState('');
  const [sort_order, setSort] = useState(0);
  const [is_active, setActive] = useState(true);

  const mut = useMutation({
    mutationFn: () => createCheckpointTemplate({ checkpoint_code, name, sort_order, is_active }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ['commercial-checkpoint-templates'] });
      toast.success('Saved');
      router.push('/commercial-core/process-configuration/tender-checkpoint-templates');
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>New checkpoint template</CardTitle>
      </CardHeader>
      <CardContent className="max-w-lg space-y-4">
        <div>
          <Label>Code</Label>
          <Input value={checkpoint_code} onChange={(e) => setCode(e.target.value)} />
        </div>
        <div>
          <Label>Name</Label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <Label>Sort order</Label>
          <Input type="number" value={sort_order} onChange={(e) => setSort(parseInt(e.target.value, 10) || 0)} />
        </div>
        <div className="flex items-center gap-2">
          <Switch checked={is_active} onCheckedChange={setActive} id="ck-active" />
          <Label htmlFor="ck-active">Active</Label>
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
