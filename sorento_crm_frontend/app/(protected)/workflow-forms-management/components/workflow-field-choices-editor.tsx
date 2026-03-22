'use client';

import { Plus, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export function WorkflowFieldChoicesEditor({
  options,
  onChange,
}: {
  options: { value: string; label: string }[];
  onChange: (next: { value: string; label: string }[]) => void;
}) {
  const list = options ?? [];
  const add = () => {
    const n = list.length + 1;
    onChange([...list, { value: `choice_${n}`, label: `Choice ${n}` }]);
  };
  const patch = (i: number, key: 'value' | 'label', v: string) => {
    const next = [...list];
    next[i] = { ...next[i], [key]: v };
    onChange(next);
  };
  const remove = (i: number) => {
    onChange(list.filter((_, j) => j !== i));
  };

  return (
    <div className="md:col-span-6 space-y-2 border-t border-border pt-3 mt-1">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Label className="text-xs font-medium">Choices</Label>
        <Button type="button" size="sm" variant="outline" onClick={add}>
          <Plus className="size-3.5 mr-1" />
          Add choice
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Each choice needs a unique <span className="font-medium">value</span> (stored in submissions) and a{' '}
        <span className="font-medium">label</span> (shown to users).
      </p>
      {list.length === 0 ? (
        <p className="text-xs text-amber-700 dark:text-amber-500">Add at least one choice for this field.</p>
      ) : (
        <div className="space-y-2">
          {list.map((o, oi) => (
            <div key={oi} className="flex flex-wrap gap-2 items-end">
              <div className="flex-1 min-w-[100px] space-y-1">
                <Label className="text-xs text-muted-foreground">Value</Label>
                <Input
                  value={o.value}
                  onChange={(e) => patch(oi, 'value', e.target.value)}
                  placeholder="e.g. acme_corp"
                />
              </div>
              <div className="flex-1 min-w-[100px] space-y-1">
                <Label className="text-xs text-muted-foreground">Label</Label>
                <Input
                  value={o.label}
                  onChange={(e) => patch(oi, 'label', e.target.value)}
                  placeholder="e.g. Acme Corp"
                />
              </div>
              <Button type="button" size="icon" variant="ghost" onClick={() => remove(oi)} aria-label="Remove choice">
                <Trash2 className="size-4 text-destructive" />
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
