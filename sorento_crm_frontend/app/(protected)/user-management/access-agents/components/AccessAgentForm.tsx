'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useRouter } from 'next/navigation';
import { LoaderCircleIcon, Plus, Save, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
  FormDescription,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useQueryClient } from '@tanstack/react-query';
import { useCreateAccessAgent, useUpdateAccessAgent, useAccessAgent, useRespondSyncedUsers, useAccessAgents, useAgentTeams, useTeams } from '../hooks/useAccessAgents';
import { setAgentTeams } from '../services/accessAgentService';
import { AccessAgentSchema, type AccessAgentSchemaType } from '../forms/access-agent-schema';
import type { AccessAgentFormData } from '../types/accessAgent.types';
import RecordNavigation from '@/components/common/RecordNavigation';

interface AccessAgentFormProps {
  accessAgentId?: string;
  onSuccess?: () => void;
}

export default function AccessAgentForm({ accessAgentId, onSuccess }: AccessAgentFormProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const isEditMode = !!accessAgentId;
  const { data: accessAgent, isLoading: isLoadingAccessAgent } = useAccessAgent(accessAgentId || null);
  const createMutation = useCreateAccessAgent();
  const updateMutation = useUpdateAccessAgent();
  const { data: respondUsers, isLoading: isLoadingRespondUsers } = useRespondSyncedUsers();
  const navigationParams = useMemo(
    () => ({
      pageIndex: 0,
      pageSize: 100,
      sorting: [{ id: 'created_at', desc: true }],
      searchQuery: '',
      status: undefined,
    }),
    [],
  );
  const { data: navigationData } = useAccessAgents(navigationParams);
  const navigationItems = navigationData?.data ?? [];
  const { data: agentTeamsData } = useAgentTeams(isEditMode ? accessAgentId ?? null : null);
  const { data: teamsList = [] } = useTeams();
  const [localAssignments, setLocalAssignments] = useState<{ code: string; team_id: string }[]>([]);

  useEffect(() => {
    const fromServer = agentTeamsData?.assignments;
    setLocalAssignments(fromServer ? [...fromServer] : []);
  }, [agentTeamsData?.assignments]);


  const form = useForm<AccessAgentSchemaType>({
    resolver: zodResolver(AccessAgentSchema),
    defaultValues: {
      code: '',
      name: '',
      description: '',
      pic_respond_user_id: '',
      is_active: true,
    },
    mode: 'onSubmit',
  });

  // Track if form has been initialized to prevent multiple resets
  const [formInitialized, setFormInitialized] = useState(false);

  // Load access agent data when editing
  useEffect(() => {
    if (accessAgent && isEditMode && !formInitialized) {
      // Use setTimeout to ensure form fields are ready
      const timeoutId = setTimeout(() => {
        form.reset({
          code: accessAgent.code,
          name: accessAgent.name,
          description: accessAgent.description || '',
          pic_respond_user_id: accessAgent.pic_respond_user_id || null,
          is_active: accessAgent.is_active,
        });
        setFormInitialized(true);
      }, 0);

      return () => clearTimeout(timeoutId);
    }
  }, [accessAgent, isEditMode, form, formInitialized]);

  // Reset formInitialized when accessAgentId changes
  useEffect(() => {
    setFormInitialized(false);
  }, [accessAgentId]);

  const onSubmit = async (data: AccessAgentSchemaType) => {
    try {
      const formData: AccessAgentFormData = {
        code: data.code,
        name: data.name,
        description: data.description || undefined,
        pic_respond_user_id: data.pic_respond_user_id && data.pic_respond_user_id !== '__none__' ? data.pic_respond_user_id : undefined,
        is_active: data.is_active,
      };

      if (isEditMode && accessAgentId) {
        await updateMutation.mutateAsync({ id: accessAgentId, data: formData });
        const validAssignments = localAssignments
          .filter((a) => a.code.trim() && a.team_id)
          .map((a) => ({ code: String(a.code).trim(), team_id: String(a.team_id) }));
        await setAgentTeams(accessAgentId, validAssignments);
        queryClient.invalidateQueries({ queryKey: ['agent-teams', accessAgentId] });
      } else {
        await createMutation.mutateAsync(formData);
      }

      if (onSuccess) {
        onSuccess();
      } else {
        router.push('/user-management/access-agents');
      }
    } catch (error) {
      console.error('Access agent form submission error:', error);
    }
  };

  if (isEditMode && isLoadingAccessAgent) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading = createMutation.isPending || updateMutation.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        {isEditMode && accessAgentId && (
          <div className="flex justify-end">
            <RecordNavigation
              currentId={accessAgentId}
              items={navigationItems}
              basePath="/user-management/access-agents"
            />
          </div>
        )}
        <Card>
          <CardHeader>
            <CardTitle>{isEditMode ? 'Edit Access Agent' : 'Create Access Agent'}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="code"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Code *</FormLabel>
                    <FormControl>
                      <Input
                        placeholder="AGENT-001"
                        {...field}
                        disabled={isEditMode}
                      />
                    </FormControl>
                    <FormDescription>
                      Unique access agent identifier (alphanumeric, dashes, underscores only)
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>Name *</FormLabel>
                    <FormControl>
                      <Input placeholder="Enter access agent name" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Enter description..."
                      {...field}
                      value={field.value || ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="pic_respond_user_id"
                render={({ field }) => {
                  // Find the selected user to display their name
                  const selectedUser = respondUsers?.find(
                    (user) => user.respond_user_id === field.value
                  );
                  const displayValue = selectedUser 
                    ? (selectedUser.name || selectedUser.email || field.value)
                    : field.value || '';
                  
                  return (
                    <FormItem>
                      <FormLabel>PIC Respond User</FormLabel>
                      <FormControl>
                        <Select
                          value={field.value || '__none__'}
                          onValueChange={(value) => {
                            // Convert "__none__" to null/empty for optional field
                            field.onChange(value === '__none__' ? null : value);
                          }}
                          disabled={isLoadingRespondUsers}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select user" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">Unassigned</SelectItem>
                            {(respondUsers || [])
                              .filter((user) => !!user.respond_user_id)
                              .map((user) => (
                                <SelectItem key={user.id} value={user.respond_user_id as string}>
                                  {user.name || user.email}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormDescription>
                        Person in charge for responding
                        {selectedUser && (
                          <span className="block mt-1 text-xs text-muted-foreground">
                            Selected: {selectedUser.name || selectedUser.email}
                          </span>
                        )}
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  );
                }}
              />

              <FormField
                control={form.control}
                name="is_active"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Active Status</FormLabel>
                      <FormDescription>
                        Enable or disable this access agent
                      </FormDescription>
                    </div>
                    <FormControl>
                      <Switch
                        checked={field.value}
                        onCheckedChange={field.onChange}
                      />
                    </FormControl>
                  </FormItem>
                )}
              />
            </div>

          </CardContent>
        </Card>

        {isEditMode && accessAgentId && (
          <Card>
            <CardHeader>
              <CardTitle>Team Assignments</CardTitle>
            </CardHeader>
            <CardContent>
              {teamsList.length === 0 ? (
                <p className="text-sm text-muted-foreground">No teams yet. Create teams under User Management → Teams.</p>
              ) : (
                <div className="space-y-4">
                  {localAssignments.map((a: { code: string; team_id: string }, idx: number) => (
                    <div
                      key={idx}
                      className="flex flex-wrap items-center gap-3 rounded-md border p-3"
                    >
                      <div className="flex-1 min-w-[140px]">
                        <label className="text-xs text-muted-foreground mb-1 block">Code</label>
                        <Input
                          placeholder="e.g. marketing"
                          value={a.code}
                          disabled={isLoading}
                          onChange={(e) => {
                            const next = [...localAssignments];
                            next[idx] = { ...next[idx], code: e.target.value };
                            setLocalAssignments(next);
                          }}
                          className="font-mono text-sm"
                        />
                      </div>
                      <div className="flex-1 min-w-[180px]">
                        <label className="text-xs text-muted-foreground mb-1 block">Team</label>
                        <Select
                          value={a.team_id}
                          disabled={isLoading}
                          onValueChange={(teamId) => {
                            const next = [...localAssignments];
                            next[idx] = { ...next[idx], team_id: teamId };
                            setLocalAssignments(next);
                          }}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select team" />
                          </SelectTrigger>
                          <SelectContent>
                            {teamsList.map((team: { id: string; name: string }) => (
                              <SelectItem key={team.id} value={team.id}>
                                {team.name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive mt-6"
                        disabled={isLoading}
                        onClick={() => {
                          setLocalAssignments(localAssignments.filter((_, i) => i !== idx));
                        }}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    disabled={isLoading || teamsList.length === 0}
                    onClick={() => {
                      setLocalAssignments([
                        ...localAssignments,
                        { code: '', team_id: teamsList[0]?.id ?? '' },
                      ]);
                    }}
                  >
                    <Plus className="mr-2 size-4" />
                    Add assignment
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        <div className="flex justify-end gap-4 pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              if (onSuccess) {
                onSuccess();
              } else {
                router.push('/user-management/access-agents');
              }
            }}
            disabled={isLoading}
          >
            Cancel
          </Button>
          <Button type="submit" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="mr-2 size-4" />
                {isEditMode ? 'Update Access Agent' : 'Create Access Agent'}
              </>
            )}
          </Button>
        </div>
      </form>
    </Form>
  );
}
