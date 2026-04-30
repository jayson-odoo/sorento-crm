'use client';
import { useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import { useEligibility, useAddBinding } from '../hooks/useLookupSets';

export default function BindingAddDialog({
  open, onOpenChange, setId,
}: { open: boolean; onOpenChange: (o: boolean) => void; setId: string }) {
  const { data: eligibility } = useEligibility(true);
  const add = useAddBinding(setId);
  const [tableName, setTableName] = useState('');
  const [columnName, setColumnName] = useState('');
  const tables = useMemo(() => {
    const m = new Map<string, string>();
    (eligibility ?? []).forEach((e) => m.set(e.table_name, e.table_label));
    return Array.from(m.entries()).map(([table_name, table_label]) => ({ table_name, table_label }));
  }, [eligibility]);
  const columns = (eligibility ?? []).filter((e) => e.table_name === tableName && !e.is_bound);

  async function submit() {
    await add.mutateAsync({ table_name: tableName, column_name: columnName });
    onOpenChange(false);
    setTableName(''); setColumnName('');
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader><DialogTitle>Add binding</DialogTitle></DialogHeader>
        <div className="space-y-3">
          <div><Label>Table</Label>
            <Select value={tableName} onValueChange={(v) => { setTableName(v); setColumnName(''); }}>
              <SelectTrigger><SelectValue placeholder="Select table" /></SelectTrigger>
              <SelectContent>
                {tables.map((t) => <SelectItem key={t.table_name} value={t.table_name}>{t.table_label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div><Label>Column</Label>
            <Select value={columnName} onValueChange={setColumnName} disabled={!tableName}>
              <SelectTrigger><SelectValue placeholder="Select column" /></SelectTrigger>
              <SelectContent>
                {columns.map((c) => <SelectItem key={c.column_name} value={c.column_name}>{c.column_label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Cancel</Button>
          <Button onClick={submit} disabled={!tableName || !columnName}>Bind</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
