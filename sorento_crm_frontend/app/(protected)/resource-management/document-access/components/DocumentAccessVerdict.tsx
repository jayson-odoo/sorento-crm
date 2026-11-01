'use client';

import { Badge } from '@/components/ui/badge';
import type {
  AccessTypeColumn,
  ContactBlock,
  DocumentAccessDocument,
  DocumentAccessRow,
  PreviewContact,
} from '../types/documentAccess.types';

type Tone = 'success' | 'warning' | 'destructive' | 'secondary' | 'info';

const BLOCKED_TEXT: Record<ContactBlock, string> = {
  no_access_type: 'No access type',
  no_company: 'No company',
  ambiguous: 'More than one contact record',
};

function plural(n: number) {
  return n.toLocaleString('en-US');
}

/** The pill text and tone for one grid row under the previewed contact. */
export function rowVerdict(
  row: DocumentAccessRow,
  contact: PreviewContact,
  accessTypes: AccessTypeColumn[],
): { text: string; tone: Tone } | null {
  const pv = row.preview;
  if (!pv) return null;
  switch (pv.verdict) {
    case 'no_access_type':
    case 'no_company':
    case 'ambiguous':
      return { text: BLOCKED_TEXT[pv.verdict], tone: 'destructive' };
    case 'staff_reads':
      return { text: `Reads ${plural(pv.total)} of ${plural(pv.total)} (as staff)`, tone: 'success' };
    case 'not_for_staff':
      return { text: 'Staff not ticked', tone: 'secondary' };
    case 'off':
      return { text: 'Off', tone: 'secondary' };
    case 'staff_only':
      return { text: 'Staff only', tone: 'secondary' };
    case 'not_ticked': {
      const names = contact.access_types.map((c) => accessTypes.find((a) => a.code === c)?.name ?? c);
      return { text: `Not ticked for ${names.join(', ')}`, tone: 'secondary' };
    }
    case 'no_documents':
      return { text: 'No documents', tone: 'secondary' };
    case 'reads': {
      const why = [
        pv.no_shared_code ? `${plural(pv.no_shared_code)} no shared access type` : '',
        pv.other_company ? `${plural(pv.other_company)} other company` : '',
      ].filter(Boolean);
      return {
        text: `Reads ${plural(pv.reads)} of ${plural(pv.total)}${why.length ? ` · ${why.join(', ')}` : ''}`,
        tone: pv.reads === 0 ? 'destructive' : why.length ? 'warning' : 'success',
      };
    }
  }
}

export function RowVerdictPill({
  row,
  contact,
  accessTypes,
}: {
  row: DocumentAccessRow;
  contact: PreviewContact;
  accessTypes: AccessTypeColumn[];
}) {
  const v = rowVerdict(row, contact, accessTypes);
  if (!v) return null;
  return (
    <Badge variant={v.tone} appearance="light" className="h-auto min-h-6 whitespace-normal py-0.5" title={v.text}>
      {v.text}
    </Badge>
  );
}

export function DocumentVerdictPill({ doc }: { doc: DocumentAccessDocument }) {
  const verdict = doc.verdict;
  if (!verdict) return null;
  let text: string;
  let tone: Tone;
  if (verdict === 'reads') {
    text = 'Reads';
    tone = 'success';
  } else if (verdict === 'no_shared_code') {
    text = 'No shared access type';
    tone = 'destructive';
  } else if (verdict === 'other_company') {
    text = doc.company_name ? `Other company: ${doc.company_name}` : 'Other company';
    tone = 'warning';
  } else {
    text = BLOCKED_TEXT[verdict];
    tone = 'destructive';
  }
  return (
    <Badge variant={tone} appearance="light" className="h-auto min-h-6 whitespace-normal py-0.5">
      {text}
    </Badge>
  );
}
