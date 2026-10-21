'use client';

import Link from 'next/link';
import { ArrowDown, ArrowRight } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { SectionSkeleton } from '@/components/common/SectionSkeleton';
import { usePromptArchitecture } from '../../hooks/useAIAssistantPrompts';
import type { PromptArchitectureSection } from '../../services/aiPromptsService';

const KIND_LABEL: Record<PromptArchitectureSection['kind'], string> = {
  text: 'Text',
  filled_from_data: 'Filled from data',
  closed_lists: 'Closed lists',
};

const BOXES = [
  "Customer's message",
  'Matched list entries',
  'What the parser got',
  'What it understood',
  'Kept or dropped',
];

const fmt = (n: number) => n.toLocaleString('en-US');

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
  const largest = Math.max(1, ...data.sections.map((s) => s.tokens));

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
          v{data.version} sends about {fmt(data.total_tokens)} tokens to the
          parser on every message.
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
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-start text-muted-foreground">
                <th className="py-1 pe-2 text-start font-medium">List</th>
                <th className="py-1 pe-2 text-start font-medium">Comes from</th>
                <th className="py-1 pe-2 text-end font-medium">Entries</th>
                <th className="py-1 pe-2 text-end font-medium">
                  Sent each message
                </th>
                <th className="py-1 text-end font-medium">Full list</th>
              </tr>
            </thead>
            <tbody>
              {data.lists.map((l) => (
                <tr key={l.key} className="border-b last:border-0">
                  <td className="py-1 pe-2">{l.name}</td>
                  <td className="py-1 pe-2">
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
                  <td className="py-1 pe-2 text-end tabular-nums">
                    {fmt(l.entries)}
                  </td>
                  <td className="py-1 pe-2 text-end tabular-nums">
                    {fmt(l.sent_each_message_tokens)}
                  </td>
                  <td className="py-1 text-end tabular-nums">
                    {l.checked_only ? '-' : fmt(l.full_list_tokens)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="space-y-1">
        <h3 className="text-sm font-medium">Sections</h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-muted-foreground">
                <th className="py-1 pe-2 text-start font-medium">Section</th>
                <th className="py-1 pe-2 text-start font-medium">Kind</th>
                <th className="py-1 text-end font-medium">Tokens</th>
              </tr>
            </thead>
            <tbody>
              {data.sections.map((s) => (
                <tr key={s.title} className="border-b last:border-0">
                  <td
                    className="max-w-[16rem] truncate py-1 pe-2"
                    title={s.title}
                  >
                    {s.title}
                  </td>
                  <td className="py-1 pe-2">{KIND_LABEL[s.kind]}</td>
                  <td className="py-1">
                    <div className="flex items-center justify-end gap-2">
                      <div
                        className="hidden h-1.5 w-24 rounded bg-muted sm:block"
                        aria-hidden
                      >
                        <div
                          className="h-full rounded bg-primary/60"
                          style={{ width: `${(s.tokens / largest) * 100}%` }}
                        />
                      </div>
                      <span className="tabular-nums">{fmt(s.tokens)}</span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
