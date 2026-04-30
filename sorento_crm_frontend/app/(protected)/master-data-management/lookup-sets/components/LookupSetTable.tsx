'use client';
import { Eye, Pencil, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { LookupSet } from '../types/lookup.types';

export default function LookupSetTable({
  rows,
  onView,
  onEdit,
  onDelete,
}: {
  rows: LookupSet[];
  onView: (s: LookupSet) => void;
  onEdit: (s: LookupSet) => void;
  onDelete: (s: LookupSet) => void;
}) {
  if (!rows.length) {
    return (
      <div className="py-12 text-center text-muted-foreground">
        No lookup sets yet. Click &quot;Add lookup set&quot; to create one.
      </div>
    );
  }
  return (
    <table className="table-fixed w-full">
      <thead>
        <tr className="text-left text-sm border-b">
          <th className="px-4 py-3 w-48">Set key</th>
          <th className="px-4 py-3">Name</th>
          <th className="px-4 py-3 w-24">Options</th>
          <th className="px-4 py-3 w-24">Bindings</th>
          <th className="px-4 py-3 w-20">Active</th>
          <th className="px-4 py-3 w-32 text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id} className="border-b hover:bg-muted/40">
            <td className="px-4 py-2 font-mono text-sm">{s.set_key}</td>
            <td className="px-4 py-2">{s.name}</td>
            <td className="px-4 py-2">{s.option_count}</td>
            <td className="px-4 py-2">{s.binding_count}</td>
            <td className="px-4 py-2">{s.is_active ? 'Yes' : 'No'}</td>
            <td className="px-4 py-2 text-right">
              <Button size="icon" variant="ghost" onClick={() => onView(s)}>
                <Eye className="size-4" />
              </Button>
              <Button size="icon" variant="ghost" onClick={() => onEdit(s)}>
                <Pencil className="size-4" />
              </Button>
              <Button size="icon" variant="ghost" onClick={() => onDelete(s)}>
                <Trash2 className="size-4" />
              </Button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
