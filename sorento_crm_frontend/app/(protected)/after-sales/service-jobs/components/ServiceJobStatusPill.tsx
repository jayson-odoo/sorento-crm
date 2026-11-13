import { Badge } from '@/components/ui/badge';
import type { ServiceJobStatus } from '../types/serviceJob.types';

const VARIANT: Record<ServiceJobStatus, 'secondary' | 'info' | 'warning' | 'success'> = {
  proposed: 'secondary',
  confirmed: 'info',
  on_the_way: 'info',
  arrived: 'warning',
  completed: 'success',
  verified: 'success',
  cancelled: 'secondary',
};

export default function ServiceJobStatusPill({
  status,
  label,
}: {
  status: ServiceJobStatus;
  label: string;
}) {
  return (
    <Badge variant={VARIANT[status] ?? 'secondary'} size="sm" className="shrink-0">
      {label}
    </Badge>
  );
}
