'use client';

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { getUsersSelect, type UserSelectItem } from '@/services/userSelectService';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import type { RecipientConfig } from '../types/automation.types';

interface RoleItem {
  id: string;
  name: string;
  slug: string;
}

interface Props {
  value: RecipientConfig;
  onChange: (next: RecipientConfig) => void;
}

export default function RecipientPicker({ value, onChange }: Props) {
  const [users, setUsers] = useState<UserSelectItem[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [emailDraft, setEmailDraft] = useState('');

  useEffect(() => {
    void getUsersSelect({ status: 'ACTIVE' }).then(setUsers).catch(() => setUsers([]));
    void apiFetch('/api/v1/user-management/roles/select')
      .then((r) => (r.ok ? r.json() : []))
      .then((data: RoleItem[]) => setRoles(data ?? []))
      .catch(() => setRoles([]));
  }, []);

  const selectedUsers = users.filter((u) => value.user_ids.includes(u.id));
  const selectedRoles = roles.filter((r) => value.role_ids.includes(r.id));

  function toggleUser(id: string) {
    onChange({
      ...value,
      user_ids: value.user_ids.includes(id)
        ? value.user_ids.filter((x) => x !== id)
        : [...value.user_ids, id],
    });
  }

  function toggleRole(id: string) {
    onChange({
      ...value,
      role_ids: value.role_ids.includes(id)
        ? value.role_ids.filter((x) => x !== id)
        : [...value.role_ids, id],
    });
  }

  function addEmail() {
    const email = emailDraft.trim();
    if (!email) return;
    if (value.extra_emails.includes(email)) {
      setEmailDraft('');
      return;
    }
    onChange({ ...value, extra_emails: [...value.extra_emails, email] });
    setEmailDraft('');
  }

  function removeEmail(email: string) {
    onChange({ ...value, extra_emails: value.extra_emails.filter((e) => e !== email) });
  }

  return (
    <div className="space-y-3 rounded-md border p-3">
      <div className="space-y-1">
        <Label>Specific users</Label>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" type="button">
              {selectedUsers.length ? `${selectedUsers.length} selected` : 'Pick users'}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[320px] max-h-[300px] overflow-y-auto" align="start">
            {users.map((u) => (
              <label
                key={u.id}
                className="flex items-center gap-2 px-2 py-1 hover:bg-muted rounded cursor-pointer"
              >
                <Checkbox
                  checked={value.user_ids.includes(u.id)}
                  onCheckedChange={() => toggleUser(u.id)}
                />
                <span className="text-sm">
                  {u.name || u.email}
                  <span className="text-muted-foreground ml-1">{u.email}</span>
                </span>
              </label>
            ))}
            {users.length === 0 && (
              <p className="text-xs text-muted-foreground p-2">No active users.</p>
            )}
          </PopoverContent>
        </Popover>
        {selectedUsers.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {selectedUsers.map((u) => (
              <Badge key={u.id} variant="secondary">
                {u.name || u.email}
              </Badge>
            ))}
          </div>
        )}
      </div>

      <div className="space-y-1">
        <Label>By role</Label>
        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" size="sm" type="button">
              {selectedRoles.length ? `${selectedRoles.length} role(s)` : 'Pick roles'}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-[320px] max-h-[300px] overflow-y-auto" align="start">
            {roles.map((r) => (
              <label
                key={r.id}
                className="flex items-center gap-2 px-2 py-1 hover:bg-muted rounded cursor-pointer"
              >
                <Checkbox
                  checked={value.role_ids.includes(r.id)}
                  onCheckedChange={() => toggleRole(r.id)}
                />
                <span className="text-sm">{r.name}</span>
              </label>
            ))}
            {roles.length === 0 && (
              <p className="text-xs text-muted-foreground p-2">No roles defined.</p>
            )}
          </PopoverContent>
        </Popover>
        {selectedRoles.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {selectedRoles.map((r) => (
              <Badge key={r.id} variant="secondary">
                {r.name}
              </Badge>
            ))}
          </div>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Checkbox
          id="rp-owner"
          checked={value.include_promotion_owner}
          onCheckedChange={(c) =>
            onChange({ ...value, include_promotion_owner: Boolean(c) })
          }
        />
        <Label htmlFor="rp-owner">Include promotion creator / owner</Label>
      </div>

      <div className="flex items-center gap-2">
        <Checkbox
          id="rp-cs-pic"
          checked={Boolean(value.include_assigned_cs_pic)}
          onCheckedChange={(c) =>
            onChange({ ...value, include_assigned_cs_pic: Boolean(c) })
          }
        />
        <Label htmlFor="rp-cs-pic">
          Include assigned CS PIC (purchase request / sponsorship form)
        </Label>
      </div>

      <div className="space-y-1">
        <Label>External emails</Label>
        <div className="flex gap-2">
          <Input
            value={emailDraft}
            onChange={(e) => setEmailDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                e.preventDefault();
                addEmail();
              }
            }}
            placeholder="someone@example.com"
            type="email"
          />
          <Button type="button" variant="outline" onClick={addEmail}>
            Add
          </Button>
        </div>
        {value.extra_emails.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {value.extra_emails.map((e) => (
              <Badge key={e} variant="secondary" className="gap-1">
                {e}
                <button type="button" onClick={() => removeEmail(e)} aria-label={`Remove ${e}`}>
                  <X className="size-3" />
                </button>
              </Badge>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
