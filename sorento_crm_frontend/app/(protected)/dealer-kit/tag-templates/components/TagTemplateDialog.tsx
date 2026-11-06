'use client';

/**
 * Modal for creating a new tag template: the shared `TemplateSettingsForm` (the editor's
 * Template settings renders the same one, TAG-TEMPLATE-DUPLICATE item 7). Creates with an empty
 * layers array.
 */

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { parseNumberDraft } from '@/lib/number-field';
import { DEFAULT_TAG_SIZE, ALL_TEMPLATE_FAMILIES } from '@/lib/dealer-kit/tag-template-types';
import { createTemplate } from '../../services/tagTemplateService';
import {
  TemplateSettingsForm,
  templateSettingsErrors,
  templateSettingsValid,
  type TemplateSettingsDraft,
} from './TemplateSettingsForm';

interface TagTemplateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: () => void;
}

const BLANK: TemplateSettingsDraft = {
  name: '',
  family: 'ala_carte',
  price_type: null,
  width_mm: DEFAULT_TAG_SIZE.width_mm,
  height_mm: DEFAULT_TAG_SIZE.height_mm,
};

export function TagTemplateDialog({
  open,
  onOpenChange,
  onCreated,
}: TagTemplateDialogProps) {
  const router = useRouter();

  const [draft, setDraft] = useState<TemplateSettingsDraft>(BLANK);
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setDraft(BLANK);
      setError(null);
      setChecked(false);
    }
  }, [open]);

  const canSubmit = !templateSettingsErrors(draft).name && !saving;

  const submit = async () => {
    setError(null);
    setChecked(true);
    if (!templateSettingsValid(draft)) return;
    setSaving(true);
    try {
      const template = await createTemplate({
        name: draft.name.trim(),
        family: draft.family,
        price_type: draft.price_type,
        print_size: {
          width_mm: parseNumberDraft(draft.width_mm) as number,
          height_mm: parseNumberDraft(draft.height_mm) as number,
        },
      });
      toast.success(`Created template "${template.name}"`);
      onCreated?.();
      onOpenChange(false);
      router.push(`/dealer-kit/tag-templates/${template.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create the template');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>New tag template</DialogTitle>
          <DialogDescription>Name, product family, price type and print size.</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <TemplateSettingsForm
            value={draft}
            onChange={setDraft}
            familyOptions={ALL_TEMPLATE_FAMILIES}
            showErrors={checked}
            autoFocusName
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {saving ? 'Creating...' : 'Create template'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
