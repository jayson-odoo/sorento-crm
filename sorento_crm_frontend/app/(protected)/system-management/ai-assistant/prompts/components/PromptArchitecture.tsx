'use client';

import Link from 'next/link';
import { ArrowDown, ArrowRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { usePromptArchitecture } from '../../hooks/useAIAssistantPrompts';

const BOXES = [
  "Customer's message",
  'Matched list entries',
  'What the bot was given',
  'What the bot understood',
  'Kept or dropped',
  'What the bot looked up',
];

const CELL =
  'max-sm:flex max-sm:justify-between max-sm:gap-3 max-sm:py-0.5 before:text-muted-foreground before:content-[attr(data-label)] sm:before:content-none';

const fmt = (n: number) => n.toLocaleString('en-US');
/** 35700 -> "35.7k"; under 1000 as is. */
const fmtSize = (n: number) =>
  n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);

export function PromptArchitecture({
  name,
  version,
}: {
  name: string;
  version: number;
}) {
  const query = usePromptArchitecture(name, version, true);

  if (query.isLoading) return <SectionSkeleton />;
  if (query.isError || !query.data) {
    return (
      <p
        className="text-sm text-muted-foreground"
        data-testid="prompt-architecture"
      >
        Could not load the architecture for this version.
      </p>
    );
  }
  const data = query.data;
  const indexed = data.mode === 'index' && data.uses_closed_lists;
  const listNames = data.lists
    .filter((l) => !l.checked_only)
    .map((l) => l.name);

  const note = (i: number) =>
    i === 1 ? (
      <ul className="mt-1 space-y-0.5 text-2xs text-muted-foreground">
        {listNames.map((n) => (
          <li key={n}>{n}</li>
        ))}
      </ul>
    ) : i === 4 ? (
      <p className="mt-1 text-2xs text-muted-foreground">
        Checked against the same lists and the warehouse list
      </p>
    ) : null;

  return (
    <div className="space-y-5" data-testid="prompt-architecture">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-sm">
          Each message, v{data.version} gives the bot about{' '}
          {fmtSize(data.total_size)} of instructions and lists.
        </p>
        <Badge
          variant={indexed ? 'success' : 'secondary'}
          appearance="light"
          size="sm"
        >
          {indexed
            ? 'Only the matching entries are sent'
            : 'Full lists are sent'}
        </Badge>
      </div>

      <div className="flex flex-col items-stretch gap-2 sm:flex-row sm:items-start">
        {BOXES.map((label, i) => (
          <div
            key={label}
            className="flex min-w-0 flex-col items-center gap-2 sm:flex-1 sm:flex-row sm:items-start"
          >
            <div className="w-full min-w-0 rounded-md border p-2 sm:flex-1">
              <div className="text-xs font-medium">{label}</div>
              {note(i)}
            </div>
            {i < BOXES.length - 1 && (
              <>
                <ArrowDown
                  className="size-4 shrink-0 text-muted-foreground sm:hidden"
                  aria-hidden
                />
                <ArrowRight
                  className="mt-2 hidden size-4 shrink-0 text-muted-foreground sm:block"
                  aria-hidden
                />
              </>
            )}
          </div>
        ))}
      </div>

      <div className="space-y-1">
        <h3 className="text-sm font-medium">Lists</h3>
        <table className="w-full text-xs max-sm:block">
          <thead className="max-sm:hidden">
            <tr className="border-b text-muted-foreground">
              <th className="py-1 pe-2 text-start font-medium">List</th>
              <th className="py-1 pe-2 text-start font-medium">Comes from</th>
              <th className="py-1 pe-2 text-start font-medium">
                How a message is matched
              </th>
              <th className="py-1 pe-2 text-end font-medium">Entries</th>
              <th className="py-1 pe-2 text-end font-medium">
                Size each message
              </th>
              <th className="py-1 text-end font-medium">Full list size</th>
            </tr>
          </thead>
          <tbody className="max-sm:block">
            {data.lists.map((l) => (
              <tr
                key={l.key}
                className="border-b align-top last:border-0 max-sm:block max-sm:py-2"
              >
                <td data-label="List" className={`py-1 pe-2 ${CELL}`}>
                  {l.name}
                </td>
                <td data-label="Comes from" className={`py-1 pe-2 ${CELL}`}>
                  {l.href ? (
                    <Link
                      href={l.href}
                      className="text-primary underline-offset-2 hover:underline"
                    >
                      {l.source}
                    </Link>
                  ) : (
                    l.source
                  )}
                </td>
                <td
                  data-label="How a message is matched"
                  className={`py-1 pe-2 ${CELL} max-sm:flex-col max-sm:gap-0.5`}
                >
                  {l.how}
                </td>
                <td
                  data-label="Entries"
                  className={`py-1 pe-2 text-end tabular-nums ${CELL}`}
                >
                  {fmt(l.entries)}
                </td>
                <td
                  data-label="Size each message"
                  className={`py-1 pe-2 text-end tabular-nums ${CELL}`}
                >
                  {fmtSize(l.sent_each_message_size)}
                </td>
                <td
                  data-label="Full list size"
                  className={`py-1 text-end tabular-nums ${CELL}`}
                >
                  {l.checked_only ? '-' : fmtSize(l.full_list_size)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="space-y-1">
        <h3 className="text-sm font-medium">What the bot is given</h3>
        <table className="w-full text-xs max-sm:block">
          <thead className="max-sm:hidden">
            <tr className="border-b text-muted-foreground">
              <th className="py-1 pe-2 text-start font-medium">Part</th>
              <th className="py-1 text-end font-medium">Size</th>
            </tr>
          </thead>
          <tbody className="max-sm:block">
            {data.groups.map((g) => (
              <tr
                key={g.name}
                className="border-b last:border-0 max-sm:block max-sm:py-2"
              >
                <td data-label="Part" className={`py-1 pe-2 ${CELL}`}>
                  {g.name}
                </td>
                <td data-label="Size" className={`py-1 ${CELL}`}>
                  <div className="flex items-center justify-end gap-2">
                    <div
                      className="hidden h-1.5 w-24 rounded bg-muted sm:block"
                      aria-hidden
                    >
                      <div
                        className="h-full rounded bg-primary/60"
                        style={{ width: `${g.share * 100}%` }}
                      />
                    </div>
                    <span className="tabular-nums">{fmtSize(g.size)}</span>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
