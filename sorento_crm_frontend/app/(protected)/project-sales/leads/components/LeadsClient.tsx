'use client';

import * as React from 'react';
import Link from 'next/link';
import { Plus, Search, Users } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useLeadMetrics, useLeads } from '../../_shared/hooks/useProjects';
import type { LeadWithAcceptance } from '../../_shared/types/leadAcceptance.types';
import { LeadAcceptanceBadge } from './LeadAcceptanceBadge';
import { informantSummary } from './acceptance';
import { LeadWizardDialog } from './LeadWizardDialog';

const OUTCOME_OPTIONS = [
  { value: 'open', label: 'Open' },
  { value: 'qualified', label: 'Qualified' },
  { value: 'disqualified', label: 'Disqualified' },
];

const SOURCE_OPTIONS = [
  { value: 'site_visit', label: 'Site visit' },
  { value: 'architect', label: 'Architect' },
  { value: 'contractor', label: 'Contractor' },
  { value: 'dealer', label: 'Dealer' },
  { value: 'inbound', label: 'Inbound enquiry' },
  { value: 'other', label: 'Other' },
];

/**
 * Leads: what we have heard about, before anybody owns it.
 *
 * Defaults to OPEN leads because the list is a worklist, not an archive: a qualified
 * lead's real life continues on its project, and a disqualified one is history. Both
 * stay one filter click away rather than being hidden.
 *
 * Duplicate hints render inline (AC-O3) and are deliberately not warnings. Two people
 * hearing the same rumour is normal, and the row says who the other person is so they
 * can talk instead of racing.
 */
export function LeadsClient() {
  const [wizardOpen, setWizardOpen] = React.useState(false);
  const [search, setSearch] = React.useState('');
  const [debounced, setDebounced] = React.useState('');
  const [outcome, setOutcome] = React.useState('open');
  const [source, setSource] = React.useState('');

  React.useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(search.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [search]);

  const leads = useLeads({
    query: debounced || undefined,
    outcome: outcome ? [outcome] : undefined,
    source: source ? [source] : undefined,
    limit: 200,
  });
  // The lead list already serves the P1 informant and acceptance fields; phase 1's
  // ProjectLead type predates them, so the rows are read through the wider type.
  const rows: LeadWithAcceptance[] = leads.data?.data ?? [];
  const total = leads.data?.pagination.total ?? 0;

  return (
    <div className="space-y-5">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold">Leads</h1>
          <p className="text-sm text-muted-foreground">
            Developments we have heard about. Nobody owns one until a salesperson
            accepts it.
          </p>
        </div>
        <Button type="button" onClick={() => setWizardOpen(true)}>
          <Plus className="size-4" aria-hidden />
          Record a lead
        </Button>
      </header>

      <ConversionStrip />

      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="relative flex-1">
          <Search
            className="absolute start-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search title or lead code…"
            className="ps-9"
            aria-label="Search leads"
          />
        </div>
        <div className="w-full sm:w-44">
          <Label className="text-xs text-muted-foreground">Outcome</Label>
          <SearchableSelect
            value={outcome}
            onChange={setOutcome}
            clearable
            options={OUTCOME_OPTIONS}
            placeholder="All outcomes"
          />
        </div>
        <div className="w-full sm:w-44">
          <Label className="text-xs text-muted-foreground">Source</Label>
          <SearchableSelect
            value={source}
            onChange={setSource}
            clearable
            options={SOURCE_OPTIONS}
            placeholder="All sources"
          />
        </div>
      </div>

      {leads.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
          <Skeleton className="h-20 w-full" />
        </div>
      ) : leads.isError ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            Leads could not be loaded
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            {leads.error instanceof Error ? leads.error.message : 'Try again shortly.'}
          </p>
        </div>
      ) : rows.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border px-6 py-12 text-center">
          <h2 className="text-sm font-semibold">
            {debounced || source || outcome !== 'open'
              ? 'No leads match these filters'
              : 'No open leads'}
          </h2>
          <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
            Record what you heard on site, even when it is vague. A lead costs nothing
            and claims nothing: it becomes somebody&apos;s only when they accept it.
          </p>
          <Button type="button" className="mt-4" onClick={() => setWizardOpen(true)}>
            <Plus className="size-4" aria-hidden />
            Record a lead
          </Button>
        </div>
      ) : (
        <>
          <p className="text-xs text-muted-foreground">
            {rows.length === total ? `${total} leads` : `${rows.length} of ${total} leads`}
          </p>
          <ul className="grid gap-3 lg:grid-cols-2">
            {rows.map((lead) => (
              <LeadCard key={lead.id} lead={lead} />
            ))}
          </ul>
        </>
      )}

      {wizardOpen && <LeadWizardDialog onDone={() => setWizardOpen(false)} />}
    </div>
  );
}

