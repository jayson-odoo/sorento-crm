import { useRouter } from 'next/navigation';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import {
  assignServiceJob,
  confirmServiceJob,
  getComplaintServiceJobs,
  getDispatchBoard,
  getServiceJob,
  getServiceJobs,
  raiseServiceJob,
  transitionServiceJob,
  type ServiceJobsListParams,
} from '../services/serviceJobService';
import { getTechniciansSelect } from '../../technicians/services/technicianService';
import { serviceJobsListQueryKey } from '../lib/listQuery';
import type { ConfirmJobValues, TransitionValues } from '../types/serviceJob.types';

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

export function useComplaintServiceJobs(complaintId: string | null) {
  return useQuery({
    queryKey: ['complaint-service-jobs', complaintId],
    queryFn: () => getComplaintServiceJobs(complaintId as string),
    enabled: !!complaintId,
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
    for (const key of ['service-jobs', 'service-job', 'complaint-service-jobs', 'service-job-board']) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };
}

export function useRaiseServiceJob() {
  const invalidate = useInvalidateJobs();
  const router = useRouter();
  return useMutation({
    mutationFn: (complaintId: string) => raiseServiceJob(complaintId),
    onSuccess: ({ job, created }) => {
      invalidate();
      if (created) toast.success('Service job raised');
      else toast.warning('This complaint already has a live service job.');
      router.push(`/complaint-management/service-jobs/${job.id}`);
    },
    onError: (error: Error) => toast.error(error.message || 'Failed to raise the service job'),
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
