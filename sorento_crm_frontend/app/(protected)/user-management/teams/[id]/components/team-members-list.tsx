'use client';

import { useCallback, useMemo, useState } from 'react';
import { ChevronsUpDown, LoaderCircleIcon, Trash2, UserPlus, X } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Card, CardHeader, CardTable } from '@/components/ui/card';
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from '@/components/ui/command';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
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
import { useTeamMembers, useRemoveTeamMember } from '../../hooks/use-team-members';
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
  const [userSelectOpen, setUserSelectOpen] = useState(false);
  const [selectedUserIds, setSelectedUserIds] = useState<Set<string>>(new Set());
  const [isAdding, setIsAdding] = useState(false);

  const { data: members = [], isLoading } = useTeamMembers(teamId);
  const removeMutation = useRemoveTeamMember(teamId);

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
      setUserSelectOpen(false);
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
                <TableHead className="w-[80px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 3 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell><Skeleton className="h-6 w-10" /></TableCell>
                    <TableCell><Skeleton className="h-6 w-40" /></TableCell>
                    <TableCell><Skeleton className="h-8 w-8" /></TableCell>
                  </TableRow>
                ))
              ) : members.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                    No members. Add users to this team for round-robin assignment.
                  </TableCell>
                </TableRow>
              ) : (
                members.map((member: TeamMember, index: number) => (
                  <TableRow key={member.id}>
                    <TableCell className="text-muted-foreground">
                      {member.sort_order ?? index + 1}
                    </TableCell>
                    <TableCell>{displayUser(userMap.get(member.user_id), member.user_id)}</TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-destructive hover:text-destructive"
                        onClick={() => removeMutation.mutate(member.user_id)}
                        disabled={removeMutation.isPending}
                      >
                        <Trash2 className="size-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))
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
              <Popover open={userSelectOpen} onOpenChange={setUserSelectOpen}>
                <PopoverTrigger asChild>
                  <Button
                    variant="outline"
                    role="combobox"
                    aria-expanded={userSelectOpen}
                    className="w-full justify-between font-normal"
                  >
                    {selectedCount === 0
                      ? 'Select users'
                      : selectedCount === 1
                        ? displayUser(
                            users.find((u) => u.id === Array.from(selectedUserIds)[0]),
                            Array.from(selectedUserIds)[0],
                          )
                        : `${selectedCount} users selected`}
                    <ChevronsUpDown className="ms-2 size-4 shrink-0 opacity-50" />
                  </Button>
                </PopoverTrigger>
              <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
                <Command>
                  <CommandInput placeholder="Search by name or email..." />
                  <CommandList>
                    <CommandEmpty>No user found.</CommandEmpty>
                    <CommandGroup>
                      {availableUsers.map((u) => (
                        <CommandItem
                          key={u.id}
                          value={`${u.name ?? ''} ${u.email}`.trim()}
                          onSelect={() => toggleUser(u.id)}
                        >
                          <Checkbox
                            checked={selectedUserIds.has(u.id)}
                            className="pointer-events-none me-2"
                          />
                          {displayUser(u, u.id)}
                        </CommandItem>
                      ))}
                    </CommandGroup>
                  </CommandList>
                </Command>
              </PopoverContent>
            </Popover>
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
