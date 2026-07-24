'use client';
import { useMemo, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
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
            <SearchableSelect
              value={tableName}
              onChange={(v) => { setTableName(v); setColumnName(''); }}
              placeholder="Select table"
              options={tables.map((t) => ({ value: t.table_name, label: t.table_label }))}
            />
          </div>
          <div><Label>Column</Label>
            <SearchableSelect
              value={columnName}
              onChange={setColumnName}
              disabled={!tableName}
              placeholder="Select column"
              options={columns.map((c) => ({ value: c.column_name, label: c.column_label }))}
            />
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
