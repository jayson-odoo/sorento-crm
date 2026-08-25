/**
 * How a sales-agent row got here, in words.
 *
 * `import` is a row an order upload created on meeting a code nobody held - the rows the
 * captain comes to this page to classify - so it is named as its own answer rather than
 * folded into "Manual". Shared by the list column and the record's Source field so one row
 * cannot read two ways on two screens one click apart.
 */
import type { SalesAgent } from '../types/salesAgent.types';

export const SALES_AGENT_SOURCE_LABEL: Record<SalesAgent['source'], string> = {
  autocount: 'AutoCount',
  manual: 'Manual',
  import: 'Import',
};

export function salesAgentSourceLabel(source: string | null | undefined): string {
  if (!source) return 'Manual';
  return SALES_AGENT_SOURCE_LABEL[source as SalesAgent['source']] ?? source;
}
