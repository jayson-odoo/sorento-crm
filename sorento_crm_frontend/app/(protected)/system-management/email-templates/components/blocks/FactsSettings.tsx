'use client';

import { Plus, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import type { AnyBlockPatch, FactsBlock } from '../../types/emailTemplate.types';

export function FactsSettings({
  block,
  onChange,
}: {
  block: FactsBlock;
  onChange: (patch: AnyBlockPatch) => void;
}) {
  const patchRow = (index: number, patch: Partial<{ label: string; value: string }>) => {
    onChange({ rows: block.rows.map((row, i) => (i === index ? { ...row, ...patch } : row)) });
  };
  const removeRow = (index: number) => {
    onChange({ rows: block.rows.filter((_, i) => i !== index) });
  };
  const addRow = () => {
    onChange({ rows: [...block.rows, { label: '', value: '' }] });
  };

  return (
    <div className="space-y-2">
      {block.rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No rows yet.</p>
      ) : (
        <div className="space-y-2">
          {block.rows.map((row, index) => (
            <div key={index} className="flex items-center gap-2">
              <Input
                aria-label="Fact label"
                value={row.label}
                onChange={(e) => patchRow(index, { label: e.target.value })}
                placeholder="Customer"
                className="flex-1"
              />
              <Input
                aria-label="Fact value"
                value={row.value}
                onChange={(e) => patchRow(index, { value: e.target.value })}
                placeholder="{{ pr.customer }}"
                className="flex-1"
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="size-8 shrink-0 p-0 text-destructive"
                aria-label="Remove row"
                onClick={() => removeRow(index)}
              >
                <X className="size-4" />
              </Button>
            </div>
          ))}
        </div>
      )}
      <div className="flex items-center justify-between gap-2">
        <Button type="button" variant="outline" size="sm" onClick={addRow}>
          <Plus className="mr-1 size-4" /> Add row
        </Button>
        <div className="flex items-center gap-2">
          <Switch
            id={`facts-hide-empty-${block.id}`}
            checked={block.hide_empty}
            onCheckedChange={(checked) => onChange({ hide_empty: checked })}
          />
          <Label htmlFor={`facts-hide-empty-${block.id}`} className="text-xs">
            Hide empty rows
          </Label>
        </div>
      </div>
    </div>
  );
}

export default FactsSettings;
