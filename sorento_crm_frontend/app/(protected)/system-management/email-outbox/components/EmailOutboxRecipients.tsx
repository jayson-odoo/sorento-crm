import type { EmailOutboxRow } from '../types/emailOutbox.types';

interface Props {
  row: Pick<EmailOutboxRow, 'recipient_email' | 'recipients_json'>;
}

/** To / Cc / Bcc of one outbox row, read the way the drainer sends it: `recipients_json.to`
 * when the row has one, else the single `recipient_email`. */
export default function EmailOutboxRecipients({ row }: Props) {
  const json = row.recipients_json ?? {};
  const to = json.to?.length ? json.to : [row.recipient_email];
  const lines: [string, string[]][] = [
    ['To', to],
    ['Cc', json.cc ?? []],
    ['Bcc', json.bcc ?? []],
  ];
  return (
    <>
      {lines
        .filter(([label, list]) => label === 'To' || list.length > 0)
        .map(([label, list]) => (
          <div key={label} className="min-w-0">
            <div className="text-muted-foreground">{label}</div>
            <div className="font-mono break-all" data-testid={`outbox-${label.toLowerCase()}`}>
              {list.join(', ')}
            </div>
          </div>
        ))}
    </>
  );
}
