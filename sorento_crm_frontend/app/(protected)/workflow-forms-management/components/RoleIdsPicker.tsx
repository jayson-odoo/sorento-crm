'use client';

import { useRoleSelectQuery } from '@/app/(protected)/user-management/roles/hooks/use-role-select-query';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { ScrollArea } from '@/components/ui/scroll-area';

type RoleRow = { id: string; name?: string; slug?: string };

export default function RoleIdsPicker({
  value,
  onChange,
  label,
}: {
  value: string[];
  onChange: (ids: string[]) => void;
  label?: string;
}) {
  const { data, isLoading } = useRoleSelectQuery();
  const roles: RoleRow[] = Array.isArray(data) ? data : (data as { data?: RoleRow[] })?.data ?? [];

  const toggle = (id: string, checked: boolean) => {
    if (checked) onChange(Array.from(new Set([...value, id])));
    else onChange(value.filter((x) => x !== id));
  };

  return (
    <div className="space-y-2">
      {label ? <Label className="text-xs text-muted-foreground">{label}</Label> : null}
      {isLoading ? (
        <p className="text-sm text-muted-foreground">Loading roles…</p>
      ) : (
        <ScrollArea className="h-36 rounded-md border p-2">
          <div className="flex flex-col gap-2">
            {roles.map((r) => (
              <div key={r.id} className="flex items-center gap-2">
                <Checkbox
                  id={`role-${r.id}`}
                  checked={value.includes(r.id)}
                  onCheckedChange={(c) => toggle(r.id, c === true)}
                />
                <Label htmlFor={`role-${r.id}`} className="text-sm font-normal cursor-pointer">
                  {r.name || r.slug || r.id}
                </Label>
              </div>
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  );
}
