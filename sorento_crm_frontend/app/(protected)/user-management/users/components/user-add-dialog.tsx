'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import {
  Dialog,
  DialogBody,
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
import { Button, ButtonArrow } from '@/components/ui/button';
import { LoaderCircleIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import { UserRole } from '@/app/models/user';
import { useRoleSelectQuery } from '../../roles/hooks/use-role-select-query';
import { UserAddSchema, UserAddSchemaType } from '../forms/user-add-schema';

const UserAddDialog = ({
  open,
  closeDialog,
}: {
  open: boolean;
  closeDialog: () => void;
}) => {
  const queryClient = useQueryClient();
  const [sendInvitationEmail, setSendInvitationEmail] = useState(true);
  const [superiorOpen, setSuperiorOpen] = useState(false);

  // Fetch available roles
  const { data: roleList } = useRoleSelectQuery();

  const form = useForm<UserAddSchemaType>({
    resolver: zodResolver(UserAddSchema),
    defaultValues: {
      name: '',
      email: '',
      contact_number: '',
      roleIds: [],
      superior_id: null,
    },
    mode: 'onSubmit',
  });

  useEffect(() => {
    if (open) {
      form.reset();
      setSendInvitationEmail(true);
    }
  }, [open, form]);

  const { data: superiorUsers } = useQuery({
    queryKey: ['users-select', 'active'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/users/select?status=ACTIVE');
      if (!response.ok) {
        throw new Error('Failed to fetch users.');
      }
      return response.json();
    },
    enabled: open,
    staleTime: 1000 * 60 * 5,
  });

  const mutation = useMutation({
    mutationFn: async (values: UserAddSchemaType) => {
      const { roleIds, superior_id, ...rest } = values;
      const contactNumber = typeof rest.contact_number === 'string' ? rest.contact_number.trim() : null;
      const payload = {
        ...rest,
        contact_number: contactNumber || null,
        role_ids: roleIds,
        superior_id: superior_id === '__none__' || superior_id === '' ? null : superior_id,
      };
      const inviteUrl = '/api/user-management/users/invite';
      const createUrl = '/api/user-management/users';
      const response = await apiFetch(sendInvitationEmail ? inviteUrl : createUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data.detail ?? data.message ?? 'Request failed');
      }

      const userData = await response.json();
      return { ...userData, _invited: sendInvitationEmail };
    },
    onSuccess: (data) => {
      const message = data._invited
        ? `Invitation sent to ${data.email}. They can set their password using the link in the email.`
        : 'User added successfully';
      toast.custom(
        () => (
          <Alert variant="mono" icon="success" close={false}>
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

      queryClient.invalidateQueries({ queryKey: ['user-users'] });
      closeDialog();
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive" close={false}>
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

  const handleSubmit = (values: UserAddSchemaType) => {
    mutation.mutate(values);
  };

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add User</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)}>
            <DialogBody className="pt-2.5 space-y-6">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name</FormLabel>
                    <FormControl>
                      <Input placeholder="Enter name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Email</FormLabel>
                    <FormControl>
                      <Input placeholder="Enter user email" {...field} />
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
                        value={field.value ?? ''}
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
                      <div className="flex max-h-48 flex-col gap-2 overflow-y-auto rounded-md border p-3">
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
                name="superior_id"
                render={({ field }) => {
                  const value = field.value || '__none__';
                  const selected = value === '__none__' ? null : (superiorUsers || []).find((u: { id: string }) => u.id === value);
                  const displayLabel = selected ? (selected.name || selected.email) : 'None';
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
                              className="w-full justify-between"
                            >
                              <span className={cn('truncate', (!value || value === '__none__') && 'text-muted-foreground')}>
                                {displayLabel}
                              </span>
                              <ButtonArrow />
                            </Button>
                          </PopoverTrigger>
                          <PopoverContent className="w-(--radix-popper-anchor-width) p-0" align="start">
                            <Command>
                              <CommandInput placeholder="Search by name or email..." />
                              <CommandList>
                                <CommandEmpty>No active user found.</CommandEmpty>
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
                                  {(superiorUsers || []).map((superior: { id: string; name?: string | null; email: string }) => (
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

              <div className="flex items-center space-x-2">
                <Checkbox
                  id="send-invitation"
                  checked={sendInvitationEmail}
                  onCheckedChange={(checked) => setSendInvitationEmail(checked === true)}
                />
                <label
                  htmlFor="send-invitation"
                  className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
                >
                  Send invitation email (they will set their password via the link)
                </label>
              </div>

            </DialogBody>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={!form.formState.isDirty || isProcessing}
              >
                {isProcessing && <LoaderCircleIcon className="animate-spin" />}
                Add user
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>

    </Dialog>
  );
};

export default UserAddDialog;
