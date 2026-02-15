'use client';

import { useMemo, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Edit, Trash2 } from 'lucide-react';
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
import { useAccessAgent, useAccessAgents, useAgentTeams, useTeams } from '../hooks/useAccessAgents';
import { formatDate } from '@/lib/helpers';
import AccessAgentDeleteDialog from './access-agent-delete-dialog';
import ContactAccessAgentsTable from './ContactAccessAgentsTable';
import RecordNavigation from '@/components/common/RecordNavigation';

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
  const { data: agentTeamsData } = useAgentTeams(accessAgentId);
  const { data: teamsList = [] } = useTeams();
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const [editModalOpen, setEditModalOpen] = useState(false);

  const assignments = agentTeamsData?.assignments ?? [];
  const teamNameMap = useMemo(() => {
    const m = new Map<string, string>();
    teamsList.forEach((t: { id: string; name: string }) => m.set(t.id, t.name));
    return m;
  }, [teamsList]);

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
              <p className="text-sm text-muted-foreground">PIC Respond User</p>
              <div className="space-y-1">
                {accessAgent.pic_respond_user_id ? (
                  <>
                    <p className="font-medium">
                      {accessAgent.pic_respond_user_name || accessAgent.pic_respond_user_id}
                    </p>
                    {accessAgent.pic_respond_user_name && (
                      <p className="text-xs text-muted-foreground font-mono">
                        ID: {accessAgent.pic_respond_user_id}
                      </p>
                    )}
                  </>
                ) : (
                  <p className="font-medium text-muted-foreground">-</p>
                )}
              </div>
            </div>
            <div>
              <p className="text-sm text-muted-foreground">Status</p>
              <Badge variant={accessAgent.is_active ? 'success' : 'secondary'} appearance="ghost">
                <BadgeDot />
                {accessAgent.is_active ? 'Active' : 'Inactive'}
              </Badge>
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
        <CardHeader>
          <CardTitle>Team Assignments</CardTitle>
          <p className="text-sm text-muted-foreground font-normal">
            Assign teams by context code for round-robin next-assignee. Add members under User Management → Teams.
          </p>
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
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Code</TableHead>
                  <TableHead>Team</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {assignments.map((a: { code: string; team_id: string }) => (
                  <TableRow key={a.code}>
                    <TableCell className="font-mono">{a.code}</TableCell>
                    <TableCell>{teamNameMap.get(a.team_id) ?? a.team_id}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
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
