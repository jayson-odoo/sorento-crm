'use client';

import { useEffect, useState } from 'react';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useUpdateAccessoryTemplate } from '../hooks/useAccessoryTemplates';
import type { AccessoryTemplateRecord } from '../../services/accessoryTemplateService';

export function RenameAccessoryTemplateDialog({
  open,
  onOpenChange,
  template,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  template: AccessoryTemplateRecord | null;
}) {
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const update = useUpdateAccessoryTemplate();

  useEffect(() => {
    if (!open) return;
    setName(template?.name ?? '');
    setError(null);
  }, [open, template]);

  const submit = async () => {
    if (!template) return;
    setError(null);
    try {
      await update.mutateAsync({ id: template.id, input: { name: name.trim() } });
      toast.success('Accessories template renamed');
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not rename this template');
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Rename template</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-2 py-2">
          <Label htmlFor="at-name">Name</Label>
          <Input id="at-name" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={update.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name.trim() || update.isPending}>
            {update.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
