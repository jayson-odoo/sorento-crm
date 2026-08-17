import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';

import { getMemberBrands, setMemberBrands } from '../services/memberBrandService';

/** A team-member's brand tags (per (team, user) membership). Empty = serves all. */
export function useMemberBrands(teamId: string, userId: string) {
  return useQuery({
    queryKey: ['member-brands', teamId, userId],
    queryFn: () => getMemberBrands(teamId, userId),
    enabled: !!teamId && !!userId,
  });
}

export function useSetMemberBrands(teamId: string, userId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (codes: string[]) => setMemberBrands(teamId, userId, codes),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['member-brands', teamId, userId] });
      toast.success('Brands updated');
    },
    onError: (e: Error) => toast.error(e.message),
  });
}
