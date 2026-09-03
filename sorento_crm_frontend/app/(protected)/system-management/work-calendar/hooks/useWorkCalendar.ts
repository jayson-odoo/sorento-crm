import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import type { DataGridApiFetchParams } from '@/components/ui/data-grid';
import type { PublicHolidayFormData, WorkCalendarConfig } from '../types/workCalendar.types';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  getWorkCalendarConfig,
  updateWorkCalendarConfig,
  getPublicHolidays,
  createPublicHoliday,
  updatePublicHoliday,
  deletePublicHoliday,
} from '../services/workCalendarService';

export function useWorkCalendarConfig() {
  return useQuery({
    queryKey: ['work-calendar-config'],
    queryFn: () => getWorkCalendarConfig(),
    staleTime: 1000 * 60 * 10,
    retry: 1,
  });
}

export function useUpdateWorkCalendarConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: Partial<WorkCalendarConfig>) => updateWorkCalendarConfig(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['work-calendar-config'] });
      toast.success('Work calendar updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update work calendar'),
  });
}

export function usePublicHolidays(params: DataGridApiFetchParams & { year?: number }) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: ['public-holidays', params.pageIndex, params.pageSize, params.year],
    queryFn: () => getPublicHolidays(params),
    staleTime: 1000 * 60,
    retry: 1,
  });
}

export function useCreatePublicHoliday() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: PublicHolidayFormData) => createPublicHoliday(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['public-holidays'] });
      toast.success('Public holiday created');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to create public holiday'),
  });
}

export function useUpdatePublicHoliday() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: string; data: Partial<PublicHolidayFormData> }) =>
      updatePublicHoliday(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['public-holidays'] });
      toast.success('Public holiday updated');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to update public holiday'),
  });
}

export function useDeletePublicHoliday() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deletePublicHoliday(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['public-holidays'] });
      toast.success('Public holiday deleted');
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to delete public holiday'),
  });
}
