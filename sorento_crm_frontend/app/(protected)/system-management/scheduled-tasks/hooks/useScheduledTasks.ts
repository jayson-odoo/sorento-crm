'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  getScheduledTasks,
  getScheduledTask,
  getScheduledTaskRuns,
  updateScheduledTask,
  runScheduledTaskNow,
} from '../services/scheduledTaskService';
import type { ScheduledTaskUpdateBody } from '../types/scheduledTask.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';

export function useScheduledTasks() {
  return useQuery({
    queryKey: ['scheduled-tasks'],
    queryFn: getScheduledTasks,
    staleTime: 1000 * 60 * 2,
  });
}

export function useScheduledTask(taskId: string | null) {
  return useQuery({
    queryKey: ['scheduled-task', taskId],
    queryFn: () => getScheduledTask(taskId!),
    enabled: !!taskId,
    staleTime: 1000 * 60 * 2,
  });
}

export function useScheduledTaskRuns(taskId: string | null, page: number = 1, limit: number = 50) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['scheduled-task-runs', taskId, page, limit],
    queryFn: () => getScheduledTaskRuns(taskId!, page, limit),
    enabled: !!taskId,
    staleTime: 1000 * 30,
  });
}

export function useUpdateScheduledTask(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ScheduledTaskUpdateBody) => updateScheduledTask(taskId, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['scheduled-task', taskId] });
    },
  });
}

export function useRunScheduledTaskNow(taskId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => runScheduledTaskNow(taskId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-tasks'] });
      queryClient.invalidateQueries({ queryKey: ['scheduled-task', taskId] });
      queryClient.invalidateQueries({ queryKey: ['scheduled-task-runs', taskId] });
    },
  });
}
