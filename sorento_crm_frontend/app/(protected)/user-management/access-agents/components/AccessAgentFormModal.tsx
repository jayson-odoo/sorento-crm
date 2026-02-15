'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { LoaderCircleIcon, Plus, Save, Trash2 } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
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
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  useCreateAccessAgent,
  useUpdateAccessAgent,
  useAccessAgent,
  useRespondSyncedUsers,
  useAgentTeams,
  useTeams,
} from '../hooks/useAccessAgents';
import { setAgentTeams } from '../services/accessAgentService';
import { AccessAgentSchema, type AccessAgentSchemaType } from '../forms/access-agent-schema';
import type { AccessAgentFormData } from '../types/accessAgent.types';

interface AccessAgentFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessAgentId?: string | null;
  onSuccess?: () => void;
}

export default function AccessAgentFormModal({
  open,
  onOpenChange,
  accessAgentId,
  onSuccess,
}: AccessAgentFormModalProps) {
  const queryClient = useQueryClient();
  const isEditMode = !!accessAgentId;
  const { data: accessAgent, isLoading: isLoadingAccessAgent } = useAccessAgent(accessAgentId || null);
  const createMutation = useCreateAccessAgent();
  const updateMutation = useUpdateAccessAgent();
  const { data: respondUsers } = useRespondSyncedUsers();
  const { data: agentTeamsData } = useAgentTeams(isEditMode ? accessAgentId ?? null : null);
  const { data: teamsList = [] } = useTeams();
  const [localAssignments, setLocalAssignments] = useState<{ code: string; team_id: string }[]>([]);

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

  const [formInitialized, setFormInitialized] = useState(false);

  useEffect(() => {
    if (accessAgent && isEditMode && open && !formInitialized) {
      form.reset({
        code: accessAgent.code,
        name: accessAgent.name,
        description: accessAgent.description || '',
        pic_respond_user_id: accessAgent.pic_respond_user_id || null,
        is_active: accessAgent.is_active,
      });
      setFormInitialized(true);
    }
  }, [accessAgent, isEditMode, open, form, formInitialized]);

  useEffect(() => {
    const fromServer = agentTeamsData?.assignments;
    setLocalAssignments(fromServer ? [...fromServer] : []);
  }, [agentTeamsData?.assignments]);

  useEffect(() => {
    if (!open) setFormInitialized(false);
  }, [open]);

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
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      console.error('Access agent form submission error:', error);
    }
  };

  const isLoading = createMutation.isPending || updateMutation.isPending;
  if (isEditMode && open && isLoadingAccessAgent) {
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <div className="flex items-center justify-center p-8">
            <LoaderCircleIcon className="size-6 animate-spin" />
          </div>
        </DialogContent>
      </Dialog>
    );
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col">
        <DialogHeader>
          <DialogTitle>{isEditMode ? 'Edit Access Agent' : 'Create Access Agent'}</DialogTitle>
        </DialogHeader>
        <ScrollArea className="flex-1 pr-4 -mr-4">
          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} id="access-agent-form" className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="code"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Code *</FormLabel>
                      <FormControl>
                        <Input placeholder="AGENT-001" {...field} disabled={isEditMode} />
                      </FormControl>
                      <FormDescription>Unique identifier (alphanumeric, dashes, underscores only)</FormDescription>
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
                      <Textarea placeholder="Enter description..." {...field} value={field.value || ''} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="pic_respond_user_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>PIC Respond User</FormLabel>
                      <FormControl>
                        <Select
                          value={field.value || '__none__'}
                          onValueChange={(v) => field.onChange(v === '__none__' ? null : v)}
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="Select user" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="__none__">Unassigned</SelectItem>
                            {(respondUsers || [])
                              .filter((u) => !!u.respond_user_id)
                              .map((u) => (
                                <SelectItem key={u.id} value={u.respond_user_id as string}>
                                  {u.name || u.email}
                                </SelectItem>
                              ))}
                          </SelectContent>
                        </Select>
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <FormField
                  control={form.control}
                  name="is_active"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                      <FormLabel className="text-base">Active</FormLabel>
                      <FormControl>
                        <Switch checked={field.value} onCheckedChange={field.onChange} />
                      </FormControl>
                    </FormItem>
                  )}
                />
              </div>

              {isEditMode && (
                <div className="space-y-4">
                  <h4 className="font-medium">Team Assignments</h4>
                  <p className="text-sm text-muted-foreground">
                    Assign teams by context code. Add members under User Management → Teams.
                  </p>
                  {teamsList.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No teams yet. Create teams first.</p>
                  ) : (
                    <>
                      {localAssignments.map((a, idx) => (
                        <div key={idx} className="flex flex-wrap items-center gap-3 rounded-md border p-3">
                          <div className="flex-1 min-w-[120px]">
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
                          <div className="flex-1 min-w-[160px]">
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
                                {teamsList.map((t: { id: string; name: string }) => (
                                  <SelectItem key={t.id} value={t.id}>
                                    {t.name}
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
                            onClick={() => setLocalAssignments(localAssignments.filter((_, i) => i !== idx))}
                          >
                            <Trash2 className="size-4" />
                          </Button>
                        </div>
                      ))}
                      <Button
                        type="button"
                        variant="outline"
                        disabled={isLoading || teamsList.length === 0}
                        onClick={() =>
                          setLocalAssignments([...localAssignments, { code: '', team_id: teamsList[0]?.id ?? '' }])
                        }
                      >
                        <Plus className="mr-2 size-4" />
                        Add assignment
                      </Button>
                    </>
                  )}
                </div>
              )}
            </form>
          </Form>
        </ScrollArea>
        <div className="flex justify-end gap-2 pt-4 border-t">
          <Button variant="outline" onClick={() => onOpenChange(false)} disabled={isLoading}>
            Cancel
          </Button>
          <Button type="submit" form="access-agent-form" disabled={isLoading}>
            {isLoading ? (
              <>
                <LoaderCircleIcon className="mr-2 size-4 animate-spin" />
                {isEditMode ? 'Updating...' : 'Creating...'}
              </>
            ) : (
              <>
                <Save className="mr-2 size-4" />
                {isEditMode ? 'Update' : 'Create'}
              </>
            )}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
