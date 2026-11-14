import { Badge } from '@/components/ui/badge';
import { answerLabel, summaryLabel } from '../lib/warrantyAnswers';

const VARIANT: Record<string, 'success' | 'warning' | 'destructive' | 'secondary'> = {
  covered: 'success',
  partly_covered: 'warning',
  expired: 'destructive',
  not_covered: 'destructive',
  defect_not_covered: 'destructive',
  no_term: 'secondary',
  unknown: 'secondary',
};

/** One pill for a per-term answer or a job summary; the two share their colours. */
export default function WarrantyPill({ code, summary = false }: { code: string; summary?: boolean }) {
  return (
    <Badge variant={VARIANT[code] ?? 'secondary'} size="sm" className="shrink-0">
      {summary ? summaryLabel(code) : answerLabel(code)}
    </Badge>
  );
}
