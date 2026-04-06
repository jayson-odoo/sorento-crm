'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2, ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import AccessAgentFormModal from './AccessAgentFormModal';
import { Button } from '@/components/ui/button';
import { Badge, BadgeDot } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { useAccessAgent, useAccessAgents, useAgentTeams, useTeams } from '../hooks/useAccessAgents';
import { formatDate } from '@/lib/helpers';
import AccessAgentDeleteDialog from './access-agent-delete-dialog';
import ContactAccessAgentsTable from './ContactAccessAgentsTable';
import RecordNavigation from '@/components/common/RecordNavigation';
import type { AgentTeamMemberInfo, AgentTeamAssignment } from '../services/accessAgentService';

interface AccessAgentDetailProps {
  accessAgentId: string;
}

export default function AccessAgentDetail({ accessAgentId }: AccessAgentDetailProps) {
  const router = useRouter();
  const { data: accessAgent, isLoading } = useAccessAgent(accessAgentId);
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
  const {
    data: agentTeamsData,
    refetch: refetchAgentTeams,
    isRefetching: isRefetchingAgentTeams,
  } = useAgentTeams(accessAgentId);
  const { data: teamsList = [] } = useTeams();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);

  const assignments = agentTeamsData?.assignments ?? [];
  const [expandedTeams, setExpandedTeams] = useState<Set<string>>(new Set());
  const teamNameMap = useMemo(() => {
    const m = new Map<string, string>();
    teamsList.forEach((t: { id: string; name: string }) => m.set(t.id, t.name));
    return m;
  }, [teamsList]);
  const groupedAssignments = useMemo(() => {
    const groups = new Map<string, AgentTeamAssignment[]>();
    for (const assignment of assignments) {
      const code = String(assignment.code ?? '').trim();
      const key = code || '(no code)';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)?.push(assignment);
    }
    return Array.from(groups.entries()).map(([code, rows]) => ({
      code,
      rows: [...rows].sort((a, b) => {
        const ta = typeof a.tier === 'number' ? a.tier : 999;
        const tb = typeof b.tier === 'number' ? b.tier : 999;
        return ta - tb;
      }),
    }));
  }, [assignments]);

  const toggleTeam = (assignmentKey: string) => {
    setExpandedTeams((prev) => {
      const next = new Set(prev);
      if (next.has(assignmentKey)) {
        next.delete(assignmentKey);
      } else {
        next.add(assignmentKey);
      }
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <Skeleton className="h-96 w-full" />
      </div>
    );
  }

  if (!accessAgent) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Access agent not found</p>
        <Button variant="outline" onClick={() => router.push('/user-management/access-agents')} className="mt-4">
          Back to Access Agents
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold">{accessAgent.name}</h1>
            <Badge variant={accessAgent.is_active ? 'success' : 'secondary'} appearance="ghost">
              <BadgeDot />
              {accessAgent.is_active ? 'Active' : 'Inactive'}
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground">
            Code: {accessAgent.code}
          </p>
        </div>
        <div className="flex gap-2">
          <RecordNavigation
            currentId={accessAgentId}
            items={navigationItems}
            basePath="/user-management/access-agents"
          />
          <Button variant="outline" onClick={() => setEditModalOpen(true)}>
            <Edit className="size-4" />
            Edit
          </Button>
          <Button variant="destructive" onClick={() => setDeleteDialogOpen(true)}>
            <Trash2 className="size-4" />
            Delete
          </Button>
        </div>
      </div>

      {/* Access Agent Information */}
      <Card>
        <CardHeader>
          <CardTitle>Access Agent Information</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <p className="text-sm text-muted-foreground">Code</p>
              <p className="font-medium">{accessAgent.code}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Name</p>
              <p className="font-medium">{accessAgent.name}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge variant={accessAgent.is_active ? 'success' : 'secondary'} appearance="ghost">
                <BadgeDot />
                {accessAgent.is_active ? 'Active' : 'Inactive'}
              </Badge>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Assign to new internal users</p>
              <p className="font-medium">
                {accessAgent.assign_to_new_internal_contacts ? 'Yes' : 'No'}
              </p>
            </div>
            {accessAgent.description && (
              <div className="md:col-span-2">
                <p className="text-sm text-muted-foreground">Description</p>
                <p className="font-medium">{accessAgent.description}</p>
              </div>
            )}
            <div>
              <p className="text-sm text-muted-foreground">Created At</p>
              <p className="font-medium">{formatDate(new Date(accessAgent.created_at))}</p>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Updated At</p>
              <p className="font-medium">{formatDate(new Date(accessAgent.updated_at))}</p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Team Assignments */}
      <Card>
        <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-2 space-y-0">
          <CardTitle>Team Assignments</CardTitle>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={isRefetchingAgentTeams}
            onClick={() => refetchAgentTeams()}
            className="shrink-0 gap-2"
            aria-label="Refresh team assignments"
          >
            <RefreshCw
              className={`size-4 ${isRefetchingAgentTeams ? 'animate-spin' : ''}`}
              aria-hidden
            />
            Refresh
          </Button>
        </CardHeader>
        <CardContent>
          {assignments.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground border rounded-lg border-dashed">
              <p>No team assignments yet.</p>
              <p className="text-sm mt-1">Edit agent to add assignments.</p>
              <Button variant="outline" size="sm" className="mt-3" onClick={() => setEditModalOpen(true)}>
                Edit Access Agent
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {groupedAssignments.map((group) => (
                <div key={group.code} className="rounded-lg border p-3">
                  <div className="mb-3">
                    <span className="font-mono text-sm font-semibold">{group.code}</span>
                  </div>
                  <div className="space-y-2">
                    {group.rows.map((a) => {
                const assignmentKey = `${a.code}::${a.tier ?? 'none'}::${a.team_id}`;
                const isExpanded = expandedTeams.has(assignmentKey);
                const members = a.members ?? [];
                const lastAssignedId = a.last_assigned?.id;
                const nextInLineId = a.next_in_line?.id;

                return (
                  <Collapsible
                    key={assignmentKey}
                    open={isExpanded}
                    onOpenChange={() => toggleTeam(assignmentKey)}
                  >
                    <div className="border rounded-lg">
                      <CollapsibleTrigger className="w-full">
                        <div className="flex items-center justify-between p-4 hover:bg-accent/50 transition-colors">
                          <div className="flex items-center gap-3 flex-1">
                            <div className="flex items-center gap-2">
                              {isExpanded ? (
                                <ChevronDown className="size-4 text-muted-foreground" />
                              ) : (
                                <ChevronRight className="size-4 text-muted-foreground" />
                              )}
                            </div>
                            <div className="text-left flex-1">
                              <div className="flex items-center gap-3 flex-wrap">
                                {typeof (a as AgentTeamAssignment).tier === 'number' &&
                                  (a as AgentTeamAssignment).tier! >= 1 &&
                                  (a as AgentTeamAssignment).tier! <= 3 && (
                                  <Badge variant="secondary" className="text-xs font-normal">
                                    Tier {(a as AgentTeamAssignment).tier}
                                  </Badge>
                                )}
                                <span className="text-sm text-muted-foreground">•</span>
                                <span className="font-medium">
                                  {a.team_name ?? teamNameMap.get(a.team_id) ?? a.team_id}
                                </span>
                              </div>
                              <div className="flex items-center gap-4 mt-1 text-xs text-muted-foreground">
                                <span>{members.length} member{members.length !== 1 ? 's' : ''}</span>
                                {a.last_assigned && (
                                  <span>
                                    Last assigned: <span className="font-medium text-foreground">
                                      {a.last_assigned.name || a.last_assigned.email || a.last_assigned.id}
                                    </span>
                                  </span>
                                )}
                                {a.next_in_line && (
                                  <span>
                                    Next in line: <span className="font-medium text-primary">
                                      {a.next_in_line.name || a.next_in_line.email || a.next_in_line.id}
                                    </span>
                                  </span>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                      </CollapsibleTrigger>
                      <CollapsibleContent>
                        <div className="px-4 pb-4 border-t bg-accent/30">
                          {members.length === 0 ? (
                            <div className="py-4 text-sm text-muted-foreground text-center">
                              No members in this team
                            </div>
                          ) : (
                            <div className="py-3 space-y-2">
                              <div className="text-xs font-medium text-muted-foreground mb-2">
                                Team Members (in round-robin order):
                              </div>
                              <div className="space-y-1.5">
                                {members.map((member: AgentTeamMemberInfo, idx: number) => {
                                  const isLastAssigned = member.id === lastAssignedId;
                                  const isNextInLine = member.id === nextInLineId;
                                  const displayName = member.name || member.email || member.id;

                                  return (
                                    <div
                                      key={member.id}
                                      className={`
                                        flex items-center justify-between p-2 rounded-md text-sm
                                        ${isNextInLine ? 'bg-primary/10 border border-primary/20' : ''}
                                        ${isLastAssigned ? 'bg-muted/50' : ''}
                                      `}
                                    >
                                      <div className="flex items-center gap-2">
                                        <span className="text-xs text-muted-foreground w-6">
                                          {idx + 1}.
                                        </span>
                                        <span className="font-medium">{displayName}</span>
                                        {member.email && member.email !== displayName && (
                                          <span className="text-xs text-muted-foreground">
                                            ({member.email})
                                          </span>
                                        )}
                                      </div>
                                      <div className="flex items-center gap-2">
                                        {isLastAssigned && (
                                          <Badge variant="secondary" className="text-xs">
                                            Last assigned
                                          </Badge>
                                        )}
                                        {isNextInLine && (
                                          <Badge variant="primary" className="text-xs">
                                            Next in line
                                          </Badge>
                                        )}
                                      </div>
                                    </div>
                                  );
                                })}
                              </div>
                            </div>
                          )}
                        </div>
                      </CollapsibleContent>
                    </div>
                  </Collapsible>
                    );
                  })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Contact Access Agents Table */}
      <Card>
        <CardHeader>
          <CardTitle>Contact Access Agents</CardTitle>
        </CardHeader>
        <ContactAccessAgentsTable accessAgentId={accessAgentId} />
      </Card>

      <AccessAgentFormModal
        open={editModalOpen}
        onOpenChange={setEditModalOpen}
        accessAgentId={accessAgentId}
      />

      {/* Delete Dialog */}
      {accessAgent && (
        <AccessAgentDeleteDialog
          open={deleteDialogOpen}
          closeDialog={() => setDeleteDialogOpen(false)}
          accessAgent={accessAgent}
          onSuccess={() => {
            router.push('/user-management/access-agents');
          }}
        />
      )}
    </div>
  );
}
