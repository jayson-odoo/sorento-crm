'use client';
import { useEffect, useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useCreateLookupSet, useUpdateLookupSet, useLookupSet, useEligibility } from '../hooks/useLookupSets';

const slugify = (s: string) => s.toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');

export default function LookupSetFormDialog({
  open, onOpenChange, setId,
}: { open: boolean; onOpenChange: (o: boolean) => void; setId?: string }) {
  const isEdit = !!setId;
  const { data: existing } = useLookupSet(setId ?? null);
  const create = useCreateLookupSet();
  const update = useUpdateLookupSet();
  const { data: eligibility } = useEligibility(true);

  const [setKey, setSetKey] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [skipBinding, setSkipBinding] = useState(false);
  const [tableName, setTableName] = useState('');
  const [columnName, setColumnName] = useState('');

  useEffect(() => {
    if (existing && isEdit) {
      setSetKey(existing.set_key); setName(existing.name);
      setDescription(existing.description ?? ''); setIsActive(existing.is_active);
    } else if (!isEdit) {
      setSetKey(''); setName(''); setDescription(''); setIsActive(true);
      setSkipBinding(false); setTableName(''); setColumnName('');
    }
  }, [existing, isEdit, open]);

  const tables = useMemo(() => {
    const seen = new Map<string, string>();
    (eligibility ?? []).forEach((e) => seen.set(e.table_name, e.table_label));
    return Array.from(seen.entries()).map(([table_name, table_label]) => ({ table_name, table_label }));
  }, [eligibility]);
  const columns = useMemo(
    () => (eligibility ?? []).filter((e) => e.table_name === tableName && !e.is_bound),
    [eligibility, tableName],
  );

  // Auto-suggest set_key + name from selected (table, column)
  useEffect(() => {
    if (isEdit) return;
    if (!tableName || !columnName) return;
    const elig = (eligibility ?? []).find((e) => e.table_name === tableName && e.column_name === columnName);
    if (!elig) return;
    if (!setKey) setSetKey(slugify(`${tableName}_${columnName}`));
    if (!name) setName(`${elig.table_label} — ${elig.column_label}`);
  }, [tableName, columnName, eligibility, isEdit, setKey, name]);

  async function submit() {
    if (isEdit) {
      await update.mutateAsync({ id: setId!, data: { set_key: setKey, name, description, is_active: isActive } });
    } else {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const payload: any = { set_key: setKey, name, description, is_active: isActive };
      if (!skipBinding && tableName && columnName) {
        payload.initial_binding = { table_name: tableName, column_name: columnName };
      }
      await create.mutateAsync(payload);
    }
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit lookup set' : 'Add lookup set'}</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {!isEdit && (
            <>
              <div className="text-sm font-medium">Where will this dropdown appear?</div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Table</Label>
                  <Select value={tableName} onValueChange={(v) => { setTableName(v); setColumnName(''); }}
                          disabled={skipBinding}>
                    <SelectTrigger><SelectValue placeholder="Select table" /></SelectTrigger>
                    <SelectContent>
                      {tables.map((t) => (
                        <SelectItem key={t.table_name} value={t.table_name}>{t.table_label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label>Column</Label>
                  <Select value={columnName} onValueChange={setColumnName} disabled={skipBinding || !tableName}>
                    <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
                    <SelectContent>
                      {columns.map((c) => (
                        <SelectItem key={c.column_name} value={c.column_name}>{c.column_label}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Switch checked={skipBinding} onCheckedChange={setSkipBinding} />
                <Label>Skip — create unbound set</Label>
              </div>
            </>
          )}
          <div>
            <Label>Set key</Label>
            <Input value={setKey} onChange={(e) => setSetKey(e.target.value)}
                   placeholder="lowercase_with_underscores" />
          </div>
          <div>
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div>
            <Label>Description</Label>
            <Textarea value={description} onChange={(e) => setDescription(e.target.value)} />
          </div>
          <div className="flex items-center gap-2">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            <Label>Active</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!setKey || !name}>
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
