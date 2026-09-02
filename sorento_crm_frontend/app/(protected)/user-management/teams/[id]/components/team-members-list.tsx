'use client';

import { useCallback, useMemo, useState } from 'react';
import { LoaderCircleIcon, Trash2, UserPlus, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { TeamMember } from '../../types/team.types';
import type { UserSelectItem } from '../../services/teamService';
import {
  useTeamMembers,
  useRemoveTeamMember,
  useUpdateTeamMemberRoundRobin,
} from '../../hooks/use-team-members';
import { addTeamMember } from '../../services/teamService';

function displayUser(user: UserSelectItem | undefined, userId: string): string {
  if (!user) return userId;
  if (user.name) return user.name;
  return user.email || userId;
}

export default function TeamMembersList({
  teamId,
  users,
}: {
  teamId: string;
  users: UserSelectItem[];
}) {
  const queryClient = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());
  const [isAdding, setIsAdding] = useState(false);

  const { data: members = [], isLoading } = useTeamMembers(teamId);
  const removeMutation = useRemoveTeamMember(teamId);
  const roundRobinMutation = useUpdateTeamMemberRoundRobin(teamId);

  const userMap = useMemo(() => {
    const m = new Map<string, UserSelectItem>();
    users.forEach((u) => m.set(u.id, u));
    return m;
  }, [users]);

  const memberUserIds = useMemo(() => new Set(members.map((m) => m.user_id)), [members]);
  const availableUsers = useMemo(
    () => users.filter((u) => !memberUserIds.has(u.id)),
    [users, memberUserIds],
  );

  const toggleUser = useCallback((userId: string) => {
    setSelectedUserIds((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }, []);

  const handleAdd = useCallback(async () => {
    if (selectedUserIds.size === 0) return;
    setIsAdding(true);
    const ids = Array.from(selectedUserIds);
    try {
      for (const userId of ids) {
        await addTeamMember(teamId, { user_id: userId });
      }
      queryClient.invalidateQueries({ queryKey: ['user-management-team-members', teamId] });
      toast.success(
        ids.length === 1 ? 'Member added' : `${ids.length} members added`,
      );
      setSelectedUserIds(new Set());
      setAddOpen(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to add members');
    } finally {
      setIsAdding(false);
    }
  }, [teamId, selectedUserIds, queryClient]);

  const selectedCount = selectedUserIds.size;

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between py-5">
          <h3 className="text-lg font-medium">Members</h3>
          <Button onClick={() => setAddOpen(true)} disabled={availableUsers.length === 0}>
            <UserPlus className="me-2 size-4" />
            Add member
          </Button>
        </CardHeader>
        <CardTable>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Order</TableHead>
                <TableHead>User</TableHead>
                <TableHead className="w-[200px]">Auto-assign (round robin)</TableHead>
                <TableHead className="w-[80px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-6 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-40" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-8 w-8" /></TableCell>
                  </TableRow>
                ))
              ) : members.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={4} className="text-center text-muted-foreground py-8">
                    No members. Add users to this team for round-robin assignment.
                  </TableCell>
                </TableRow>
              ) : (
                members.map((member: TeamMember, index: number) => {
                  const includeInRR = member.include_in_round_robin ?? true;
                  return (
                    <TableRow key={member.id}>
                      <TableCell className="text-muted-foreground">
                        {member.sort_order ?? index + 1}
                      </TableCell>
                      <TableCell>{displayUser(userMap.get(member.user_id), member.user_id)}</TableCell>
                      <TableCell>
                        <Switch
                          size="sm"
                          checked={includeInRR}
                          onCheckedChange={(checked) =>
                            roundRobinMutation.mutate({
                              userId: member.user_id,
                              includeInRoundRobin: checked,
                            })
                          }
                          aria-label="Include in round robin"
                        />
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="text-destructive hover:text-destructive"
                          onClick={() => removeMutation.mutate(member.user_id)}
                          disabled={removeMutation.isPending}
                          aria-label="Remove member"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </CardTable>
      </Card>

      <Dialog
        open={addOpen}
        onOpenChange={(open) => {
          setAddOpen(open);
          if (!open) setSelectedUserIds(new Set());
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Add members</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <SearchableMultiSelect
                value={Array.from(selectedUserIds)}
                onChange={(next) => setSelectedUserIds(new Set(next))}
                placeholder="Select users"
                emptyMessage="No user found."
                // Chips below already list the picks, so the trigger keeps its terse summary.
                renderTriggerLabel={(sel) =>
                  sel.length === 0
                    ? 'Select users'
                    : sel.length === 1
                      ? displayUser(
                          users.find((u) => u.id === sel[0].value),
                          sel[0].value,
                        )
                      : `${sel.length} users selected`
                }
                options={availableUsers.map((u) => ({
                  value: u.id,
                  label: displayUser(u, u.id),
                  searchText: `${u.name ?? ''} ${u.email}`.trim(),
                }))}
              />
            </div>
            {selectedCount > 0 && (
              <div className="flex flex-wrap gap-2 rounded-md border px-3 py-2">
                {Array.from(selectedUserIds).map((userId) => {
                  const u = users.find((x) => x.id === userId);
                  return (
                    <Badge
                      key={userId}
                      variant="secondary"
                      className="gap-1 pr-1 font-normal"
                    >
                      {displayUser(u, userId)}
                      <button
                        type="button"
                        onClick={() => toggleUser(userId)}
                        className="ml-0.5 rounded-full hover:bg-muted p-0.5"
                        aria-label={'Remove ' + displayUser(u, userId)}
                      >
                        <X className="size-3" />
                      </button>
                    </Badge>
                  );
                })}
              </div>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setAddOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={handleAdd}
                disabled={selectedCount === 0 || isAdding}
              >
                {isAdding && <LoaderCircleIcon className="animate-spin me-2 size-4" />}
                Add {selectedCount > 0 ? selectedCount : ''} member{selectedCount !== 1 ? 's' : ''}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
