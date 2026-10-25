import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { LIST_QUERY_OPTIONS } from '@/lib/list-query/options';
import type { ProjectRegisterBody } from '../../_shared/types/project.types';
import {
  approveProjectRegistration,
  getProjectRegistration,
  getProjectRegistrations,
  rejectProjectRegistration,
  type ProjectRegistrationListParams,
} from '@/services/projectRegistrationService';

const LIST_KEY = 'project-registrations';

export function useProjectRegistrations(params: ProjectRegistrationListParams) {
  return useQuery({
    ...LIST_QUERY_OPTIONS,
    queryKey: [
      LIST_KEY,
      params.pageIndex,
      params.pageSize,
      params.sorting,
      params.searchQuery,
      params.status,
    ],
    queryFn: () => getProjectRegistrations(params),
    retry: 1,
  });
}

export function useProjectRegistration(id: string | null) {
  return useQuery({
    queryKey: ['project-registration', id],
    queryFn: () => {
      if (!id) throw new Error('Registration ID is required');
      return getProjectRegistration(id);
    },
    enabled: !!id,
    retry: 1,
  });
}

function useInvalidateRegistrations() {
  const queryClient = useQueryClient();
  return (id: string) => {
    void queryClient.invalidateQueries({ queryKey: [LIST_KEY] });
    void queryClient.invalidateQueries({ queryKey: ['project-registration', id] });
    // An approval creates a project.
    void queryClient.invalidateQueries({ queryKey: ['projects'] });
  };
}

export function useApproveProjectRegistration(id: string) {
  const invalidate = useInvalidateRegistrations();
  return useMutation({
    mutationFn: (payload: ProjectRegisterBody) => approveProjectRegistration(id, payload),
    onSuccess: (registration) => {
      invalidate(id);
      toast.success(
        registration.project_code
          ? `${registration.project_code} registered`
          : 'Registration approved',
      );
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useRejectProjectRegistration(id: string) {
  const invalidate = useInvalidateRegistrations();
  return useMutation({
    mutationFn: (reason: string) => rejectProjectRegistration(id, reason),
    onSuccess: () => {
      invalidate(id);
      toast.success('Registration rejected');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
