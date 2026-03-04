'use client';

import { useEffect, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { formatDate } from '@/lib/helpers';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
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
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { LoaderCircleIcon, Plus, X } from 'lucide-react';
import { UserRole } from '@/app/models/user';
import { useRoleSelectQuery } from '../../roles/hooks/use-role-select-query';
import { UserAddSchema, UserAddSchemaType } from '../forms/user-add-schema';
import UserAgentAccessDialog from '../[id]/components/UserAgentAccessDialog';

interface AccessAgent {
  id: string;
  code: string;
  name: string;
  description?: string | null;
  is_active: boolean;
}

interface UserAgentAccess {
  agent_id: string;
  agent_name: string;
  is_allowed: boolean;
  valid_from?: Date | null;
  valid_to?: Date | null;
}

const UserAddDialog = ({
  open,
  closeDialog,
}: {
  open: boolean;
  closeDialog: () => void;
}) => {
  const queryClient = useQueryClient();
  const [selectedAgent, setSelectedAgent] = useState<{ id: string; name: string } | null>(null);
  const [accessDialogOpen, setAccessDialogOpen] = useState(false);
  const [userAgentAccesses, setUserAgentAccesses] = useState<UserAgentAccess[]>([]);
  const [sendInvitationEmail, setSendInvitationEmail] = useState(true);

  // Fetch available roles
  const { data: roleList } = useRoleSelectQuery();

  // Fetch available access agents
  const { data: agentsData } = useQuery({
    queryKey: ['access-agents', 'all'],
    queryFn: async () => {
      const response = await apiFetch('/api/user-management/access-agents?page=1&limit=1000');
      if (!response.ok) throw new Error('Failed to fetch access agents');
      return response.json();
    },
    enabled: open,
  });

  const form = useForm<UserAddSchemaType>({
    resolver: zodResolver(UserAddSchema),
    defaultValues: {
      name: '',
      email: '',
      roleId: '',
      superior_id: null,
    },
    mode: 'onSubmit',
  });

  useEffect(() => {
    if (open) {
      form.reset();
      setUserAgentAccesses([]);
      setSelectedAgent(null);
      setAccessDialogOpen(false);
      setSendInvitationEmail(true);
    }
  }, [open, form]);

  const handleAddAgentClick = (agent: AccessAgent) => {
    setSelectedAgent({ id: agent.id, name: agent.name });
    setAccessDialogOpen(true);
  };

  const handleAccessAgentSubmit = (data: {
    agent_id: string;
    is_allowed: boolean;
    valid_from?: Date | null;
    valid_to?: Date | null;
  }) => {
    if (selectedAgent) {
      setUserAgentAccesses([
        ...userAgentAccesses,
        {
          agent_id: data.agent_id,
          agent_name: selectedAgent.name,
          is_allowed: data.is_allowed,
          valid_from: data.valid_from,
          valid_to: data.valid_to,
        },
      ]);
      setAccessDialogOpen(false);
      setSelectedAgent(null);
    }
  };

  const handleRemoveAgent = (agentId: string) => {
    setUserAgentAccesses(userAgentAccesses.filter((ua) => ua.agent_id !== agentId));
  };

  const agents = agentsData?.data || [];
  const assignedAgentIds = userAgentAccesses.map((ua) => ua.agent_id);
  const availableAgents = agents.filter((agent: AccessAgent) => !assignedAgentIds.includes(agent.id));

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

  const mutation = useMutation({
    mutationFn: async (values: UserAddSchemaType) => {
      const { agent_ids, roleId, superior_id, ...rest } = values;
      const payload = {
        ...rest,
        role_ids: roleId ? [roleId] : undefined,
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
      const userId = userData.id;

      if (userAgentAccesses.length > 0) {
        for (const access of userAgentAccesses) {
          await apiFetch(`/api/user-management/users/${userId}/agents`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
            },
            body: JSON.stringify({
              agent_id: access.agent_id,
              is_allowed: access.is_allowed,
              valid_from: access.valid_from ? access.valid_from.toISOString() : null,
              valid_to: access.valid_to ? access.valid_to.toISOString() : null,
            }),
          });
        }
      }

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
                name="roleId"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Role</FormLabel>
                    <FormControl>
                      <Select
                        onValueChange={(value) => field.onChange(value)}
                        defaultValue={field.value}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select a role" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectGroup>
                            {roleList?.map((role: UserRole) => (
                              <SelectItem key={role.id} value={role.id}>
                                {role.name}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="superior_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Superior</FormLabel>
                    <FormControl>
                      <Select
                        onValueChange={(value) => {
                          field.onChange(value === '__none__' ? null : value);
                        }}
                        value={field.value || '__none__'}
                      >
                        <SelectTrigger>
                          <SelectValue placeholder="Select a superior" />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectGroup>
                            <SelectItem value="__none__">None</SelectItem>
                            {(superiorUsers || []).map((superior: { id: string; name?: string | null; email: string }) => (
                              <SelectItem key={superior.id} value={superior.id}>
                                {superior.name || superior.email}
                              </SelectItem>
                            ))}
                          </SelectGroup>
                        </SelectContent>
                      </Select>
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
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

              {/* Access Agents Section */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <FormLabel>Access Agents</FormLabel>
                  {availableAgents.length > 0 && (
                    <Select
                      onValueChange={(agentId) => {
                        const agent = agents.find((a: AccessAgent) => a.id === agentId);
                        if (agent) {
                          handleAddAgentClick(agent);
                        }
                      }}
                      value=""
                    >
                      <SelectTrigger className="w-auto">
                        <SelectValue placeholder="Add access agent" />
                      </SelectTrigger>
                      <SelectContent>
                        {availableAgents.map((agent: AccessAgent) => (
                          <SelectItem key={agent.id} value={agent.id}>
                            {agent.name} ({agent.code})
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                </div>

                {userAgentAccesses.length > 0 && (
                  <div className="space-y-2 border rounded-lg p-3">
                    {userAgentAccesses.map((access) => (
                      <div
                        key={access.agent_id}
                        className="flex items-center justify-between p-2 bg-muted rounded"
                      >
                        <div className="flex-1">
                          <div className="font-medium text-sm">{access.agent_name}</div>
                          <div className="text-xs text-muted-foreground">
                            Allowed: {access.is_allowed ? 'Yes' : 'No'}
                            {access.valid_from && ` • From: ${formatDate(new Date(access.valid_from))}`}
                            {access.valid_to && ` • To: ${formatDate(new Date(access.valid_to))}`}
                          </div>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => handleRemoveAgent(access.agent_id)}
                        >
                          <X className="h-4 w-4" />
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
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

      {/* Access Agent Configuration Dialog */}
      {selectedAgent && (
        <UserAgentAccessDialog
          open={accessDialogOpen}
          onOpenChange={(open) => {
            setAccessDialogOpen(open);
            if (!open) {
              setSelectedAgent(null);
            }
          }}
          userId="" // Will be set after user creation
          agentId={selectedAgent.id}
          agentName={selectedAgent.name}
          onSubmit={handleAccessAgentSubmit}
        />
      )}
    </Dialog>
  );
};

export default UserAddDialog;
