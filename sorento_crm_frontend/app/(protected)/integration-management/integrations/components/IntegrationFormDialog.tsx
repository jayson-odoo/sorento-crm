'use client';

import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { getUsersSelect } from '@/services/userSelectService';

import { useCreateIntegration, useUpdateIntegration } from '../hooks/useIntegrations';
import type { Integration } from '../types/integration.types';

const TYPE_OPTIONS = [
  { value: 'autocount_esb', label: 'AutoCount ESB' },
  { value: 'automation', label: 'Automation (n8n)' },
  { value: 'mcp', label: 'MCP server' },
  { value: 'legacy', label: 'Legacy shared key' },
  { value: 'other', label: 'Other' },
];

export function IntegrationFormDialog({
  open,
  onOpenChange,
  integration,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  integration?: Integration | null;
}) {
  const isEdit = !!integration;
  const create = useCreateIntegration();
  const update = useUpdateIntegration();

  const [name, setName] = useState('');
  const [type, setType] = useState('autocount_esb');
  const [actAsUserId, setActAsUserId] = useState<string | null>(null);
  const [isActive, setIsActive] = useState(true);

  // This SearchableSelect is static-options only, so the roster is fetched
  // once and filtered client-side rather than searched server-side.
  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ['users-select', 'integration-principal'],
    queryFn: () => getUsersSelect({ status: 'ACTIVE' }),
    enabled: open,
  });
  const userOptions = useMemo(
    () =>
      (users ?? []).map((u) => ({
        value: u.id,
        label: u.name || u.email,
        description: u.name ? u.email : undefined,
        searchText: `${u.name ?? ''} ${u.email}`,
      })),
    [users],
  );

  useEffect(() => {
    if (!open) return;
    setName(integration?.name ?? '');
    setType(integration?.type ?? 'autocount_esb');
    setActAsUserId(integration?.act_as_user_id ?? null);
    setIsActive(integration?.is_active ?? true);
  }, [open, integration]);

  const submit = async () => {
    if (isEdit && integration) {
      // credentials_json is deliberately not sent: omitting it means "keep the
      // existing credential". Sending an empty object here would silently wipe
      // it, which reads to an operator as an outage rather than an edit.
      await update.mutateAsync({
        id: integration.id,
        payload: { name, type, act_as_user_id: actAsUserId, is_active: isActive },
      });
    } else {
      await create.mutateAsync({
        name,
        type,
        act_as_user_id: actAsUserId,
        is_active: isActive,
      });
    }
    onOpenChange(false);
  };

  const busy = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* max-h + overflow so the submit button stays reachable at phone width */}
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Edit integration' : 'Add integration'}</DialogTitle>
          <DialogDescription>
            An integration acts as a user, so what it can reach is controlled by that
            user&apos;s role.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="integration-name">Name</Label>
            <Input
              id="integration-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="foundryx-esb"
            />
          </div>

          <div className="space-y-2">
            <Label>Type</Label>
            <SearchableSelect
              options={TYPE_OPTIONS}
              value={type}
              onChange={setType}
              placeholder="Select a type"
            />
          </div>

          <div className="space-y-2">
            <Label>Acts as user</Label>
            <SearchableSelect
              options={userOptions}
              value={actAsUserId ?? ''}
              onChange={(v) => setActAsUserId(v || null)}
              placeholder={usersLoading ? 'Loading users…' : 'Select the principal'}
              disabled={usersLoading}
            />
            <p className="text-xs text-muted-foreground">
              Every record this integration writes is attributed to this user, and its
              role decides what the integration may reach.
            </p>
          </div>

          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <Label htmlFor="integration-active">Active</Label>
              <p className="text-xs text-muted-foreground">
                Inactive integrations are refused even with a valid key.
              </p>
            </div>
            <Switch
              id="integration-active"
              checked={isActive}
              onCheckedChange={setIsActive}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={busy}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={busy || !name.trim()}>
            {isEdit ? 'Save' : 'Create'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
