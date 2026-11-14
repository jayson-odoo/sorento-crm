import { useLookupSetOptions } from '@/hooks/useLookupSetOptions';
import { leadSourceLabel } from '../lib/leadSource';

/** A project's lead source as the label people read (PS-REGISTRATION-V3), from its editable list. */
export function useLeadSourceLabel(value?: string | null): string | null {
  const sources = useLookupSetOptions('project_lead_source');
  return leadSourceLabel(sources.data, value);
}
