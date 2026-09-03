'use client';

/**
 * "Use template..." - pull one of the designed templates onto this line's tag (D51).
 *
 * Any family, not just the line's own: the family rule picks the starting point
 * and this is where somebody disagrees with it. The line's own family is listed
 * first so the ordinary answer is the first one.
 */

import { useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { familyLabel, type TagTemplate } from '@/lib/dealer-kit/tag-template-types';

interface Props {
  open: boolean;
  templates: TagTemplate[];
  /** The template the tag is on now, preselected so "Reset to template" is one click. */
  currentTemplateId: string | null;
  /** The family the line's code says it is, listed first. */
  preferredFamily: string | null;
  onCancel: () => void;
  /**
   * `applyToAll` is the "Apply to all lines" checkbox (default off, AC-S5-4):
   * on, the chosen template replaces every line's tag, not only this one.
   * Either way it replaces immediately - the confirm dialog that used to sit
   * in front of this is gone (D11); Undo is the safety net now.
   */
  onConfirm: (templateId: string, applyToAll: boolean) => void;
}

export function TemplatePickDialog({
  open,
  templates,
  currentTemplateId,
  preferredFamily,
  onCancel,
  onConfirm,
}: Props) {
  const [selected, setSelected] = useState('');
  const [applyToAll, setApplyToAll] = useState(false);

  useEffect(() => {
    if (open) {
      setSelected(currentTemplateId ?? '');
      setApplyToAll(false);
    }
  }, [open, currentTemplateId]);

  const options = useMemo(() => {
    const rows = templates.map((template) => ({
      value: template.id,
      label: template.name,
      description: `${familyLabel(template.family)} / ${template.print_size.width_mm} x ${template.print_size.height_mm} mm`,
      family: template.family,
    }));
    // The line's own family first, then the rest in catalogue order.
    return [
      ...rows.filter((row) => row.family === preferredFamily),
      ...rows.filter((row) => row.family !== preferredFamily),
    ].map(({ value, label, description }) => ({ value, label, description }));
  }, [templates, preferredFamily]);

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onCancel()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Use a template for this tag</DialogTitle>
        </DialogHeader>
        <DialogBody className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label className="text-xs text-muted-foreground">Template</Label>
            <SearchableSelect
              value={selected}
              onChange={setSelected}
              options={options}
              clearable
              placeholder="Search templates"
            />
          </div>
          {templates.length === 0 && (
            <p className="text-xs text-muted-foreground">
              There are no tag templates yet. Design one under Tag Templates first.
            </p>
          )}
          <label className="flex items-center gap-2 text-xs text-foreground">
            <Checkbox
              size="sm"
              checked={applyToAll}
              onCheckedChange={(checked) => setApplyToAll(checked === true)}
            />
            Apply to all lines
          </label>
        </DialogBody>
        <DialogFooter>
          <Button variant="outline" onClick={onCancel}>
            Cancel
          </Button>
          <Button disabled={!selected} onClick={() => onConfirm(selected, applyToAll)}>
            Use template
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
