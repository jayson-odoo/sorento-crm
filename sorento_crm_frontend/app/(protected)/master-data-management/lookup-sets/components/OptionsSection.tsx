'use client';
import { useState } from 'react';
import { Plus, Pencil, Trash2 } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import { useOptions } from '../hooks/useLookupSets';
import { deleteOption } from '../services/lookupSetService';
import OptionFormDialog from './OptionFormDialog';
import type { LookupOption } from '../types/lookup.types';

export default function OptionsSection({ setId }: { setId: string }) {
  const { data: options, isLoading } = useOptions(setId);
  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<LookupOption | null>(null);
  const [deleting, setDeleting] = useState<LookupOption | null>(null);

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>Options</CardTitle>
        <Button onClick={() => { setEditing(null); setFormOpen(true); }}>
          <Plus className="size-4" /> Add option
        </Button>
      </CardHeader>
      <CardContent>
        {isLoading ? <div>Loading…</div> :
          (options ?? []).length === 0 ? (
            <div className="py-6 text-muted-foreground text-sm">
              No options yet. Click &quot;Add option&quot; to populate this dropdown.
            </div>
          ) : (
            <table className="table-fixed w-full text-sm">
              <thead>
                <tr className="text-left border-b">
                  <th className="px-3 py-2 w-48">Value</th>
                  <th className="px-3 py-2">Label</th>
                  <th className="px-3 py-2 w-20">Sort</th>
                  <th className="px-3 py-2 w-20">Active</th>
                  <th className="px-3 py-2 w-24">Keywords</th>
                  <th className="px-3 py-2 w-28 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {options!.map((o) => (
                  <tr key={o.id} className="border-b">
                    <td className="px-3 py-2 font-mono">{o.value}</td>
                    <td className="px-3 py-2">{o.label}</td>
                    <td className="px-3 py-2">{o.sort_order}</td>
                    <td className="px-3 py-2">{o.is_active ? 'Yes' : 'No'}</td>
                    <td className="px-3 py-2">{o.keywords.length}</td>
                    <td className="px-3 py-2 text-right">
                      <Button size="icon" variant="ghost"
                              onClick={() => { setEditing(o); setFormOpen(true); }}>
                        <Pencil className="size-4" />
                      </Button>
                      <Button size="icon" variant="ghost" onClick={() => setDeleting(o)}>
                        <Trash2 className="size-4" />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
      </CardContent>
      <OptionFormDialog open={formOpen} onOpenChange={setFormOpen} setId={setId} editing={editing} />
      {deleting && (
        <ConfirmDeleteDialog
          open={!!deleting}
          onOpenChange={(o) => { if (!o) setDeleting(null); }}
          title="Delete option?"
          description={`This will permanently delete "${deleting.label}". This action cannot be undone.`}
          onDelete={() => deleteOption(setId, deleting.id)}
          queryKeysToInvalidate={[['lookup-sets', setId, 'options']]}
          onSuccess={() => setDeleting(null)}
        />
      )}
    </Card>
  );
}
