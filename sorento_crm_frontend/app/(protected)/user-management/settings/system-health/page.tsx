'use client';

import { useMemo, useState } from 'react';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { LoaderCircleIcon, UserPlus } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { getUsersSelect } from '@/services/userSelectService';
import { extractApiError } from '@/lib/api-client';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Command,
  CommandCheck,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Switch } from '@/components/ui/switch';
import { useSettings } from '../components/settings-context';

/** Clamp a free-text number field to a non-negative integer. */
function toNonNegativeInt(raw: string, fallback: number): number {
  const n = parseInt(raw, 10);
  if (Number.isNaN(n) || n < 0) return fallback;
  return n;
}

const SystemHealthSettingsPage = () => {
  const queryClient = useQueryClient();
  const { settings, roles } = useSettings();

  const initialRoleIds = useMemo(
    () => settings.healthNotifyRoleIds ?? [],
    [settings.healthNotifyRoleIds],
  );
  const initialUserIds = useMemo(
    () => settings.healthNotifyUserIds ?? [],
    [settings.healthNotifyUserIds],
  );

  const { data: users } = useQuery({
    queryKey: ['health-notify-user-select'],
    queryFn: () => getUsersSelect(),
    staleTime: 5 * 60 * 1000,
  });

  const [digestEnabled, setDigestEnabled] = useState<boolean>(settings.healthDigestEnabled);
  const [alertsEnabled, setAlertsEnabled] = useState<boolean>(settings.healthAlertsEnabled);
  const [roleIds, setRoleIds] = useState<string[]>([...initialRoleIds]);
  const [userIds, setUserIds] = useState<string[]>([...initialUserIds]);
  const [failThreshold, setFailThreshold] = useState<string>(
    String(settings.healthIntegrationFailThreshold ?? 10),
  );
  const [auditFloor, setAuditFloor] = useState<string>(
    String(settings.healthAuditVolumeFloor ?? 0),
  );

  const toggleRole = (roleId: string) => {
    setRoleIds((prev) =>
      prev.includes(roleId) ? prev.filter((id) => id !== roleId) : [...prev, roleId],
    );
  };

  const toggleUser = (userId: string) => {
    setUserIds((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId],
    );
  };

  const mutation = useMutation({
    mutationFn: async () => {
      // apiFetch maps /api/... straight to the FastAPI backend; POST /general
      // setattrs any provided snake_case column.
      const response = await apiFetch('/api/user-management/settings/general', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          health_digest_enabled: digestEnabled,
          health_alerts_enabled: alertsEnabled,
          health_notify_role_ids: roleIds,
          health_notify_user_ids: userIds,
          health_integration_fail_threshold: toNonNegativeInt(
            failThreshold,
            settings.healthIntegrationFailThreshold ?? 10,
          ),
          health_audit_volume_floor: toNonNegativeInt(
            auditFloor,
            settings.healthAuditVolumeFloor ?? 0,
          ),
        }),
      });
      if (!response.ok) {
        throw new Error(await extractApiError(response, 'Failed to save'));
      }
      return response.json();
    },
    onSuccess: () => {
      toast('success', 'System health settings updated');
      queryClient.invalidateQueries({ queryKey: ['system-settings'] });
    },
    onError: (error: Error) => toast('destructive', error.message),
  });

  const isProcessing = mutation.status === 'pending';

  const handleReset = () => {
    setDigestEnabled(settings.healthDigestEnabled);
    setAlertsEnabled(settings.healthAlertsEnabled);
    setRoleIds([...initialRoleIds]);
    setUserIds([...initialUserIds]);
    setFailThreshold(String(settings.healthIntegrationFailThreshold ?? 10));
    setAuditFloor(String(settings.healthAuditVolumeFloor ?? 0));
  };

  const noRecipients =
    (digestEnabled || alertsEnabled) && roleIds.length === 0 && userIds.length === 0;

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <CardTitle>System Health Settings</CardTitle>
      </CardHeader>
      <CardContent className="space-y-6 py-5">
        {/* Digest toggle */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="text-md font-semibold">Daily health digest</div>
            <div className="text-muted-foreground text-2sm">
              Send a once-daily in-app and email summary of email queue, imports,
              scheduled tasks, integrations and audit activity to the notify roles.
            </div>
          </div>
          <Switch
            data-testid="health-digest-enabled"
            checked={digestEnabled}
            onCheckedChange={setDigestEnabled}
          />
        </div>

        {/* Alerts toggle */}
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <div className="text-md font-semibold">Immediate anomaly alerts</div>
            <div className="text-muted-foreground text-2sm">
              Alert off-cycle the moment a watchdog condition trips (n8n liveness
              failure, a scheduled task failing or running overdue, or an
              integration failure spike).
            </div>
          </div>
          <Switch
            data-testid="health-alerts-enabled"
            checked={alertsEnabled}
            onCheckedChange={setAlertsEnabled}
          />
        </div>

        {/* Notify roles */}
        <div className="space-y-2">
          <div className="space-y-1">
            <div className="text-md font-semibold">Notify roles</div>
            <div className="text-muted-foreground text-2sm">
              Members of these roles receive the digest and alerts.
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" mode="icon" className="h-7! w-7!">
                  <UserPlus className="size-3.5!" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[220px] p-0" align="start" side="bottom">
                <Command>
                  <CommandInput placeholder="Search roles..." />
                  <CommandList>
                    <CommandEmpty>No roles found.</CommandEmpty>
                    <CommandGroup>
                      <ScrollArea>
                        {roles?.map((role) => {
                          const isSelected = roleIds.includes(role.id);
                          return (
                            <CommandItem
                              key={role.id}
                              onSelect={() => toggleRole(role.id)}
                            >
                              <span className="grow">{role.name}</span>
                              {isSelected && <CommandCheck />}
                            </CommandItem>
                          );
                        })}
                      </ScrollArea>
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            <div className="flex flex-wrap items-center gap-2">
              {roleIds.length > 0 ? (
                roleIds.map((roleId) => {
                  const role = roles.find((r) => r.id === roleId);
                  return (
                    <Badge key={roleId} variant="secondary">
                      {role?.name ?? 'Unknown role'}
                    </Badge>
                  );
                })
              ) : (
                <span className="text-muted-foreground text-sm">Not set</span>
              )}
            </div>
          </div>
        </div>

        {/* Notify individual users */}
        <div className="space-y-2">
          <div className="space-y-1">
            <div className="text-md font-semibold">Notify users</div>
            <div className="text-muted-foreground text-2sm">
              Individual users who receive the digest and alerts, in addition to
              members of the notify roles above.
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Popover>
              <PopoverTrigger asChild>
                <Button variant="outline" mode="icon" className="h-7! w-7!">
                  <UserPlus className="size-3.5!" />
                </Button>
              </PopoverTrigger>
              <PopoverContent className="w-[260px] p-0" align="start" side="bottom">
                <Command>
                  <CommandInput placeholder="Search users..." />
                  <CommandList>
                    <CommandEmpty>No users found.</CommandEmpty>
                    <CommandGroup>
                      <ScrollArea>
                        {users?.map((user) => {
                          const isSelected = userIds.includes(user.id);
                          return (
                            <CommandItem
                              key={user.id}
                              value={`${user.name ?? ''} ${user.email}`}
                              onSelect={() => toggleUser(user.id)}
                            >
                              <span className="grow truncate">{user.name || user.email}</span>
                              {isSelected && <CommandCheck />}
                            </CommandItem>
                          );
                        })}
                      </ScrollArea>
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
            <div className="flex flex-wrap items-center gap-2">
              {userIds.length > 0 ? (
                userIds.map((userId) => {
                  const user = users?.find((u) => u.id === userId);
                  return (
                    <Badge key={userId} variant="secondary">
                      {user ? user.name || user.email : 'Selected user'}
                    </Badge>
                  );
                })
              ) : (
                <span className="text-muted-foreground text-sm">Not set</span>
              )}
            </div>
          </div>
        </div>

        {noRecipients && (
          <Alert variant="mono" icon="warning">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>
              No roles or users selected — the digest and alerts fall back to superadmin and admin users.
            </AlertTitle>
          </Alert>
        )}

        {/* Thresholds */}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="health-fail-threshold">Integration failure alert threshold</Label>
            <Input
              id="health-fail-threshold"
              data-testid="health-integration-fail-threshold"
              type="number"
              min={0}
              value={failThreshold}
              onChange={(e) => setFailThreshold(e.target.value)}
            />
            <div className="text-muted-foreground text-2sm">
              Failed integration logs on a single channel within the window that
              trip an immediate alert.
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="health-audit-floor">Daily audit volume floor</Label>
            <Input
              id="health-audit-floor"
              data-testid="health-audit-volume-floor"
              type="number"
              min={0}
              value={auditFloor}
              onChange={(e) => setAuditFloor(e.target.value)}
            />
            <div className="text-muted-foreground text-2sm">
              Warn in the daily digest when audit events fall below this count. Set
              to 0 to disable the low-volume check.
            </div>
          </div>
        </div>
      </CardContent>
      <CardFooter className="flex justify-end gap-4 py-5 px-10">
        <Button type="button" variant="outline" onClick={handleReset}>
          Reset
        </Button>
        <Button type="button" onClick={() => mutation.mutate()} disabled={isProcessing}>
          {isProcessing && <LoaderCircleIcon className="animate-spin" />}
          Save Settings
        </Button>
      </CardFooter>
    </Card>
  );
};

function toast(icon: 'success' | 'destructive', title: string) {
  // Lazy import to keep parity with the rest of the settings pages.
  import('sonner').then(({ toast: sonner }) =>
    sonner.custom(
      () => (
        <Alert variant="mono" icon={icon}>
          <AlertIcon>
            {icon === 'success' ? <RiCheckboxCircleFill /> : <RiErrorWarningFill />}
          </AlertIcon>
          <AlertTitle>{title}</AlertTitle>
        </Alert>
      ),
      { position: 'top-center' },
    ),
  );
}

export default SystemHealthSettingsPage;
