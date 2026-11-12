'use client';

import { useQuery } from '@tanstack/react-query';
import { listPublishedTemplates } from '../services/tagTemplateService';

/** Every PUBLISHED tag template with its published doc (what a request prints from). */
export function usePublishedTagTemplates(enabled = true) {
  return useQuery({
    queryKey: ['tag-templates', 'published'],
    queryFn: listPublishedTemplates,
    enabled,
    staleTime: 60_000,
  });
}
