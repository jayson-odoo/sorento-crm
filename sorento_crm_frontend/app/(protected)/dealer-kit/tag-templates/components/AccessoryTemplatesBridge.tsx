'use client';

/**
 * PRICETAG-ACCESSORY-DESIGNER S3: the editor's window on the saved accessories templates: it reads
 * the list (for the toolbar menu and the "Linked" note) and owns the "Save as accessories template"
 * dialog. Mounted only where a query client exists, so a bare canvas test or host still renders.
 */
import { useEffect, useState } from 'react';
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
import type { AccessoryDesign } from '@/lib/dealer-kit/accessory-card';
import type { AccessoryTemplateRecord } from '../../services/accessoryTemplateService';
import {
  useAccessoryTemplatesQuery,
  useCreateAccessoryTemplate,
} from '../../accessory-templates/hooks/useAccessoryTemplates';

export interface SaveTemplateRequest {
  layerId: string;
  design: AccessoryDesign;
}

export function AccessoryTemplatesBridge({
  onTemplates,
  request,
  onSaved,
  onClose,
}: {
  onTemplates: (templates: AccessoryTemplateRecord[]) => void;
  request: SaveTemplateRequest | null;
  onSaved: (layerId: string, template: AccessoryTemplateRecord) => void;
  onClose: () => void;
}) {
  const query = useAccessoryTemplatesQuery();
  const create = useCreateAccessoryTemplate();
  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const templates = query.data;

  useEffect(() => {
    onTemplates(templates ?? []);
  }, [templates, onTemplates]);

  useEffect(() => {
    if (!request) return;
    setName('');
    setError(null);
  }, [request]);

  const submit = async () => {
    if (!request) return;
    setError(null);
    try {
      const saved = await create.mutateAsync({ name: name.trim(), design: request.design });
      onSaved(request.layerId, saved);
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this template');
    }
  };

  return (
    <Dialog open={request !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Save as accessories template</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-2 py-2">
          <Label htmlFor="accessory-template-name">Name</Label>
          <Input
            id="accessory-template-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={create.isPending}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!name.trim() || create.isPending}>
            {create.isPending ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
