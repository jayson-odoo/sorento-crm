'use client';

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useCreateKind, useUpdateKind } from '../hooks/useWarrantyConfig';
import type { WarrantyKind } from '../types/warranty.types';

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Present = Edit. */
  kind?: WarrantyKind | null;
}

export function KindFormDialog({ open, onOpenChange, kind }: Props) {
  const create = useCreateKind();
  const update = useUpdateKind();
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [tried, setTried] = useState(false);
  const [filledFor, setFilledFor] = useState<string | null>(null);

  useEffect(() => {
    const key = open ? (kind?.id ?? 'new') : null;
    if (key === filledFor) return;
    setFilledFor(key);
    if (!key) return;
    setName(kind?.name ?? '');
    setCode(kind?.code ?? '');
    setTried(false);
  }, [open, kind, filledFor]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setTried(true);
    if (!name.trim() || !code.trim()) return;
    const values = { name: name.trim(), code: code.trim() };
    try {
      if (kind) await update.mutateAsync({ id: kind.id, values });
      else await create.mutateAsync(values);
      onOpenChange(false);
    } catch {
      /* the mutation toasts the server's message */
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="overflow-hidden sm:max-w-md" aria-describedby={undefined}>
        <DialogHeader>
          <DialogTitle>{kind ? 'Edit kind' : 'Create kind'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={submit} className="flex min-h-0 flex-1 flex-col gap-4">
          <DialogBody className="min-h-0 space-y-4 overflow-y-auto">
            <div className="space-y-1">
              <Label htmlFor="wk-name">Kind *</Label>
              <Input id="wk-name" value={name} onChange={(e) => setName(e.target.value)} />
              {tried && !name.trim() && <p role="alert" className="text-sm text-destructive">Kind is required.</p>}
            </div>
            <div className="space-y-1">
              <Label htmlFor="wk-code">Code *</Label>
              <Input id="wk-code" value={code} onChange={(e) => setCode(e.target.value)} />
              {tried && !code.trim() && <p role="alert" className="text-sm text-destructive">Code is required.</p>}
            </div>
          </DialogBody>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
            <Button type="submit" disabled={create.isPending || update.isPending}>{kind ? 'Save' : 'Create'}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
