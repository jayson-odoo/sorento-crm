import { Badge, BadgeDot } from '@/components/ui/badge';
import type { IdeaStatusColor } from '@/types/ideas';

const VARIANT: Record<IdeaStatusColor, 'secondary' | 'info' | 'primary' | 'warning' | 'success' | 'destructive'> = {
  grey: 'secondary',
  info: 'info',
  primary: 'primary',
  warning: 'warning',
  success: 'success',
  destructive: 'destructive',
};

/** The status pill. The label is the tenant's own wording, never a hard-coded one. */
export function IdeaStatusBadge({ label, color }: { label: string; color: IdeaStatusColor }) {
  return (
    <Badge variant={VARIANT[color] ?? 'secondary'} appearance="light">
      <BadgeDot />
      {label}
    </Badge>
  );
}
