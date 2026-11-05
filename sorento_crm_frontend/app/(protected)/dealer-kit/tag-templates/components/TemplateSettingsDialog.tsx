'use client';

/**
 * Edit an existing template's name, family and print size
 * (PRICETAG-DESIGNER-GAPS item 4).
 *
 * The host decides how each change is written: on the editor page the name
 * and family go straight to the template row (they are not versioned), and a
 * size change goes through the same draft resize the left-rail size control
 * uses, so it lands in the draft and reaches the live tag on the next publish.
 * A size change keeps every layer where it is, so the dialog warns and counts
 * the layers the new size would cut off.
 */

import { useEffect, useMemo, useState } from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
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
import { NumberInput } from '@/components/ui/number-input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { numberFieldError, parseNumberDraft } from '@/lib/number-field';
import { layersOutside } from '@/lib/dealer-kit/layer-bounds';
import {
  SPEC_SHEET_FAMILIES,
  TAG_TEMPLATE_FAMILIES,
  isSpecSheetFamily,
  type TagLayer,
  type TagTemplateFamily,
} from '@/lib/dealer-kit/tag-template-types';

export interface TemplateSettingsValues {
  name: string;
  family: TagTemplateFamily;
  width_mm: number;
  height_mm: number;
}

interface TemplateSettingsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  initial: TemplateSettingsValues;
  /** The draft layers, to count what a smaller size would cut off. */
  layers: TagLayer[];
  /** Whether a published version is live (its size changes only on publish). */
  isLive?: boolean;
  /** Throws to keep the dialog open with the error shown. */
  onSave: (values: TemplateSettingsValues) => Promise<void>;
}

const MIN_MM = 10;

/**
 * A price tag stays a price tag and a spec sheet page stays a page: the editor
 * and the request designer treat the two kinds differently. A family that has
 * since left the list stays offered, so the select never shows blank.
 */
function familyOptions(current: string): { value: string; label: string }[] {
  const options = isSpecSheetFamily(current) ? SPEC_SHEET_FAMILIES : TAG_TEMPLATE_FAMILIES;
  return options.some((option) => option.value === current)
    ? options
    : [{ value: current, label: current }, ...options];
}

export function TemplateSettingsDialog({
  open,
  onOpenChange,
  initial,
  layers,
  isLive = false,
  onSave,
}: TemplateSettingsDialogProps) {
  const [name, setName] = useState(initial.name);
  const [family, setFamily] = useState<TagTemplateFamily>(initial.family);
  const [widthMm, setWidthMm] = useState<number | null>(initial.width_mm);
  const [heightMm, setHeightMm] = useState<number | null>(initial.height_mm);
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Re-seed on every open, so a cancelled edit never lingers.
  useEffect(() => {
    if (open) {
      setName(initial.name);
      setFamily(initial.family);
      setWidthMm(initial.width_mm);
      setHeightMm(initial.height_mm);
      setChecked(false);
      setError(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- seed on open only
  }, [open]);

  const options = useMemo(() => familyOptions(initial.family), [initial.family]);

  const width = parseNumberDraft(widthMm);
  const height = parseNumberDraft(heightMm);
  const sizeValid =
    !numberFieldError(widthMm, { min: MIN_MM }) && !numberFieldError(heightMm, { min: MIN_MM });
  const sizeChanged =
    sizeValid && (width !== initial.width_mm || height !== initial.height_mm);
  const cutOff = sizeChanged ? layersOutside(layers, width as number, height as number) : 0;

  const widthError = checked ? numberFieldError(widthMm, { min: MIN_MM }) : undefined;
  const heightError = checked ? numberFieldError(heightMm, { min: MIN_MM }) : undefined;
  const canSubmit = name.trim().length > 0 && !saving;

  const submit = async () => {
    setError(null);
    setChecked(true);
    if (!sizeValid) return;
    setSaving(true);
    try {
      await onSave({
        name: name.trim(),
        family,
        width_mm: width as number,
        height_mm: height as number,
      });
      onOpenChange(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not save the template settings');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Template settings</DialogTitle>
          <DialogDescription>Name, product family and print size.</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-2">
            <Label htmlFor="ts-name">Name</Label>
            <Input id="ts-name" value={name} onChange={(e) => setName(e.target.value)} />
          </div>

          <div className="flex flex-col gap-2">
            <Label>Family</Label>
            <SearchableSelect
              value={family}
              onChange={(v: string) => setFamily(v as TagTemplateFamily)}
              options={options}
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-2">
              <Label htmlFor="ts-width">Width (mm)</Label>
              <NumberInput
                id="ts-width"
                value={widthMm}
                min={MIN_MM}
                onValueChange={setWidthMm}
                error={widthError}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="ts-height">Height (mm)</Label>
              <NumberInput
                id="ts-height"
                value={heightMm}
                min={MIN_MM}
                onValueChange={setHeightMm}
                error={heightError}
              />
            </div>
          </div>

          {sizeChanged && (
            <Alert variant="warning" size="sm" role="status">
              <AlertDescription className="flex flex-col gap-1">
                <p>Layers keep their place and may need moving.</p>
                {cutOff > 0 && (
                  <p>
                    {cutOff === 1 ? '1 layer sits' : `${cutOff} layers sit`} outside {width} x{' '}
                    {height} mm.
                  </p>
                )}
                {isLive && <p>The live version keeps its size until you publish.</p>}
              </AlertDescription>
            </Alert>
          )}

          {error && <p className="text-sm text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
