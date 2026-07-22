'use client';

import { RiCheckboxCircleFill, RiErrorWarningFill } from '@remixicon/react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { toast } from 'sonner';
import { zodResolver } from '@hookform/resolvers/zod';
import { Alert, AlertDescription, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
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
} from '@/components/ui/form';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import { LoaderCircleIcon } from 'lucide-react';
import type { Team } from '../types/team.types';
import { createTeam, updateTeam, getTeams } from '../services/teamService';
import { TeamSchema, type TeamSchemaType } from '../forms/team-schema';

const NO_PARENT = '__none__';

export default function TeamEditDialog({
  open,
  closeDialog,
  team,
}: {
  open: boolean;
  closeDialog: () => void;
  team: Team | null;
}) {
  const queryClient = useQueryClient();
  const form = useForm<TeamSchemaType>({
    resolver: zodResolver(TeamSchema),
    defaultValues: { name: '', description: '', parent_team_id: null },
    mode: 'onSubmit',
  });

  const { data: teams = [] } = useQuery({
    queryKey: ['user-management-teams'],
    queryFn: getTeams,
    enabled: open,
    staleTime: 60 * 1000,
  });

  // A team cannot be its own parent (server also rejects deeper cycles).
  const parentOptions = teams.filter((t) => t.id !== team?.id);

  useEffect(() => {
    if (open) {
      form.reset({
        name: team?.name ?? '',
        description: team?.description ?? '',
        parent_team_id: team?.parent_team_id ?? null,
      });
    }
  }, [form, open, team]);

  const mutation = useMutation({
    mutationFn: async (values: TeamSchemaType) => {
      const payload = {
        ...values,
        parent_team_id: values.parent_team_id ?? null,
      };
      if (team?.id) return updateTeam(team.id, payload);
      return createTeam(payload);
    },
    onSuccess: () => {
      const message = team ? 'Team updated successfully' : 'Team created successfully';
      toast.custom(
        () => (
          <Alert variant="mono" icon="success">
            <AlertIcon>
              <RiCheckboxCircleFill />
            </AlertIcon>
            <AlertTitle>{message}</AlertTitle>
          </Alert>
        ),
        { position: 'top-center', duration: 5000 },
      );
      queryClient.invalidateQueries({ queryKey: ['user-management-teams'] });
      closeDialog();
    },
    onError: (error: Error) => {
      toast.custom(
        () => (
          <Alert variant="mono" icon="destructive">
            <AlertIcon>
              <RiErrorWarningFill />
            </AlertIcon>
            <AlertTitle>{error.message}</AlertTitle>
          </Alert>
        ),
        { position: 'top-center' },
      );
    },
  });

  return (
    <Dialog open={open} onOpenChange={closeDialog}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{team ? 'Edit Team' : 'Create Team'}</DialogTitle>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((v) => mutation.mutate(v))} className="space-y-4">
            {mutation.isError && (
              <Alert variant="destructive">
                <AlertDescription>{mutation.error?.message}</AlertDescription>
              </Alert>
            )}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input placeholder="Team name" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="description"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Description (optional)</FormLabel>
                  <FormControl>
                    <Textarea
                      placeholder="Brief description"
                      className="resize-none"
                      rows={3}
                      {...field}
                      value={field.value ?? ''}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="parent_team_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Parent team (optional)</FormLabel>
                  <FormControl>
                    <SearchableSelect
                      value={field.value ?? NO_PARENT}
                      onChange={(v) => field.onChange(v === NO_PARENT ? null : v)}
                      placeholder="No parent team"
                      options={[
                        { value: NO_PARENT, label: 'No parent team' },
                        ...parentOptions.map((t) => ({ value: t.id, label: t.name })),
                      ]}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <DialogFooter>
              <Button type="button" variant="outline" onClick={closeDialog}>
                Cancel
              </Button>
              <Button type="submit" disabled={mutation.isPending}>
                {mutation.isPending && <LoaderCircleIcon className="animate-spin me-2" />}
                {team ? 'Save' : 'Create'}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
