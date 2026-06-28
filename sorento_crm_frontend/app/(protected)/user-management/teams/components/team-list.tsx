'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Plus, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardFooter, CardHeader } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import type { Team } from '../types/team.types';
import { getTeams } from '../services/teamService';
import TeamEditDialog from './team-edit-dialog';
import TeamDeleteDialog from './team-delete-dialog';
import TeamTree from './team-tree';

export default function TeamList() {
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [selectedTeam, setSelectedTeam] = useState<Team | null>(null);
  const [query, setQuery] = useState('');

  const { data: teams = [], isLoading } = useQuery({
    queryKey: ['user-management-teams'],
    queryFn: getTeams,
    staleTime: 60 * 1000,
  });

  return (
    <>
      <Card>
        <CardHeader className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="relative w-full sm:max-w-xs">
            <Search className="text-muted-foreground absolute start-2.5 top-1/2 size-4 -translate-y-1/2" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search teams…"
              className="ps-8 pe-8"
            />
            {query && (
              <button
                type="button"
                onClick={() => setQuery('')}
                className="text-muted-foreground hover:text-foreground absolute end-2 top-1/2 -translate-y-1/2"
                aria-label="Clear search"
              >
                <X className="size-4" />
              </button>
            )}
          </div>
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

        <div className="border-t">
          <p className="text-muted-foreground border-b px-4 py-2 text-xs">
            Drag a row by its handle onto another team to nest it; drop on the top zone to detach.
          </p>
          {isLoading ? (
            <div className="space-y-2 p-4">
              {Array.from({ length: 6 }).map((_, i) => (
                <Skeleton key={i} className="h-10 w-full" />
              ))}
            </div>
          ) : (
            <TeamTree
              teams={teams}
              query={query}
              onEdit={(t) => {
                setSelectedTeam(t);
                setEditOpen(true);
              }}
              onDelete={(t) => {
                setSelectedTeam(t);
                setDeleteOpen(true);
              }}
            />
          )}
        </div>

        {!isLoading && teams.length > 0 && (
          <CardFooter className="text-muted-foreground text-sm">
            {teams.length} team{teams.length !== 1 ? 's' : ''}
          </CardFooter>
        )}
      </Card>

      <TeamEditDialog open={editOpen} closeDialog={() => setEditOpen(false)} team={selectedTeam} />
      <TeamDeleteDialog
        open={deleteOpen}
        closeDialog={() => setDeleteOpen(false)}
        team={selectedTeam}
      />
    </>
  );
}
