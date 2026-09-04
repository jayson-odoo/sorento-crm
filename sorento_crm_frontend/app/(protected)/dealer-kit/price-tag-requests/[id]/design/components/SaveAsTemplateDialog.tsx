'use client';

/**
 * "Save as template" - publish the SELECTED line's designed tag as a reusable
 * template, ready in every request's "Use template..." picker (S4, D1).
 *
 * Name and family are prefilled (the line's code + its family) but both stay
 * editable - a design started for one product often earns a name of its own.
 * Product overrides on bound layers are stripped (`templateFromTag`); the
 * template is created AND published as v1 in one call, never left a draft.
 */

import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import {
  TAG_TEMPLATE_FAMILIES,
  type PlacedTag,
  type TagTemplate,
  type TagTemplateFamily,
} from '@/lib/dealer-kit/tag-template-types';
import { templateFromTag } from '@/lib/dealer-kit/request-tags';
import { createTemplateFromTag } from '../../../../services/tagTemplateService';

let idSeq = 0;
function newLayerId(): string {
  idSeq += 1;
  return `layer-${Date.now()}-${idSeq}`;
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  tag: PlacedTag | null;
  defaultName: string;
  defaultFamily: TagTemplateFamily;
  onCreated: (template: TagTemplate) => void;
}

export function SaveAsTemplateDialog({
  open,
  onOpenChange,
  tag,
  defaultName,
  defaultFamily,
  onCreated,
}: Props) {
  const [name, setName] = useState(defaultName);
  const [family, setFamily] = useState<TagTemplateFamily>(defaultFamily);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setName(defaultName);
    setFamily(defaultFamily);
    setError(null);
  }, [open, defaultName, defaultFamily]);

  const canSubmit = Boolean(tag) && name.trim().length > 0 && !saving;

  const submit = async () => {
    if (!tag) return;
    setError(null);
    setSaving(true);
    try {
      const payload = templateFromTag(tag, {
        name: name.trim(),
        family,
        newId: newLayerId,
      });
      const template = await createTemplateFromTag(payload);
      onCreated(template);
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save this template');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Save as template</DialogTitle>
          <DialogDescription>
            Publishes this design as a reusable template, ready right away in every
            request&apos;s &quot;Use template...&quot; picker.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="stt-name">Name</Label>
            <Input
              id="stt-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              autoFocus
            />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Family</Label>
            <SearchableSelect
              value={family}
              onChange={(v: string) => setFamily(v as TagTemplateFamily)}
              options={TAG_TEMPLATE_FAMILIES}
            />
          </div>

          {tag && (
            <div className="grid grid-cols-2 gap-y-1 text-sm">
              <span className="text-muted-foreground">Size</span>
              <span>
                {tag.width_mm} x {tag.height_mm} mm
              </span>
              <span className="text-muted-foreground">Layers</span>
              <span>{tag.layers.length}</span>
            </div>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {saving ? 'Saving...' : 'Save & publish'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
