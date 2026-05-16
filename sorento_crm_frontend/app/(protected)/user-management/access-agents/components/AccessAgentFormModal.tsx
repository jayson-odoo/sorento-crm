'use client';

import { useEffect, useState } from 'react';
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
import { toast } from 'sonner';
import {
  useCreateAccessAgent,
  useUpdateAccessAgent,
  useAccessAgent,
  useAgentTeams,
  useTeams,
  useAgentMcpToolBindings,
  useSetAgentMcpToolBindings,
} from '../hooks/useAccessAgents';
import { setAgentTeams, type McpToolBindingInput } from '../services/accessAgentService';
import { McpToolBindingsEditor } from './McpToolBindingsEditor';
import { AccessAgentSchema, type AccessAgentSchemaType } from '../forms/access-agent-schema';
import type { AccessAgentFormData } from '../types/accessAgent.types';

interface AccessAgentFormModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accessAgentId?: string | null;
  onSuccess?: () => void;
}

type AssignmentRow = { id: string; tier: number | null; team_id: string };
type AssignmentGroup = { id: string; code: string; rows: AssignmentRow[] };

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
  const { data: agentTeamsData } = useAgentTeams(isEditMode ? accessAgentId ?? null : null);
  const { data: teamsList = [] } = useTeams();
  const [assignmentGroups, setAssignmentGroups] = useState<AssignmentGroup[]>([]);

  const { data: agentMcpBindingsData } = useAgentMcpToolBindings(isEditMode ? accessAgentId ?? null : null);
  const setAgentMcpToolBindingsMutation = useSetAgentMcpToolBindings();
  const [bindings, setBindings] = useState<McpToolBindingInput[]>([]);
  const [initialBindings, setInitialBindings] = useState<McpToolBindingInput[]>([]);

  useEffect(() => {
    if (agentMcpBindingsData) {
      const next: McpToolBindingInput[] = agentMcpBindingsData.map((b) => ({
        tool_id: b.tool_id,
        team_id: b.team_id,
        tier: b.tier,
      }));
      setBindings(next);
      setInitialBindings(next);
    }
  }, [agentMcpBindingsData]);

  const form = useForm<AccessAgentSchemaType>({
    resolver: zodResolver(AccessAgentSchema),
    defaultValues: {
      code: '',
      name: '',
      description: '',
      is_active: true,
      assign_to_new_internal_contacts: false,
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
        is_active: accessAgent.is_active,
        assign_to_new_internal_contacts: accessAgent.assign_to_new_internal_contacts ?? false,
      });
      setFormInitialized(true);
    }
  }, [accessAgent, isEditMode, open, form, formInitialized]);

  useEffect(() => {
    const fromServer = agentTeamsData?.assignments;
    if (!fromServer || fromServer.length === 0) {
      setAssignmentGroups([]);
      return;
    }
    const grouped = new Map<string, AssignmentGroup>();
    for (const assignment of fromServer) {
      const code = String(assignment.code ?? '').trim();
      if (!grouped.has(code)) {
        grouped.set(code, { id: crypto.randomUUID(), code, rows: [] });
      }
      grouped.get(code)?.rows.push({
        id: crypto.randomUUID(),
        tier:
          assignment.tier != null && Number(assignment.tier) >= 1 && Number(assignment.tier) <= 3
            ? Number(assignment.tier)
            : null,
        team_id: String(assignment.team_id ?? ''),
      });
    }
    setAssignmentGroups(Array.from(grouped.values()));
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
        is_active: data.is_active,
        assign_to_new_internal_contacts: data.assign_to_new_internal_contacts,
      };

      if (isEditMode && accessAgentId) {
        await updateMutation.mutateAsync({ id: accessAgentId, data: formData });
        const validAssignments = assignmentGroups
          .flatMap((group) =>
            group.rows.map((row) => ({
              code: String(group.code).trim(),
              team_id: String(row.team_id),
              tier: row.tier != null && row.tier >= 1 && row.tier <= 3 ? row.tier : undefined,
            })),
          )
          .filter((a) => a.code && a.team_id);
        await setAgentTeams(accessAgentId, validAssignments);
        queryClient.invalidateQueries({ queryKey: ['agent-teams', accessAgentId] });
        const sanitized = bindings.filter((b) => b.tool_id);
        if (JSON.stringify(sanitized) !== JSON.stringify(initialBindings)) {
          await setAgentMcpToolBindingsMutation.mutateAsync({
            agentId: accessAgentId,
            bindings: sanitized,
          });
          setInitialBindings(sanitized);
        }
        toast.success('Access agent updated successfully');
      } else {
        await createMutation.mutateAsync(formData);
      }
      queryClient.invalidateQueries({ queryKey: ['access-agents'] });
      onOpenChange(false);
      onSuccess?.();
    } catch (error) {
      console.error('Access agent form submission error:', error);
      const msg = error instanceof Error ? error.message : 'Something went wrong';
      toast.error(msg);
    }
  };

  const isLoading =
    createMutation.isPending ||
    updateMutation.isPending ||
    setAgentMcpToolBindingsMutation.isPending;
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
      <DialogContent className="max-w-2xl max-h-[90vh] flex flex-col overflow-hidden">
        <DialogHeader className="shrink-0">
          <DialogTitle>{isEditMode ? 'Edit Access Agent' : 'Create Access Agent'}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden pr-1">
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
                <FormField
                  control={form.control}
                  name="assign_to_new_internal_contacts"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                      <div className="space-y-0.5">
                        <FormLabel className="text-base">Assign to new internal users</FormLabel>
                      </div>
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
                  {teamsList.length === 0 ? (
                    <p className="text-sm text-muted-foreground">No teams yet. Create teams first.</p>
                  ) : (
                    <>
                      <ScrollArea className="h-[200px] rounded-md border">
                        <div className="space-y-3 p-3">
                          {assignmentGroups.map((group, groupIdx) => (
                            <div key={group.id} className="space-y-3 rounded-md border p-3">
                              <div className="flex items-end gap-3">
                                <div className="flex-1 min-w-[140px]">
                                  <label className="text-xs text-muted-foreground mb-1 block">Code</label>
                                  <Input
                                    placeholder="e.g. marketing"
                                    value={group.code}
                                    disabled={isLoading}
                                    onChange={(e) => {
                                      const next = [...assignmentGroups];
                                      next[groupIdx] = { ...next[groupIdx], code: e.target.value };
                                      setAssignmentGroups(next);
                                    }}
                                    className="font-mono text-sm"
                                  />
                                </div>
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon"
                                  className="text-destructive hover:text-destructive"
                                  disabled={isLoading}
                                  onClick={() => setAssignmentGroups(assignmentGroups.filter((_, i) => i !== groupIdx))}
                                >
                                  <Trash2 className="size-4" />
                                </Button>
                              </div>
                              {group.rows.map((row, rowIdx) => {
                                const usedTiers = new Set(
                                  group.rows
                                    .filter((_, i) => i !== rowIdx)
                                    .map((r) => r.tier)
                                    .filter((t): t is number => t != null),
                                );
                                return (
                                  <div key={row.id} className="flex flex-wrap items-end gap-3 rounded-md border p-3">
                                    <div className="w-[100px]">
                                      <label className="text-xs text-muted-foreground mb-1 block">Tier</label>
                                      <Select
                                        value={row.tier != null ? String(row.tier) : '__none__'}
                                        disabled={isLoading}
                                        onValueChange={(v) => {
                                          const next = [...assignmentGroups];
                                          next[groupIdx].rows[rowIdx] = {
                                            ...next[groupIdx].rows[rowIdx],
                                            tier: v === '__none__' ? null : Number(v),
                                          };
                                          setAssignmentGroups(next);
                                        }}
                                      >
                                        <SelectTrigger>
                                          <SelectValue placeholder="—" />
                                        </SelectTrigger>
                                        <SelectContent>
                                          <SelectItem value="__none__">—</SelectItem>
                                          <SelectItem value="1" disabled={usedTiers.has(1)}>1</SelectItem>
                                          <SelectItem value="2" disabled={usedTiers.has(2)}>2</SelectItem>
                                          <SelectItem value="3" disabled={usedTiers.has(3)}>3</SelectItem>
                                        </SelectContent>
                                      </Select>
                                    </div>
                                    <div className="flex-1 min-w-[160px]">
                                      <label className="text-xs text-muted-foreground mb-1 block">Team</label>
                                      <Select
                                        value={row.team_id}
                                        disabled={isLoading}
                                        onValueChange={(teamId) => {
                                          const next = [...assignmentGroups];
                                          next[groupIdx].rows[rowIdx] = {
                                            ...next[groupIdx].rows[rowIdx],
                                            team_id: teamId,
                                          };
                                          setAssignmentGroups(next);
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
                                      className="text-destructive hover:text-destructive"
                                      disabled={isLoading}
                                      onClick={() => {
                                        const next = [...assignmentGroups];
                                        next[groupIdx].rows = next[groupIdx].rows.filter((_, i) => i !== rowIdx);
                                        setAssignmentGroups(next);
                                      }}
                                    >
                                      <Trash2 className="size-4" />
                                    </Button>
                                  </div>
                                );
                              })}
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                disabled={isLoading || teamsList.length === 0}
                                onClick={() => {
                                  const next = [...assignmentGroups];
                                  next[groupIdx].rows.push({
                                    id: crypto.randomUUID(),
                                    tier: null,
                                    team_id: teamsList[0]?.id ?? '',
                                  });
                                  setAssignmentGroups(next);
                                }}
                              >
                                <Plus className="mr-2 size-4" />
                                Add tier
                              </Button>
                            </div>
                          ))}
                        </div>
                      </ScrollArea>
                      <Button
                        type="button"
                        variant="outline"
                        disabled={isLoading || teamsList.length === 0}
                        onClick={() =>
                          setAssignmentGroups([
                            ...assignmentGroups,
                            {
                              id: crypto.randomUUID(),
                              code: '',
                              rows: [{ id: crypto.randomUUID(), tier: null, team_id: teamsList[0]?.id ?? '' }],
                            },
                          ])
                        }
                      >
                        <Plus className="mr-2 size-4" />
                        Add group
                      </Button>
                    </>
                  )}
                </div>
              )}

              {isEditMode && accessAgentId && (
                <div className="space-y-3">
                  <h4 className="font-medium">MCP Tool Bindings</h4>
                  <p className="text-xs text-muted-foreground">
                    Bind a tool to a specific team to route escalation for that tool only
                    to that team. Leave team empty to fan out via this agent&apos;s team
                    set above.
                  </p>
                  <McpToolBindingsEditor
                    value={bindings}
                    onChange={setBindings}
                    disabled={isLoading}
                  />
                </div>
              )}
            </form>
          </Form>
        </div>
        <div className="flex shrink-0 justify-end gap-2 pt-4 border-t">
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
