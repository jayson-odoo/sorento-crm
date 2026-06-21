import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import {
  fetchSessions,
  revokeSession,
  revokeOtherSessions,
  forceLogoutUser,
  type SessionInfo,
} from '@/services/sessionService';

const SESSIONS_KEY = ['auth', 'sessions'];

export function useSessionsQuery() {
  return useQuery<SessionInfo[]>({
    queryKey: SESSIONS_KEY,
    queryFn: fetchSessions,
  });
}

export function useRevokeSessionMutation() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: revokeSession,
    onSuccess: () => {
      toast.success('Device signed out.');
      qc.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
    onError: (err) => toast.error(err.message),
  });
}

export function useRevokeOtherSessionsMutation() {
  const qc = useQueryClient();
  return useMutation<{ count: number }, Error, void>({
    mutationFn: revokeOtherSessions,
    onSuccess: (data) => {
      toast.success(`Signed out ${data.count} other device(s).`);
      qc.invalidateQueries({ queryKey: SESSIONS_KEY });
    },
    onError: (err) => toast.error(err.message),
  });
}

export function useForceLogoutUserMutation() {
  return useMutation<{ count: number }, Error, string>({
    mutationFn: forceLogoutUser,
    onSuccess: (data) => toast.success(`Signed out ${data.count} device(s).`),
    onError: (err) => toast.error(err.message),
  });
}
