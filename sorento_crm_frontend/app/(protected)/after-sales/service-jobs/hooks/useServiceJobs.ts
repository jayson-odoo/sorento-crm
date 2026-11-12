import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  assignServiceJob,
  confirmServiceJob,
  getDispatchBoard,
  getServiceJob,
  getServiceJobs,
  createServiceJob,
  updateServiceJob,
  searchComplaintNumbers,
  transitionServiceJob,
  type ServiceJobsListParams,
} from '../services/serviceJobService';
import { getTechniciansSelect } from '../../technicians/services/technicianService';
import { serviceJobsListQueryKey } from '../lib/listQuery';
import type { ConfirmJobValues, ServiceJobFormValues, TransitionValues } from '../types/serviceJob.types';

export function useServiceJobsList(params: ServiceJobsListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: serviceJobsListQueryKey(params),
    queryFn: () => getServiceJobs(params),
    staleTime: Infinity,
    gcTime: 1000 * 60 * 60,
    retry: 1,
  });
}

export function useServiceJob(id: string | null) {
  return useQuery({
    queryKey: ['service-job', id],
    queryFn: () => getServiceJob(id as string),
    enabled: !!id,
    retry: 1,
  });
}

export function useDispatchBoard(day: string) {
  return useQuery({
    queryKey: ['service-job-board', day],
    queryFn: () => getDispatchBoard(day),
    retry: 1,
  });
}

export function useTechniciansSelect() {
  return useQuery({
    queryKey: ['technicians-select'],
    queryFn: getTechniciansSelect,
    staleTime: 1000 * 60,
  });
}

function useInvalidateJobs() {
  const queryClient = useQueryClient();
  return () => {
    for (const key of ['service-jobs', 'service-job', 'service-job-board']) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function useServiceJobMutations() {
  const invalidate = useInvalidateJobs();
  const create = useMutation({
    mutationFn: (values: ServiceJobFormValues) => createServiceJob(values),
    onSuccess: () => {
      invalidate();
      toast.success('Service job created');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to create the service job'),
  });
  const update = useMutation({
    mutationFn: ({ id, values }: { id: string; values: ServiceJobFormValues }) => updateServiceJob(id, values),
    onSuccess: () => {
      invalidate();
      toast.success('Service job updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update the service job'),
  });
  return { create, update };
}

export function useComplaintNumberSearch(query: string, enabled: boolean) {
  return useQuery({
    queryKey: ['service-job-complaint-search', query],
    queryFn: () => searchComplaintNumbers(query),
    enabled,
    staleTime: 30_000,
  });
}

export function useServiceJobActions() {
  const invalidate = useInvalidateJobs();
  const onError = (error: Error) => toast.error(error.message || 'Failed to update the service job');
  const confirm = useMutation({
    mutationFn: ({ id, values }: { id: string; values: ConfirmJobValues }) =>
      confirmServiceJob(id, values),
    onSuccess: () => {
      invalidate();
      toast.success('Date confirmed');
    },
    onError,
  });
  const assign = useMutation({
    mutationFn: ({ id, technicianId }: { id: string; technicianId: string }) =>
      assignServiceJob(id, technicianId),
    onSuccess: () => {
      invalidate();
      toast.success('Technician assigned');
    },
    onError,
  });
  const transition = useMutation({
    mutationFn: ({ id, values }: { id: string; values: TransitionValues }) =>
      transitionServiceJob(id, values),
    onSuccess: () => {
      invalidate();
      toast.success('Service job updated');
    },
    onError,
  });
  return { confirm, assign, transition };
}
