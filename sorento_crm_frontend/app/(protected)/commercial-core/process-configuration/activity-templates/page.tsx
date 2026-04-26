'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { RuntimeTemplateTasksPanel } from '../_components/RuntimeTemplateTasksPanel';
import { createRuntimeActivityTemplate, deleteRuntimeActivityTemplate, listRuntimeActivityTemplates } from '../services/commercialActivityPlanService';

export default function ActivityTemplatesPage() {
  const qc = useQueryClient();
  const [openAccordion, setOpenAccordion] = useState<string[]>([]);
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [deleteTplId, setDeleteTplId] = useState<string | null>(null);

  const { data: templates = [], isLoading } = useQuery({
    queryKey: ['commercial-activity-templates-runtime'],
    queryFn: () => listRuntimeActivityTemplates(true),
  });

  const createMut = useMutation({
    mutationFn: () => createRuntimeActivityTemplate({ name: newName.trim(), is_active: true }),
    onSuccess: () => {
      toast.success('Template created');
      setCreateOpen(false);
      setNewName('');
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteRuntimeActivityTemplate(id),
    onSuccess: () => {
      toast.success('Template deleted');
      setDeleteTplId(null);
      void qc.invalidateQueries({ queryKey: ['commercial-activity-templates-runtime'] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2">
        <CardTitle>Task templates</CardTitle>
        <Button type="button" size="sm" onClick={() => setCreateOpen(true)}>
          <Plus className="size-4" />
          New template
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : templates.length === 0 ? (
          <p className="text-muted-foreground text-sm">No active templates.</p>
        ) : (
          <Accordion type="multiple" value={openAccordion} onValueChange={setOpenAccordion}>
            {templates.map((t) => (
              <AccordionItem key={t.id} value={t.id}>
                <AccordionTrigger className="text-start">
                  <span className="flex flex-wrap items-center gap-2">
                    <span>{t.name}</span>
                    <span className="text-muted-foreground text-xs font-normal">v{t.version_number}</span>
                  </span>
                </AccordionTrigger>
                <AccordionContent>
                  <div className="flex justify-end pb-2">
                    <Button type="button" variant="outline" size="sm" onClick={() => setDeleteTplId(t.id)}>
                      Delete template
                    </Button>
                  </div>
                  <RuntimeTemplateTasksPanel
                    templateId={t.id}
                    open={openAccordion.includes(t.id)}
                    layout="tree"
                    showAdvancedLink={false}
                  />
                </AccordionContent>
              </AccordionItem>
            ))}
          </Accordion>
        )}
      </CardContent>

      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New template</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 py-2">
            <Label>Name</Label>
            <Input value={newName} onChange={(e) => setNewName(e.target.value)} />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setCreateOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              disabled={!newName.trim() || createMut.isPending}
              onClick={() => createMut.mutate()}
            >
              Create
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={!!deleteTplId}
        onOpenChange={(o) => !o && setDeleteTplId(null)}
        description="Delete this template and all of its tasks?"
        onDelete={async () => {
          if (deleteTplId) await deleteMut.mutateAsync(deleteTplId);
        }}
      />
    </Card>
  );
}
