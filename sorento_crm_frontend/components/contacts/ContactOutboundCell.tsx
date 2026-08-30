'use client';

import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';

interface ContactOutboundCellProps {
  /** The contact's `outbound_enabled`. `null`/`undefined` = the row is not linked to a contact. */
  enabled?: boolean | null;
  /** Human name (or phone) of the contact, for the switch's accessible label. */
  contactLabel: string;
  disabled?: boolean;
  onChange: (enabled: boolean) => void;
}

/**
 * One contact's outbound kill switch, as a grid cell.
 *
 * Shared by every grid that shows it (contacts, contact x agent grants flat and
 * grouped) so the wording and the colour of "silenced" cannot drift between the
 * screens that manage the same column.
 *
 * A row with no linked `respond_contacts` row shows "Not linked" and NO switch:
 * there is nothing to flip, and pretending it is reachable would be a lie.
 */
export default function ContactOutboundCell({
  enabled,
  contactLabel,
  disabled,
  onChange,
}: ContactOutboundCellProps) {
  if (enabled === null || enabled === undefined) {
    return <span className="text-muted-foreground">Not linked</span>;
  }

  return (
    <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
      <Switch
        checked={enabled}
        disabled={disabled}
        aria-label={
          enabled
            ? `Disable outbound for ${contactLabel}`
            : `Enable outbound for ${contactLabel}`
        }
        onCheckedChange={onChange}
      />
      <Badge variant={enabled ? 'secondary' : 'destructive'}>
        {enabled ? 'Can be messaged' : 'Silenced'}
      </Badge>
    </div>
  );
}
