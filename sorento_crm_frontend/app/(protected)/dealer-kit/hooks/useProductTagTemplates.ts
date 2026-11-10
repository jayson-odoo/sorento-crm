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
  assignTemplateToProducts,
  isPriceTagFamily,
  listTemplateProductIds,
  listComboTagTemplates,
  listProductTagTemplates,
  previewTemplateAssignment,
  setComboTagTemplates,
  setProductTagTemplates,
  type TagTemplateLinks,
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
    mutationFn: (links: TagTemplateLinks) => setProductTagTemplates(productId, links),
    onSuccess: (rows) => {
      queryClient.setQueryData(productTagTemplatesKey(productId), rows);
      toast.success('Price tag templates saved');
    },
    onError: (error: Error) => toast.error(error.message),
  });
}

export const comboTagTemplatesKey = (comboId: string) =>
  ['combo-tag-templates', comboId] as const;

export function useComboTagTemplates(comboId: string, enabled = true) {
  return useQuery({
    queryKey: comboTagTemplatesKey(comboId),
    queryFn: () => listComboTagTemplates(comboId),
    enabled: enabled && !!comboId,
  });
}

/** A combo's template links: saved once a new combo exists (the combo modal) and from the
 *  combo's own block on the product page. */
export function useSetComboTagTemplates() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ combo_id, ...links }: TagTemplateLinks & { combo_id: string }) =>
      setComboTagTemplates(combo_id, links),
    onSuccess: (rows, { combo_id }) => {
      queryClient.setQueryData(comboTagTemplatesKey(combo_id), rows);
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
    // Family then name, the order this picker always had: with no sort the list endpoint now
    // answers the Tag Templates list's manual (drag) order (TAG-TEMPLATE-DUPLICATE item 6).
    queryFn: async () =>
      (await listTemplates())
        .filter((t) => isPriceTagFamily(t.family))
        .sort((a, b) => a.family.localeCompare(b.family) || a.name.localeCompare(b.name)),
    enabled,
  });
}

/** PRICETAG-TEMPLATE-PRODUCTS: the products that use a template (the designer's ticks). */
export const templateProductIdsKey = (templateId: string) =>
  ['tag-template-product-ids', templateId] as const;

export function useTemplateProductIds(
  templateId: string,
  enabled = true,
  { fresh = false }: { fresh?: boolean } = {},
) {
  return useQuery({
    queryKey: templateProductIdsKey(templateId),
    queryFn: () => listTemplateProductIds(templateId),
    enabled: enabled && !!templateId,
    // The Products dialog diffs its Save against this list, so it always reads it fresh.
    ...(fresh ? { refetchOnMount: 'always' as const } : {}),
  });
}

/** Link the template to the picked products; the toast is the caller's, after the whole Save. */
export function useLinkTemplateProducts(templateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (productIds: string[]) => assignTemplateToProducts(templateId, productIds),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['product-tag-templates'] });
      void queryClient.invalidateQueries({ queryKey: templateProductIdsKey(templateId) });
    },
    onError: (error: Error) => toast.error(error.message),
  });
}
