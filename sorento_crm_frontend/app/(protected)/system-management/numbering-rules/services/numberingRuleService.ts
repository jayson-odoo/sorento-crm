import { apiFetch } from '@/lib/api';
import type { DocumentNumberingRule, DocumentNumberingRuleUpdate } from '../types/numberingRule.types';

export async function listNumberingRules(): Promise<DocumentNumberingRule[]> {
  const response = await apiFetch('/api/v1/system/numbering-rules');
  if (!response.ok) throw new Error('Failed to fetch numbering rules');
  return response.json();
}

export async function getNumberingRule(docType: string): Promise<DocumentNumberingRule> {
  const response = await apiFetch(`/api/v1/system/numbering-rules/${encodeURIComponent(docType)}`);
  if (!response.ok) throw new Error('Failed to fetch numbering rule');
  return response.json();
}

export async function updateNumberingRule(
  docType: string,
  data: DocumentNumberingRuleUpdate,
): Promise<DocumentNumberingRule> {
  const response = await apiFetch(`/api/v1/system/numbering-rules/${encodeURIComponent(docType)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!response.ok) throw new Error('Failed to update numbering rule');
  return response.json();
}
