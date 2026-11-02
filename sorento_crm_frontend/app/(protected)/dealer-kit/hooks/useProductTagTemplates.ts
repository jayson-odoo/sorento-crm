'use client';

/**
 * Product <-> tag template links and the bulk assignment
 * (PRICETAG-TEMPLATE-PER-PRODUCT): UI -> these hooks -> productTagTemplateService.
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from '@/lib/toast';
import { listTemplates } from '../services/tagTemplateService';
import {
  assignTemplate,
  isPriceTagFamily,
  listProductTagTemplates,
  previewTemplateAssignment,
  setProductTagTemplates,
  type TemplateAssignAction,
  type TemplateAssignFilter,
} from '../services/productTagTemplateService';

export const productTagTemplatesKey = (productId: string) =>
  ['product-tag-templates', productId] as const;

export function useProductTagTemplates(productId: string, enabled = true) {
  return useQuery({
    queryKey: productTagTemplatesKey(productId),
    queryFn: () => listProductTagTemplates(productId),
    enabled: enabled && !!productId,
  });
}

export function useSetProductTagTemplates(productId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (templateIds: string[]) => setProductTagTemplates(productId, templateIds),
    onSuccess: (rows) => {
      queryClient.setQueryData(productTagTemplatesKey(productId), rows);
      toast.success('Price tag templates saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export function useTemplateAssignPreview(
  templateId: string | null,
  filter: TemplateAssignFilter,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ['tag-template-assign-preview', templateId, filter],
    queryFn: () => previewTemplateAssignment(templateId as string, filter),
    enabled: enabled && !!templateId,
  });
}

export function useAssignTemplate(templateId: string | null) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ filter, action }: { filter: TemplateAssignFilter; action: TemplateAssignAction }) =>
      assignTemplate(templateId as string, filter, action),
    onSuccess: ({ changed }, { action }) => {
      void queryClient.invalidateQueries({ queryKey: ['product-tag-templates'] });
      void queryClient.invalidateQueries({ queryKey: ['tag-template-assign-preview'] });
      const noun = changed === 1 ? 'product' : 'products';
      toast.success(action === 'add' ? `Added to ${changed} ${noun}` : `Removed from ${changed} ${noun}`);
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

/** Every price tag template (published or not), for the product page's picker. */
export function usePriceTagTemplateOptions(enabled: boolean) {
  return useQuery({
    queryKey: ['tag-templates', 'price-tag-options'],
    queryFn: async () => (await listTemplates()).filter((t) => isPriceTagFamily(t.family)),
    enabled,
  });
}
