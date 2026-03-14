'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { listNumberingRules, updateNumberingRule } from '../services/numberingRuleService';
import type { DocumentNumberingRuleUpdate } from '../types/numberingRule.types';

const QUERY_KEY = ['numbering-rules'];

export function useNumberingRules() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: listNumberingRules,
  });
}

export function useUpdateNumberingRule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ docType, data }: { docType: string; data: DocumentNumberingRuleUpdate }) =>
      updateNumberingRule(docType, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}
