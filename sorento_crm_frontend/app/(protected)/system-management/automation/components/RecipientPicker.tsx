'use client';

import { useEffect, useState, type ReactNode } from 'react';
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

interface Addresses {
  userIds: string[];
  roleIds: string[];
  emails: string[];
}

interface AddressFieldsProps {
  title: 'To' | 'Cc';
  users: UserSelectItem[];
  roles: RoleItem[];
  value: Addresses;
  onChange: (next: Addresses) => void;
  children?: ReactNode;
}

function toggle(list: string[], id: string): string[] {
  return list.includes(id) ? list.filter((x) => x !== id) : [...list, id];
}

/** One recipient line of the email (To or Cc): users, roles and typed addresses. */
function AddressFields({ title, users, roles, value, onChange, children }: AddressFieldsProps) {
  const [emailDraft, setEmailDraft] = useState('');
  const headingId = `rp-${title.toLowerCase()}-heading`;
  const selectedUsers = users.filter((u) => value.userIds.includes(u.id));
  const selectedRoles = roles.filter((r) => value.roleIds.includes(r.id));

  function addEmail() {
    const email = emailDraft.trim();
    if (!email) return;
    if (!value.emails.includes(email)) onChange({ ...value, emails: [...value.emails, email] });
    setEmailDraft('');
  }

  return (
    <div role="group" aria-labelledby={headingId} className="space-y-3 rounded-md border p-3">
      <p id={headingId} className="text-sm font-semibold">
        {title}
      </p>

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
                  checked={value.userIds.includes(u.id)}
                  onCheckedChange={() => onChange({ ...value, userIds: toggle(value.userIds, u.id) })}
                />
                <span className="text-sm truncate" title={`${u.name || u.email} ${u.email}`}>
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
                  checked={value.roleIds.includes(r.id)}
                  onCheckedChange={() => onChange({ ...value, roleIds: toggle(value.roleIds, r.id) })}
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

      {children}

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
        {value.emails.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-1">
            {value.emails.map((e) => (
              <Badge key={e} variant="secondary" className="gap-1 max-w-full">
                <span className="truncate" title={e}>
                  {e}
                </span>
                <button
                  type="button"
                  onClick={() => onChange({ ...value, emails: value.emails.filter((x) => x !== e) })}
                  aria-label={`Remove ${e}`}
                >
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

export default function RecipientPicker({ value, onChange }: Props) {
  const [users, setUsers] = useState<UserSelectItem[]>([]);
  const [roles, setRoles] = useState<RoleItem[]>([]);

  useEffect(() => {
    void getUsersSelect({ status: 'ACTIVE' }).then(setUsers).catch(() => setUsers([]));
    void apiFetch('/api/v1/user-management/roles/select')
      .then((r) => (r.ok ? r.json() : []))
      .then((data: RoleItem[]) => setRoles(data ?? []))
      .catch(() => setRoles([]));
  }, []);

  const to: Addresses = {
    userIds: value.user_ids,
    roleIds: value.role_ids,
    emails: value.extra_emails,
  };
  const cc: Addresses = {
    userIds: value.cc_user_ids ?? [],
    roleIds: value.cc_role_ids ?? [],
    emails: value.cc_emails ?? [],
  };

  return (
    <div className="space-y-3">
      <AddressFields
        title="To"
        users={users}
        roles={roles}
        value={to}
        onChange={(next) =>
          onChange({
            ...value,
            user_ids: next.userIds,
            role_ids: next.roleIds,
            extra_emails: next.emails,
          })
        }
      >
        <div className="flex items-center gap-2">
          <Checkbox
            id="rp-owner"
            checked={value.include_promotion_owner}
            onCheckedChange={(c) => onChange({ ...value, include_promotion_owner: Boolean(c) })}
          />
          <Label htmlFor="rp-owner">Include promotion creator / owner</Label>
        </div>

        <div className="flex items-center gap-2">
          <Checkbox
            id="rp-cs-pic"
            checked={Boolean(value.include_assigned_cs_pic)}
            onCheckedChange={(c) => onChange({ ...value, include_assigned_cs_pic: Boolean(c) })}
          />
          <Label htmlFor="rp-cs-pic">
            Include assigned CS PIC (purchase request / sponsorship form)
          </Label>
        </div>
      </AddressFields>

      <AddressFields
        title="Cc"
        users={users}
        roles={roles}
        value={cc}
        onChange={(next) =>
          onChange({
            ...value,
            cc_user_ids: next.userIds,
            cc_role_ids: next.roleIds,
            cc_emails: next.emails,
          })
        }
      >
        <div className="flex items-center gap-2">
          <Checkbox
            id="rp-actor"
            checked={Boolean(value.include_actor)}
            onCheckedChange={(c) => onChange({ ...value, include_actor: Boolean(c) })}
          />
          <Label htmlFor="rp-actor">Cc the person who raised it</Label>
        </div>

        <div className="flex items-center gap-2">
          <Checkbox
            id="rp-raiser"
            checked={Boolean(value.include_raiser)}
            onCheckedChange={(c) => onChange({ ...value, include_raiser: Boolean(c) })}
          />
          <Label htmlFor="rp-raiser">Cc the person who raised the inquiry</Label>
        </div>

        <div className="flex items-center gap-2">
          <Checkbox
            id="rp-requester"
            checked={Boolean(value.include_requester)}
            onCheckedChange={(c) => onChange({ ...value, include_requester: Boolean(c) })}
          />
          <Label htmlFor="rp-requester">Cc the person who requested</Label>
        </div>
      </AddressFields>

      <div className="flex items-center gap-2">
        <Checkbox
          id="rp-one-email"
          checked={Boolean(value.one_email)}
          onCheckedChange={(c) => onChange({ ...value, one_email: Boolean(c) })}
        />
        <Label htmlFor="rp-one-email">One email, everyone on the thread</Label>
      </div>
    </div>
  );
}
