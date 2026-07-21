'use client';

import { useEffect, useMemo, useState } from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';
import { useQuery } from '@tanstack/react-query';
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
import { toast } from 'sonner';
import { useCreateAccessAgent, useUpdateAccessAgent, useAccessAgent, useAccessAgents, useAgentTeams, useTeams } from '../hooks/useAccessAgents';
import { setAgentTeams } from '../services/accessAgentService';
import { getSLAPolicies } from '@/app/(protected)/sla-management/sla-policies/services/slaPolicyService';
import { AccessAgentSchema, type AccessAgentSchemaType } from '../forms/access-agent-schema';
import type { AccessAgentFormData } from '../types/accessAgent.types';
import RecordNavigation from '@/components/common/RecordNavigation';

interface AccessAgentFormProps {
  accessAgentId?: string;
  onSuccess?: () => void;
}

type AssignmentRow = { id: string; tier: number | null; team_id: string; notify_on_extension: boolean };
type AssignmentGroup = { id: string; code: string; policy_id: string | null; rows: AssignmentRow[] };

const NO_POLICY = '__none__';

export default function AccessAgentForm({ accessAgentId, onSuccess }: AccessAgentFormProps) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const isEditMode = !!accessAgentId;
  const { data: accessAgent, isLoading: isLoadingAccessAgent } = useAccessAgent(accessAgentId || null);
  const createMutation = useCreateAccessAgent();
  const updateMutation = useUpdateAccessAgent();
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
  const [assignmentGroups, setAssignmentGroups] = useState<AssignmentGroup[]>([]);

  // SLA policies for the per-group policy picker. One policy per team-set group; on save
  // it is stamped onto every tier row of that group (backend casts it to all rows).
  const { data: slaPoliciesData } = useQuery({
    queryKey: ['sla-policies', 'access-agent-picker'],
    queryFn: () =>
      getSLAPolicies({
        pageIndex: 0,
        pageSize: 100,
        sorting: [{ id: 'name', desc: false }],
        searchQuery: '',
      }),
    enabled: isEditMode,
  });
  const slaPolicies = slaPoliciesData?.data ?? [];


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
        grouped.set(code, {
          id: crypto.randomUUID(),
          code,
          // Rows of a group share one policy_id; read the first non-null seen.
          policy_id: assignment.policy_id ? String(assignment.policy_id) : null,
          rows: [],
        });
      }
      const grp = grouped.get(code);
      if (grp && !grp.policy_id && assignment.policy_id) {
        grp.policy_id = String(assignment.policy_id);
      }
      grp?.rows.push({
        id: crypto.randomUUID(),
        tier:
          assignment.tier != null && Number(assignment.tier) >= 1 && Number(assignment.tier) <= 3
            ? Number(assignment.tier)
            : null,
        team_id: String(assignment.team_id ?? ''),
        notify_on_extension: assignment.notify_on_extension ?? true,
      });
    }
    setAssignmentGroups(Array.from(grouped.values()));
  }, [agentTeamsData?.assignments]);


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
          is_active: accessAgent.is_active,
          assign_to_new_internal_contacts: accessAgent.assign_to_new_internal_contacts ?? false,
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
              // Stamp the group's policy onto every row; backend casts one policy per code.
              policy_id: group.policy_id || undefined,
              notify_on_extension: row.notify_on_extension ?? true,
            })),
          )
          .filter((a) => a.code && a.team_id);
        await setAgentTeams(accessAgentId, validAssignments);
        queryClient.invalidateQueries({ queryKey: ['agent-teams', accessAgentId] });
        toast.success('Access agent updated successfully');
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
      const msg = error instanceof Error ? error.message : 'Something went wrong';
      toast.error(msg);
    }
  };

  if (isEditMode && isLoadingAccessAgent) {
    return (
      <div className="flex items-center justify-center p-8">
        <LoaderCircleIcon className="size-6 animate-spin" />
      </div>
    );
  }

  const isLoading =
    createMutation.isPending ||
    updateMutation.isPending;

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

              <FormField
                control={form.control}
                name="assign_to_new_internal_contacts"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center justify-between rounded-lg border p-4">
                    <div className="space-y-0.5">
                      <FormLabel className="text-base">Assign to new internal users</FormLabel>
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
                  {assignmentGroups.map((group, groupIdx) => (
                    <div key={group.id} className="space-y-3 rounded-md border p-3">
                      <div className="flex flex-wrap items-end gap-3">
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
                        <div className="flex-1 min-w-[200px]">
                          <label className="text-xs text-muted-foreground mb-1 block">SLA policy</label>
                          <Select
                            value={group.policy_id ?? NO_POLICY}
                            disabled={isLoading}
                            onValueChange={(v) => {
                              const next = [...assignmentGroups];
                              next[groupIdx] = {
                                ...next[groupIdx],
                                policy_id: v === NO_POLICY ? null : v,
                              };
                              setAssignmentGroups(next);
                            }}
                          >
                            <SelectTrigger>
                              <SelectValue placeholder="Select SLA policy" />
                            </SelectTrigger>
                            <SelectContent>
                              <SelectItem value={NO_POLICY}>— No policy —</SelectItem>
                              {slaPolicies.map((policy) => (
                                <SelectItem key={policy.id} value={policy.id}>
                                  {policy.name} ({policy.code})
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
                            <div className="w-[140px]">
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
                            <div className="flex-1 min-w-[180px]">
                              <label className="text-xs text-muted-foreground mb-1 block">Team</label>
                              <Select
                                value={row.team_id}
                                disabled={isLoading}
                                onValueChange={(teamId) => {
                                  const next = [...assignmentGroups];
                                  next[groupIdx].rows[rowIdx] = { ...next[groupIdx].rows[rowIdx], team_id: teamId };
                                  setAssignmentGroups(next);
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
                            {/* Notify-on-extension applies to escalation tiers (2/3):
                                when a lower-tier deadline is extended, this tier's team
                                is notified. Tier 1 is the base handler, never a notify
                                target, so the toggle only shows for tier 2/3. */}
                            {row.tier != null && row.tier >= 2 && (
                              <div className="flex items-center gap-2 pb-1.5">
                                <Switch
                                  id={`notify-ext-${row.id}`}
                                  checked={row.notify_on_extension ?? true}
                                  disabled={isLoading}
                                  onCheckedChange={(checked) => {
                                    const next = [...assignmentGroups];
                                    next[groupIdx].rows[rowIdx] = {
                                      ...next[groupIdx].rows[rowIdx],
                                      notify_on_extension: checked,
                                    };
                                    setAssignmentGroups(next);
                                  }}
                                />
                                <label
                                  htmlFor={`notify-ext-${row.id}`}
                                  className="text-xs text-muted-foreground"
                                >
                                  Notify on extension
                                </label>
                              </div>
                            )}
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
                            notify_on_extension: true,
                          });
                          setAssignmentGroups(next);
                        }}
                      >
                        <Plus className="mr-2 size-4" />
                        Add tier
                      </Button>
                    </div>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    disabled={isLoading || teamsList.length === 0}
                    onClick={() => {
                      setAssignmentGroups([
                        ...assignmentGroups,
                        {
                          id: crypto.randomUUID(),
                          code: '',
                          policy_id: null,
                          rows: [{ id: crypto.randomUUID(), tier: null, team_id: teamsList[0]?.id ?? '', notify_on_extension: true }],
                        },
                      ]);
                    }}
                  >
                    <Plus className="mr-2 size-4" />
                    Add group
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
