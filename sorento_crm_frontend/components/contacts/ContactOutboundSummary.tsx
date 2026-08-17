'use client';

interface ContactOutboundSummaryProps {
  /** Distinct CONTACTS on the current page that can be messaged. */
  reachable: number;
  /** Distinct CONTACTS on the current page that are silenced. */
  silenced: number;
}

/**
 * The audit line above a grid that carries the outbound switch.
 *
 * Scoped to the page on purpose, and labelled as such: these grids page and
 * filter, so a whole-table figure would not describe what the reader is looking
 * at. The whole-table counts live on System Management -> Respond.io Contacts,
 * which asks the backend for them.
 */
export default function ContactOutboundSummary({
  reachable,
  silenced,
}: ContactOutboundSummaryProps) {
  return (
    <div className="flex flex-wrap items-center gap-6">
      <Stat label="Reachable on this page" value={reachable} tone="ok" />
      <Stat label="Silenced on this page" value={silenced} tone="off" />
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: 'ok' | 'off' }) {
  return (
    <div>
      <p className="text-xs font-medium text-muted-foreground">{label}</p>
      <p
        className={`text-2xl font-semibold tabular-nums ${
          tone === 'ok' ? 'text-green-600' : 'text-destructive'
        }`}
      >
        {value}
      </p>
    </div>
  );
}