/**
 * Conversion at the top of the list, because it is the number the module was asked
 * for: "lead-to-project conversion rate becomes a real metric".
 *
 * Renders "no decisions yet" rather than 0% when nothing is decided. Zero would read
 * as "we convert nothing", which is a different and wrong statement.
 */
function ConversionStrip() {
  const metrics = useLeadMetrics();
  const data = metrics.data;

  if (metrics.isLoading) return <Skeleton className="h-16 w-full" />;
  if (metrics.isError || !data) return null;

  return (
    <Card>
      <CardContent className="grid gap-4 py-4 sm:grid-cols-4">
        <Metric label="Open" value={String(data.open)} />
        <Metric label="Qualified" value={String(data.qualified)} />
        <Metric label="Disqualified" value={String(data.disqualified)} />
        <Metric
          label="Conversion"
          value={
            data.conversion_rate === null || data.conversion_rate === undefined
              ? 'No decisions yet'
              : `${Math.round(data.conversion_rate * 100)}%`
          }
          hint={
            data.decided > 0
              ? `${data.qualified} of ${data.decided} decided`
              : 'Measured once leads are qualified or disqualified'
          }
        />
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="truncate text-lg font-semibold" title={value}>
        {value}
      </p>
      {hint && <p className="truncate text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function LeadCard({ lead }: { lead: LeadWithAcceptance }) {
  const informant = informantSummary(lead);
  return (
    <li className="rounded-lg border border-border p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-1">
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="font-mono text-[11px] text-muted-foreground">
              {lead.lead_code}
            </span>
            <Badge variant={lead.outcome === 'open' ? 'outline' : 'secondary'} className="capitalize">
              {lead.outcome}
            </Badge>
            {lead.status_label && (
              <Badge variant="secondary" className="text-[11px]">
                {lead.status_label}
              </Badge>
            )}
          </div>
          <Link
            href={`/project-sales/leads/${lead.id}`}
            className="block font-medium hover:underline"
          >
            <span className="line-clamp-2" title={lead.title}>
              {lead.title}
            </span>
          </Link>
          <p className="truncate text-xs text-muted-foreground">
            {[lead.developer_name, lead.location].filter(Boolean).join(' · ') ||
              'No developer or location recorded'}
          </p>
          <p className="truncate text-xs text-muted-foreground" title={informant ?? undefined}>
            Told us: {informant ?? 'not recorded'}
          </p>
          <p className="truncate text-xs text-muted-foreground">
            Buyer: {lead.customer_name ?? 'not known yet'}
          </p>
          <LeadAcceptanceBadge lead={lead} className="flex flex-wrap items-center gap-1" />
          <p className="text-xs text-muted-foreground">
            {lead.estimated_value ? formatMyr(lead.estimated_value) : 'No value yet'}
            {lead.project_count > 0
              ? ` · ${lead.project_count} project${lead.project_count === 1 ? '' : 's'}`
              : ''}
          </p>
        </div>
      </div>

      {/* Informational, never a block (AC-O3). Naming the other owner is the point:
          it turns a race into a conversation. */}
      {lead.possible_duplicates.length > 0 && (
        <p className="mt-2 flex items-start gap-1.5 rounded-md bg-muted/60 px-2 py-1.5 text-xs text-muted-foreground">
          <Users className="mt-0.5 size-3 shrink-0" aria-hidden />
          <span>
            Also recorded by{' '}
            {lead.possible_duplicates
              .map((hint) => hint.owner_name ?? hint.lead_code)
              .join(', ')}
            . Leads are not exclusive, so both stand.
          </span>
        </p>
      )}

      {lead.disqualified_reason && (
        <p className="mt-2 text-xs text-muted-foreground">
          Disqualified: {lead.disqualified_reason.replace(/_/g, ' ')}
        </p>
      )}
    </li>
  );
}

function formatMyr(value: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  return `RM ${amount.toLocaleString('en-MY', { maximumFractionDigits: 0 })}`;
}
