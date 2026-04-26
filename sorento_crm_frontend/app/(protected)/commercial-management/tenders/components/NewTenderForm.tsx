'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { createTender, getTenderStagesSelect } from '../services/tenderService';

export default function NewTenderForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const defaultProject = searchParams.get('project_id') || '';
  const [projectId, setProjectId] = useState(defaultProject);
  const [tenderCode, setTenderCode] = useState('');
  const [title, setTitle] = useState('');
  const [pipelineStage, setPipelineStage] = useState<string>('');

  const { data: stages = [] } = useQuery({
    queryKey: ['tender-stages-select'],
    queryFn: getTenderStagesSelect,
  });

  const m = useMutation({
    mutationFn: () =>
      createTender({
        project_id: projectId.trim(),
        tender_code: tenderCode.trim(),
        title: title.trim(),
        pipeline_stage: pipelineStage || undefined,
      }),
    onSuccess: (t) => {
      toast.success('Tender created');
      router.push(`/commercial-management/tenders/${encodeURIComponent(t.tender_code)}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card className="max-w-lg">
      <CardHeader>New tender</CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="project_id">Project ID</Label>
          <Input
            id="project_id"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            placeholder="Paste project ID from project detail"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="tender_code">Tender code</Label>
          <Input id="tender_code" value={tenderCode} onChange={(e) => setTenderCode(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label htmlFor="title">Title</Label>
          <Input id="title" value={title} onChange={(e) => setTitle(e.target.value)} />
        </div>
        <div className="space-y-2">
          <Label>Pipeline stage</Label>
          <Select value={pipelineStage || '__none__'} onValueChange={(v) => setPipelineStage(v === '__none__' ? '' : v)}>
            <SelectTrigger>
              <SelectValue placeholder="Optional" />
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
        <Button
          disabled={m.isPending || !projectId.trim() || !tenderCode.trim() || !title.trim()}
          onClick={() => m.mutate()}
        >
          Create
        </Button>
      </CardContent>
    </Card>
  );
}
