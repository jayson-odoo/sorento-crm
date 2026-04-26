'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Container } from '@/components/common/container';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useHasPermission } from '@/hooks/usePermissions';
import { QuotationReactQuill } from '@/components/commercial/QuotationReactQuill';
import {
  createQuotationEmailTemplate,
  deleteQuotationEmailTemplate,
  listQuotationEmailTemplatesAll,
  patchQuotationEmailTemplate,
  type QuotationEmailTemplateRow,
} from '@/app/(protected)/commercial-management/quotation-revisions/services/quotationPrintEmailService';

export default function QuotationEmailTemplatesPage() {
  const canView = useHasPermission('commercial_core.master_quotations.view');
  const canEdit = useHasPermission('commercial_core.master_quotations.edit');
  const [rows, setRows] = useState<QuotationEmailTemplateRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<QuotationEmailTemplateRow | null>(null);
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [subjectTemplate, setSubjectTemplate] = useState('');
  const [bodyTemplate, setBodyTemplate] = useState('');
  const [isDefault, setIsDefault] = useState(false);

  const load = useCallback(async () => {
    if (!canView) return;
    setLoading(true);
    try {
      const data = await listQuotationEmailTemplatesAll();
      setRows(data);
    } catch {
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, [canView]);

  useEffect(() => {
    void load();
  }, [load]);

  const openCreate = () => {
    setEditing(null);
    setCode('');
    setName('');
    setSubjectTemplate('Quotation {{quotation_code}} — {{client_name}}');
    setBodyTemplate(
      '<p>Dear {{client_name}},</p><p>Please find our quotation <strong>{{quotation_code}}</strong> attached.</p>',
    );
    setIsDefault(false);
    setDialogOpen(true);
  };

  const openEdit = (r: QuotationEmailTemplateRow) => {
    setEditing(r);
    setCode(r.code);
    setName(r.name);
    setSubjectTemplate(r.subject_template);
    setBodyTemplate(r.body_html_template);
    setIsDefault(r.is_default);
    setDialogOpen(true);
  };

  const save = async () => {
    if (!canEdit) return;
    try {
      if (editing) {
        await patchQuotationEmailTemplate(editing.id, {
          code: code.trim(),
          name: name.trim(),
          subject_template: subjectTemplate,
          body_html_template: bodyTemplate,
          is_default: isDefault,
        });
        toast.success('Template updated');
      } else {
        await createQuotationEmailTemplate({
          code: code.trim(),
          name: name.trim(),
          subject_template: subjectTemplate,
          body_html_template: bodyTemplate,
          is_default: isDefault,
        });
        toast.success('Template created');
      }
      setDialogOpen(false);
      void load();
    } catch {
      toast.error('Save failed');
    }
  };

  const remove = async (r: QuotationEmailTemplateRow) => {
    if (!canEdit) return;
    if (!confirm(`Deactivate template “${r.name}”?`)) return;
    try {
      await deleteQuotationEmailTemplate(r.id);
      toast.success('Template deactivated');
      void load();
    } catch {
      toast.error('Deactivate failed');
    }
  };

  if (!canView) {
    return (
      <Container width="fluid" className="py-8">
        <p className="text-sm text-muted-foreground">You do not have access to this page.</p>
      </Container>
    );
  }

  return (
    <Container width="fluid" className="space-y-6 py-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">Quotation email templates</h1>
        {canEdit ? (
          <Button type="button" onClick={openCreate}>
            New template
          </Button>
        ) : null}
      </div>
      <div className="rounded-lg border">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground">
                  Loading…
                </TableCell>
              </TableRow>
            ) : rows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={4} className="text-muted-foreground">
                  No templates
                </TableCell>
              </TableRow>
            ) : (
              rows.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="font-medium">
                    {r.name}
                    {r.is_default ? (
                      <Badge variant="secondary" className="ml-2">
                        Default
                      </Badge>
                    ) : null}
                  </TableCell>
                  <TableCell>{r.code}</TableCell>
                  <TableCell>{r.is_active ? 'Active' : 'Inactive'}</TableCell>
                  <TableCell className="text-right">
                    {canEdit ? (
                      <div className="flex justify-end gap-2">
                        <Button type="button" variant="outline" size="sm" onClick={() => openEdit(r)}>
                          Edit
                        </Button>
                        {r.is_active ? (
                          <Button type="button" variant="ghost" size="sm" onClick={() => void remove(r)}>
                            Deactivate
                          </Button>
                        ) : null}
                      </div>
                    ) : null}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editing ? 'Edit template' : 'New template'}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-3">
            <div className="grid gap-1">
              <Label>Code</Label>
              <Input value={code} onChange={(e) => setCode(e.target.value)} disabled={!!editing} />
            </div>
            <div className="grid gap-1">
              <Label>Name</Label>
              <Input value={name} onChange={(e) => setName(e.target.value)} />
            </div>
            <div className="grid gap-1">
              <Label>Subject template</Label>
              <Input value={subjectTemplate} onChange={(e) => setSubjectTemplate(e.target.value)} />
            </div>
            <div className="flex items-center gap-2">
              <input
                id="tpl-default"
                type="checkbox"
                checked={isDefault}
                onChange={(e) => setIsDefault(e.target.checked)}
              />
              <Label htmlFor="tpl-default">Default template</Label>
            </div>
            <div className="grid gap-1">
              <Label>Body (HTML)</Label>
              <QuotationReactQuill value={bodyTemplate} onChange={setBodyTemplate} minHeightPx={200} />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setDialogOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void save()} disabled={!canEdit}>
              Save
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Container>
  );
}
