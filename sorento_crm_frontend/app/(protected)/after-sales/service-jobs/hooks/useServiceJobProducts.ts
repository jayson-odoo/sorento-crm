import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import {
  addServiceJobProduct,
  getServiceJobProducts,
  updateServiceJobProduct,
} from '../services/serviceJobService';
import type { ServiceJobProductValues } from '../types/serviceJob.types';

export const jobProductsKey = (jobId: string) => ['service-job-products', jobId] as const;

export function useServiceJobProducts(jobId: string) {
  return useQuery({
    queryKey: jobProductsKey(jobId),
    queryFn: () => getServiceJobProducts(jobId),
    retry: 1,
  });
}

export function useServiceJobProductMutations(jobId: string) {
  const queryClient = useQueryClient();
  // The job carries the warranty answer and the list its summary: both move with a line.
  const invalidate = () => {
    for (const key of ['service-job-products', 'service-job', 'service-jobs']) {
      void queryClient.invalidateQueries({ queryKey: [key] });
    }
  };
  const add = useMutation({
    mutationFn: (values: ServiceJobProductValues) => addServiceJobProduct(jobId, values),
    onSuccess: () => {
      invalidate();
      toast.success('Product added');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to add the product'),
  });
  const update = useMutation({
    mutationFn: ({ lineId, values }: { lineId: string; values: Partial<Omit<ServiceJobProductValues, 'product_id'>> }) =>
      updateServiceJobProduct(jobId, lineId, values),
    onSuccess: () => {
      invalidate();
      toast.success('Product updated');
    },
    onError: (e: Error) => toast.error(e.message || 'Failed to update the product'),
  });
  return { add, update };
}
