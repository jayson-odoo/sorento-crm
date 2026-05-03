import { Badge } from '@/components/ui/badge';
import type { TicketStatus } from '../types/ticket.types';

const STATUS_LABEL: Record<TicketStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  assigned: 'Assigned',
  responded: 'Responded',
  resolved: 'Resolved',
};

const STATUS_VARIANT: Record<TicketStatus, 'secondary' | 'primary' | 'outline' | 'success'> = {
  draft: 'outline',
  submitted: 'secondary',
  assigned: 'primary',
  responded: 'primary',
  resolved: 'success',
};

export function TicketStatusBadge({ status }: { status: TicketStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status] ?? 'secondary'}>
      {STATUS_LABEL[status] ?? status}
    </Badge>
  );
}

export function TicketPriorityBadge({
  priority,
}: {
  priority: 'low' | 'medium' | 'high' | 'urgent';
}) {
  const variant: Record<typeof priority, 'secondary' | 'info' | 'warning' | 'destructive'> = {
    low: 'secondary',
    medium: 'info',
    high: 'warning',
    urgent: 'destructive',
  };
  const label = priority.charAt(0).toUpperCase() + priority.slice(1);
  return <Badge variant={variant[priority]}>{label}</Badge>;
}
