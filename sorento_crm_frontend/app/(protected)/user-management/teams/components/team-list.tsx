'use client';

import { useQuery } from '@tanstack/react-query';
import { Ellipsis, Plus, Users } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader, CardTable } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import type { Team } from '../types/team.types';
import { getTeams } from '../services/teamService';
import TeamEditDialog from './team-edit-dialog';
import TeamDeleteDialog from './team-delete-dialog';

export default function TeamList() {
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);

  const { data: teams = [], isLoading } = useQuery({
    queryKey: ['user-management-teams'],
    queryFn: getTeams,
    staleTime: 60 * 1000,
  });

  return (
    <>
      <Card>
        <CardHeader className="flex flex-row items-center justify-between py-5">
          <h3 className="text-lg font-medium">Teams</h3>
          <Button
            onClick={() => {
              setSelectedTeam(null);
              setEditOpen(true);
            }}
          >
            <Plus className="me-2 size-4" />
            Create team
          </Button>
        </CardHeader>
        <CardTable>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="w-[100px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {isLoading ? (
                Array.from({ length: 5 }).map((_, i) => (
                  <TableRow key={i}>
                    <TableCell>
                      <Skeleton className="h-6 w-32" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-6 w-48" />
                    </TableCell>
                    <TableCell>
                      <Skeleton className="h-8 w-8" />
                    </TableCell>
                  </TableRow>
                ))
              ) : teams.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3} className="text-center text-muted-foreground py-8">
                    No teams yet. Create a team to use for round-robin assignees.
                  </TableCell>
                </TableRow>
              ) : (
                teams.map((team) => (
                  <TableRow key={team.id}>
                    <TableCell className="font-medium">{team.name}</TableCell>
                    <TableCell className="text-muted-foreground max-w-md truncate">
                      {team.description ?? '—'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" asChild>
                          <Link href={`/user-management/teams/${team.id}`}>
                            <Users className="me-1 size-4" />
                            Members
                          </Link>
                        </Button>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button className="h-8 w-8" mode="icon" variant="ghost" size="icon">
                              <Ellipsis />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onClick={() => {
                                setSelectedTeam(team);
                                setEditOpen(true);
                              }}
                            >
                              Edit team
                            </DropdownMenuItem>
                            <DropdownMenuSeparator />
                            <DropdownMenuItem
                              variant="destructive"
                              onClick={() => {
                                setSelectedTeam(team);
                                setDeleteOpen(true);
                              }}
                            >
                              Delete team
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardTable>
        {!isLoading && teams.length > 0 && (
          <CardFooter className="text-muted-foreground text-sm">
            {teams.length} team{teams.length !== 1 ? 's' : ''}
          </CardFooter>
        )}
      </Card>

      <TeamEditDialog
        open={editOpen}
        closeDialog={() => setEditOpen(false)}
        team={selectedTeam}
      />
      <TeamDeleteDialog
        open={deleteOpen}
        closeDialog={() => setDeleteOpen(false)}
        team={selectedTeam}
      />
    </>
  );
}
