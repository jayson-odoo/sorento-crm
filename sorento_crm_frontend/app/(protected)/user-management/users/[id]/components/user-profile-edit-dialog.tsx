'use client';

import { useEffect, useRef, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm, type Resolver } from 'react-hook-form';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import {
  Alert,
  AlertDescription,
  AlertIcon,
  AlertTitle,
} from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button, ButtonArrow } from '@/components/ui/button';
import { LoaderCircleIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { User, UserRole } from '@/app/models/user';
import { useRoleSelectQuery } from '../../../roles/hooks/use-role-select-query';
import { UserStatusProps } from '../../constants/status';
import {
  UserProfileSchema,
  UserProfileSchemaType,
} from '../forms/user-profile-schema';

const UserProfileEditDialog = ({
  open,
  closeDialog,
  user,
}: {
  open: boolean;
  closeDialog: () => void;
  user: User;
}) => {
  // #region agent log
  fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'user-profile-edit-dialog.tsx:60',message:'UserProfileEditDialog component rendered',data:{open,userId:user?.id,hasUser:!!user},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'A'})}).catch(()=>{});
  // #endregion
  const queryClient = useQueryClient();
  const [superiorOpen, setSuperiorOpen] = useState(false);

  // Fetch available roles
  const { data: roleList } = useRoleSelectQuery();

  const { data: userRoles = [] } = useQuery({
    queryKey: ['user-roles', user?.id],
    queryFn: async () => {
      const response = await apiFetch(`/api/user-management/users/${user!.id}/roles`);
      if (!response.ok) throw new Error('Failed to fetch user roles');
      return response.json() as Promise<{ id: string; name: string }[]>;
    },
    enabled: open && !!user?.id,
  });

  const form = useForm<UserProfileSchemaType>({
    resolver: zodResolver(UserProfileSchema) as Resolver<UserProfileSchemaType>,
    defaultValues: {
      name: user?.name || '',
      roleIds: user?.roles?.length ? user.roles.map((r) => r.id) : (user?.roleId ? [user.roleId] : []),
      status: user?.status || '',
      respond_user_id: user?.respondUserId || '',
      contact_number: user?.contactNumber || '',
      tier: user?.tier ?? undefined,
      superior_id: user?.superiorId || '',
    },
    mode: 'onSubmit',
  });

  const lastResetRef = useRef<{ userId: string } | null>(null);
  useEffect(() => {
    if (!open) {
      lastResetRef.current = null;
      return;
    }
    if (!user?.id) return;
    if (lastResetRef.current?.userId === user.id) return;
    lastResetRef.current = { userId: user.id };
    const roleIds = userRoles.length ? userRoles.map((r: { id: string }) => r.id) : (user?.roles?.length ? user.roles.map((r) => r.id) : (user?.roleId ? [user.roleId] : []));
    form.reset({
      name: user.name || '',
      roleIds,
      status: user.status || '',
      respond_user_id: user.respondUserId || '',
      contact_number: user.contactNumber || '',
      tier: user.tier ?? undefined,
      superior_id: user.superiorId || '',
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- form is stable; omit to avoid reset loop
  }, [open, user?.id, user?.name, user?.status, user?.roles, user?.respondUserId, user?.tier, user?.superiorId, userRoles.length]);

  const { data: superiorUsers } = useQuery({
    queryKey: ['users-select'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/users/select');
      if (!response.ok) {
        throw new Error('Failed to fetch users.');
      }
      return response.json();
    },
    staleTime: 1000 * 60 * 5,
  });

  const { data: respondUsers } = useQuery({
    queryKey: ['respond-users'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/users/respond-users');
      if (!response.ok) {
        // If endpoint fails, return empty array (Respond API might not be configured)
        return [];
      }
      return response.json();
    },
    staleTime: 1000 * 60 * 5,
  });

  const mutation = useMutation({
    mutationFn: async (values: UserProfileSchemaType) => {
      const roleIds = values.roleIds?.length ? values.roleIds : [];
      const rolesResponse = await apiFetch(`/api/user-management/users/${user.id}/roles`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_ids: roleIds }),
      });
      if (!rolesResponse.ok) {
        const err = await rolesResponse.json().catch(() => ({}));
        throw new Error((err as { detail?: string }).detail || 'Failed to update roles');
      }

      const profileData: Record<string, unknown> = {
        name: values.name,
        status: values.status,
      };
      profileData.contact_number = values.contact_number?.trim() || null;
      profileData.respond_user_id = values.respond_user_id?.trim() || null;
      profileData.tier = values.tier != null ? (typeof values.tier === 'number' ? values.tier : Number(values.tier)) : null;
      profileData.superior_id = (values.superior_id && values.superior_id !== '__none__' && values.superior_id.trim() !== '')
        ? values.superior_id
        : null;

      const response = await apiFetch(`/api/user-management/users/${user.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(profileData),
      });

      if (!response.ok) {
        const err = await response.json().catch(() => ({}));
        throw new Error((err as { message?: string }).message || 'Failed to update user');
      }

      const updatedUser = await response.json();
      return { success: true, user: updatedUser };
    },
    onSuccess: () => {
      const message = 'User updated successfully';

      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>{message}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );

      // Invalidate and refetch user data to get updated values
      queryClient.invalidateQueries({ queryKey: ['user-users'] });
      queryClient.invalidateQueries({ queryKey: ['user-user', user.id] });
      queryClient.invalidateQueries({ queryKey: ['user-roles', user.id] });
      queryClient.refetchQueries({ queryKey: ['user-user', user.id] });
      closeDialog();
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );
    },
  });

  const respondSyncMutation = useMutation({
    mutationFn: async () => {
      // Get the current respond_user_id from the form
      const respondUserId = form.getValues('respond_user_id');
      const response = await apiFetch(`/api/v1/user-management/users/${user.id}/sync-respond`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ respond_user_id: respondUserId }),
      });

      if (!response.ok) {
        const { message } = await response.json().catch(() => ({ message: 'Failed to sync respond user.' }));
        throw new Error(message);
      }

      return response.json();
    },
    onSuccess: (data) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>{data.message || 'Respond user synced successfully'}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );

      queryClient.invalidateQueries({ queryKey: ['user-user'] });
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message}</AlertTitle>
          </Alert>
        ),
        {
          position: 'top-center',
        },
      );
    },
  });

  const isProcessing = mutation.status === 'pending';
  const isSyncing = respondSyncMutation.status === 'pending';

  const handleSubmit = (values: UserProfileSchemaType) => {
    mutation.mutate(values);
  };

  // Debug: Log when component renders
  useEffect(() => {
    if (open) {
      console.log('🔍 UserProfileEditDialog opened', {
        hasRespondUsers: !!respondUsers,
        respondUsersCount: respondUsers?.length || 0,
        userRespondId: user?.respondUserId
      });
    }
  }, [open, respondUsers, user]);

  // #region agent log
  fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'user-profile-edit-dialog.tsx:261',message:'Rendering dialog JSX',data:{open,formFieldsCount:6},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'B'})}).catch(()=>{});
  // #endregion
  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent className="max-h-[90vh] overflow-hidden flex flex-col">
        <DialogHeader className="shrink-0">
          <DialogTitle>Edit User Details</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form
            onSubmit={form.handleSubmit(handleSubmit)}
            className="flex flex-1 min-h-0 flex-col overflow-hidden"
          >
            <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden pr-1 space-y-6">
            {mutation.status === 'error' && (
              <Alert variant="destructive">
                <AlertDescription>{mutation.error.message}</AlertDescription>
              </Alert>
            )}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Enter user name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="contact_number"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Contact Number</FormLabel>
                  <FormControl>
                    <Input
                      placeholder="Enter contact number"
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="roleIds"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Roles</FormLabel>
                  <FormControl>
                    <div className="flex flex-col gap-2 rounded-md border p-3">
                      {(roleList ?? []).map((role: UserRole) => (
                        <div
                          key={role.id}
                          className="flex flex-row items-center space-x-2"
                        >
                          <Checkbox
                            id={`role-${role.id}`}
                            checked={field.value?.includes(role.id)}
                            onCheckedChange={(checked) => {
                              const next = checked
                                ? [...(field.value ?? []), role.id]
                                : (field.value ?? []).filter((id) => id !== role.id);
                              field.onChange(next);
                            }}
                          />
                          <label
                            htmlFor={`role-${role.id}`}
                            className="font-normal cursor-pointer text-sm"
                          >
                            {role.name}
                          </label>
                        </div>
                      ))}
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="status"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Status</FormLabel>
                  <FormControl>
                    <Select
                      onValueChange={(value) => field.onChange(value)}
                      value={field.value || ''}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="Select a status" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectGroup>
                          {Object.entries(UserStatusProps).map(
                            ([status, { label }]) => (
                              <SelectItem key={status} value={status}>
                                {label}
                              </SelectItem>
                            ),
                          )}
                        </SelectGroup>
                      </SelectContent>
                    </Select>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            {/* RESPOND USER ID FIELD - ADDED */}
            <FormField
              control={form.control}
              name="respond_user_id"
              render={({ field }) => {
                // #region agent log
                fetch('http://127.0.0.1:7242/ingest/82ff2983-30f8-41d1-a335-d37b94435673',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({location:'user-profile-edit-dialog.tsx:350',message:'Respond User ID field rendering',data:{fieldValue:field.value,hasField:!!field},timestamp:Date.now(),sessionId:'debug-session',runId:'run1',hypothesisId:'C'})}).catch(()=>{});
                // #endregion
                return (
                <FormItem>
                  <FormLabel className="text-lg font-semibold">Respond User ID</FormLabel>
                  <FormControl>
                    <div className="space-y-2">
                      <Input 
                        placeholder="Enter Respond user ID (e.g., user_123)" 
                        {...field} 
                        value={field.value || ''} 
                        className="border-2"
                      />
                      {field.value && (
                        <div className="flex flex-wrap items-center gap-2 mt-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => respondSyncMutation.mutate()}
                            disabled={isSyncing}
                          >
                            {isSyncing && <LoaderCircleIcon className="animate-spin mr-2 h-4 w-4" />}
                            Sync Respond User
                          </Button>
                        </div>
                      )}
                    </div>
                  </FormControl>
                  <FormMessage />
                </FormItem>
              );
              }}
            />
            <FormField
              control={form.control}
              name="tier"
              render={({ field }) => (
                <FormItem>
                  <FormLabel className="text-lg font-semibold">Tier</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      min={1}
                      step={1}
                      placeholder="Conversation SLA policy tier (e.g. 1, 2)"
                      {...field}
                      value={field.value ?? ''}
                      onChange={(e) => {
                        const v = e.target.value;
                        field.onChange(v === '' ? undefined : (Number(v) || undefined));
                      }}
                      className="border-2"
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="superior_id"
              render={({ field }) => {
                const value = field.value || '__none__';
                const selected = value === '__none__' ? null : (superiorUsers || []).find((u: { id: string }) => u.id === value);
                const displayLabel = selected ? (selected.name || selected.email) : 'None';
                const filteredSuperiors = (superiorUsers || []).filter((s: { id: string }) => s.id !== user.id);
                return (
                  <FormItem>
                    <FormLabel>Superior</FormLabel>
                    <FormControl>
                      <Popover open={superiorOpen} onOpenChange={setSuperiorOpen}>
                        <PopoverTrigger asChild>
                          <Button
                            type="button"
                            variant="outline"
                            role="combobox"
                            mode="input"
                            placeholder={!value || value === '__none__'}
                            aria-expanded={superiorOpen}
                            className={cn('w-full justify-between font-normal')}
                          >
                            <span className={cn('truncate', (!value || value === '__none__') && 'text-muted-foreground')}>
                              {displayLabel}
                            </span>
                            <ButtonArrow />
                          </Button>
                        </PopoverTrigger>
                        <PopoverContent className="w-(--radix-popper-anchor-width) max-h-[min(320px,80vh)] flex flex-col p-0" align="start">
                          <Command className="max-h-full min-h-0 flex flex-col">
                            <CommandInput placeholder="Search by name or email..." />
                            <CommandList className="max-h-[240px] min-h-0 overflow-y-auto overflow-x-hidden">
                              <CommandEmpty>No user found.</CommandEmpty>
                              <CommandGroup>
                                <CommandItem
                                  value="__none__"
                                  onSelect={() => {
                                    field.onChange(null);
                                    setSuperiorOpen(false);
                                  }}
                                >
                                  None
                                </CommandItem>
                                {filteredSuperiors.map((superior: { id: string; name?: string | null; email: string }) => (
                                  <CommandItem
                                    key={superior.id}
                                    value={`${superior.name ?? ''} ${superior.email}`.trim() || superior.id}
                                    onSelect={() => {
                                      field.onChange(superior.id);
                                      setSuperiorOpen(false);
                                    }}
                                  >
                                    {superior.name || superior.email}
                                  </CommandItem>
                                ))}
                              </CommandGroup>
                            </CommandList>
                          </Command>
                        </PopoverContent>
                      </Popover>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                );
              }}
            />
            </div>
            <DialogFooter className="shrink-0">
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!form.formState.isDirty || isProcessing}
              >
                {isProcessing && <LoaderCircleIcon className="animate-spin" />}
                Save Changes
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
};

export default UserProfileEditDialog;
