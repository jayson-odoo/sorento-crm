import { useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  addCustomerGroupCustomers,
  createCustomerGroup,
} from '@/app/(protected)/order-management/customer-groups/services/customerGroupService';

export type AssignCustomerGroupInput = {
  customerIds: string[];
  /** An existing group... */
  group?: { id: string; name: string };
  /** ...or a name to create first. */
  newName?: string;
};

/** Put the picked customers into one group, creating the group first when given a new name. */
export function useAssignCustomerGroup() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ customerIds, group, newName }: AssignCustomerGroupInput) => {
      const target = group ?? (await createCustomerGroup({ name: newName ?? '' }));
      await addCustomerGroupCustomers(target.id, customerIds);
      return { name: target.name, count: customerIds.length };
    },
    onSuccess: ({ name, count }) => {
      void queryClient.invalidateQueries({ queryKey: ['customers'] });
      void queryClient.invalidateQueries({ queryKey: ['customer-groups'] });
      toast.success(`${count} customer${count === 1 ? '' : 's'} set to group ${name}`);
    },
    onError: (error: Error) => {
      toast.error(error.message || 'Failed to set customer group');
    },
  });
}
