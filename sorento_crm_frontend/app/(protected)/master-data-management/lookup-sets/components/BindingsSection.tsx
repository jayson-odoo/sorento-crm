'use client';
import { useState } from 'react';
import { Plus, Trash2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useBindings } from '../hooks/useLookupSets';
import { removeBinding } from '../services/lookupSetService';
import BindingAddDialog from './BindingAddDialog';
import type { LookupBinding } from '../types/lookup.types';

export default function BindingsSection({ setId }: { setId: string }) {
  const { data: bindings, isLoading } = useBindings(setId);
  const [addOpen, setAddOpen] = useState(false);
  const [deleting, setDeleting] = useState<LookupBinding | null>(null);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Bindings</CardTitle>
        <Button onClick={() => setAddOpen(true)}><Plus className="size-4" /> Add binding</Button>
      </CardHeader>
      <CardContent>
        {isLoading ? <div>Loading…</div> :
          (bindings ?? []).length === 0 ? (
            <div className="py-6 text-muted-foreground text-sm">
              Not yet bound to any field. Click &quot;Add binding&quot; to choose where this dropdown appears.
            </div>
          ) : (
            <table className="table-fixed w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="px-3 py-2">Table</th>
                  <th className="px-3 py-2">Column</th>
                  <th className="px-3 py-2 w-24 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {bindings!.map((b) => (
                  <tr key={b.id} className="border-b">
                    <td className="px-3 py-2">{b.table_label ?? b.table_name}</td>
                    <td className="px-3 py-2">{b.column_label ?? b.column_name}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="icon" variant="ghost" onClick={() => setDeleting(b)}>
                        <Trash2 className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>
      <BindingAddDialog open={addOpen} onOpenChange={setAddOpen} setId={setId} />
      {deleting && (
        <ConfirmDeleteDialog
          open={!!deleting}
          onOpenChange={(o) => { if (!o) setDeleting(null); }}
          title="Remove binding?"
          description={`This will unbind ${deleting.table_label ?? deleting.table_name} → ${deleting.column_label ?? deleting.column_name}. Existing data is unaffected.`}
          onDelete={() => removeBinding(setId, deleting.id)}
          queryKeysToInvalidate={[['lookup-sets', setId, 'bindings'], ['lookup-eligibility']]}
          onSuccess={() => setDeleting(null)}
        />
      )}
    </Card>
  );
}
