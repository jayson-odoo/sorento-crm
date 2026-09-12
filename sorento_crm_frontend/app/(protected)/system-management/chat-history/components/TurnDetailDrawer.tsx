'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SearchableCode } from '@/components/common/find-in-text/SearchableCode';
import { useChatbotTurn } from '../hooks/useChatbotTurns';
import { shortTurnId } from '../turnPresentation';
import type {
  TurnDetail,
  TurnDetailCrossdomain,
  TurnDetailDecay,
  TurnDetailFocus,
} from '../types/chatbotTurn.types';

/**
 * Turn detail trace view (chatbot growth r1, Slice D2, AC-972, AC-973).
 *
 * `TurnPanel` (the existing per-stage timeline under a message) already answers
 * "what happened, in order". This answers a narrower question an engineer opens
 * a specific turn to ask: what did the tool call actually carry, what did a
 * cross-domain probe find, which field-reveal keys were dropped, which focus
 * rule fired and why, what did the session gain or lose. Each section renders
 * whatever the backend composed and collapses to nothing wasted when a kind
 * has not shipped yet - never an error, never a placeholder explaining why.
 */
export function TurnDetailDrawer({
  turnId,
  shadowTurnId = null,
  onOpenChange,
}: {
  turnId: string | null;
  /**
   * AC-1029. The shadow parse of the SAME message, when the Shadow filter is on and a
   * shadow row exists. Fetched only while the drawer is open, and only for the Parse
   * section: nothing else on a shadow turn differs, because it sends nothing and writes
   * no session.
   */
  shadowTurnId?: string | null;
  onOpenChange: (open: boolean) => void;
}) {
  const { data: turn, isLoading, isError } = useChatbotTurn(turnId);
  const { data: shadowTurn, isError: shadowFailed } = useChatbotTurn(
    turnId && shadowTurnId ? shadowTurnId : null,
  );

  return (
    <Sheet open={Boolean(turnId)} onOpenChange={onOpenChange}>
      <SheetContent
        className="w-full sm:max-w-2xl flex flex-col p-0 overflow-x-hidden"
        aria-describedby={undefined}
      >
        <SheetHeader className="px-4 sm:px-6 py-4 border-b">
          <SheetTitle className="truncate">
            {turn ? `Turn #${shortTurnId(turn.id)}` : turnId ? `Turn #${shortTurnId(turnId)}` : 'Turn'}
          </SheetTitle>
        </SheetHeader>

        <div className="flex-1 overflow-y-auto overflow-x-hidden px-4 sm:px-6 py-4 space-y-3">
          {isLoading && (
            <div className="space-y-2" data-testid="turn-detail-loading">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          )}
          {isError && (
            <p className="text-sm text-destructive">
              Could not load this turn. Reload to try again.
            </p>
          )}
          {turn && (
            <Sections
              detail={turn.trace_detail}
              shadowParse={shadowTurn?.trace_detail.parse ?? null}
              shadowAsked={Boolean(shadowTurnId)}
              shadowFailed={shadowFailed}
            />
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}

function Sections({
  detail,
  shadowParse = null,
  shadowAsked = false,
  shadowFailed = false,
}: {
  detail: TurnDetail;
  shadowParse?: TurnDetail['parse'];
  shadowAsked?: boolean;
  shadowFailed?: boolean;
}) {
  return (
    <>
      <Section title="Stages" testId="section-stages" defaultOpen>
        <StagesSection stages={detail.stages} />
      </Section>
      <Section title="Parse" testId="section-parse">
        <ParseSection
          parse={detail.parse}
          shadowParse={shadowParse}
          shadowAsked={shadowAsked}
          shadowFailed={shadowFailed}
        />
      </Section>
      <Section title="Decay" testId="section-decay">
        <DecaySection decay={detail.decay} />
      </Section>
      <Section title="Open question" testId="section-open-question">
        <OpenQuestionSection openQuestion={detail.open_question} />
      </Section>
      <Section title="Focus" testId="section-focus">
        <FocusSection focus={detail.focus} />
      </Section>
      <Section title="Tool" testId="section-tool">
        <ToolSection tool={detail.tool} />
      </Section>
      <Section title="Cross-domain" testId="section-crossdomain">
        <CrossdomainSection crossdomain={detail.crossdomain} />
      </Section>
      <Section title="Field reveals" testId="section-reveals">
        <RevealsSection reveals={detail.reveals} />
      </Section>
      <Section title="Session" testId="section-session">
        <SessionSection session={detail.session} />
      </Section>
    </>
  );
}

function Section({
  title,
  testId,
  defaultOpen = false,
  children,
}: {
  title: string;
  testId: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Collapsible open={open} onOpenChange={setOpen} className="rounded-lg border">
      <CollapsibleTrigger
        className="flex w-full items-center gap-1.5 px-3 py-2 text-start text-sm font-medium"
        data-testid={`${testId}-trigger`}
      >
        {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        {title}
      </CollapsibleTrigger>
      <CollapsibleContent data-testid={testId}>
        <div className="border-t px-3 py-2">{children}</div>
      </CollapsibleContent>
    </Collapsible>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="text-xs text-muted-foreground">{children}</p>;
}

function Code({ value }: { value: unknown }) {
  return (
    <div className="overflow-x-auto">
      <SearchableCode text={JSON.stringify(value, null, 2)} />
    </div>
  );
}

function StagesSection({ stages }: { stages: TurnDetail['stages'] }) {
  if (stages.length === 0) return <Empty>No stages recorded.</Empty>;
  return (
    <ol className="space-y-2">
      {stages.map((stage, i) => (
        <li key={`${stage.name}-${i}`} className="text-xs">
          <div className="flex items-center gap-2">
            <Badge
              variant={stage.status === 'failed' ? 'destructive' : 'success'}
              appearance="light"
              size="sm"
            >
              {stage.name}
            </Badge>
            {stage.ms != null && (
              <span className="text-muted-foreground tabular-nums">{stage.ms}ms</span>
            )}
          </div>
          {stage.status === 'failed' && stage.error ? (
            <p className="mt-1 rounded-md border border-destructive/30 bg-destructive/5 px-2 py-1.5 text-destructive">
              {stage.error}
            </p>
          ) : stage.summary ? (
            <p className="mt-1 text-muted-foreground">{stage.summary}</p>
          ) : null}
        </li>
      ))}
    </ol>
  );
}

/**
 * The turn's own parse, and - once a shadow version is running - the second parse beside
 * it (AC-1029).
 *
 * TWO COLUMNS, not a computed diff. The owner is reading a whole emission to judge a
 * prompt, and a diff would decide for them which keys matter; at 375px the columns stack,
 * which is the same reading order one after the other.
 */
function ParseSection({
  parse,
  shadowParse = null,
  shadowAsked = false,
  shadowFailed = false,
}: {
  parse: TurnDetail['parse'];
  shadowParse?: TurnDetail['parse'];
  shadowAsked?: boolean;
  shadowFailed?: boolean;
}) {
  if (!parse) return <Empty>No parse recorded.</Empty>;
  if (!shadowAsked) return <ParseColumn parse={parse} />;
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2" data-testid="parse-columns">
      <div className="min-w-0">
        <div className="mb-1 text-2xs uppercase tracking-wide text-muted-foreground/70">live</div>
        <ParseColumn parse={parse} />
      </div>
      <div className="min-w-0">
        <div className="mb-1 text-2xs uppercase tracking-wide text-muted-foreground/70">shadow</div>
        {shadowFailed ? (
          <p className="text-xs text-destructive">The shadow parse could not be loaded.</p>
        ) : shadowParse ? (
          <ParseColumn parse={shadowParse} />
        ) : (
          <Empty>No shadow parse for this turn.</Empty>
        )}
      </div>
    </div>
  );
}

function ParseColumn({ parse }: { parse: NonNullable<TurnDetail['parse']> }) {
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">prompt version</dt>
        <dd>{parse.prompt_version ?? '-'}</dd>
        <dt className="text-muted-foreground">model</dt>
        <dd>{parse.model ?? '-'}</dd>
      </dl>
      {parse.post_processed && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Post-processed</div>
          <Code value={parse.post_processed} />
        </div>
      )}
      {parse.raw && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Raw</div>
          <Code value={parse.raw} />
        </div>
      )}
    </div>
  );
}

function DecaySection({ decay }: { decay: TurnDetailDecay[] }) {
  if (decay.length === 0) return <Empty>Nothing decayed this turn.</Empty>;
  return (
    <ul className="space-y-2 text-xs">
      {decay.map((d, i) => (
        <li key={`${d.slot}-${i}`} className="rounded-md border px-2 py-1.5">
          <div className="flex items-center gap-2">
            <span className="font-medium">{d.slot}</span>
            {d.age_turns != null && (
              <span className="text-muted-foreground">{d.age_turns} turns old</span>
            )}
          </div>
          {d.reason && <p className="text-muted-foreground">{d.reason}</p>}
        </li>
      ))}
    </ul>
  );
}

function OpenQuestionSection({
  openQuestion,
}: {
  openQuestion: TurnDetail['open_question'];
}) {
  if (!openQuestion) return <Empty>No open question this turn.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">handler</dt>
        <dd>{openQuestion.handler ?? '-'}</dd>
        <dt className="text-muted-foreground">outcome</dt>
        <dd>{openQuestion.outcome ?? '-'}</dd>
      </dl>
      <Code value={{ before: openQuestion.before, answer: openQuestion.answer, after: openQuestion.after }} />
    </div>
  );
}

function FocusSection({ focus }: { focus: TurnDetailFocus[] }) {
  if (focus.length === 0) return <Empty>No focus rule fired this turn.</Empty>;
  return (
    <ul className="space-y-2 text-xs">
      {focus.map((f, i) => (
        <li key={`${f.slot}-${i}`} className="rounded-md border px-2 py-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-medium">{f.slot}</span>
            <Badge variant="secondary" appearance="light" size="sm">
              {f.rule}
            </Badge>
            {f.source && (
              <span className="text-2xs text-muted-foreground">source: {f.source}</span>
            )}
          </div>
          <div className="mt-1 text-muted-foreground">
            {JSON.stringify(f.before)} {'->'} {JSON.stringify(f.after)}
          </div>
        </li>
      ))}
    </ul>
  );
}

function ToolSection({ tool }: { tool: TurnDetail['tool'] }) {
  if (!tool) return <Empty>No tool call recorded.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <dl className="grid grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5">
        <dt className="text-muted-foreground">name</dt>
        <dd>{tool.name ?? '-'}</dd>
        <dt className="text-muted-foreground">ms</dt>
        <dd>{tool.ms ?? '-'}</dd>
      </dl>
      {tool.args && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Args</div>
          <Code value={tool.args} />
        </div>
      )}
      {tool.envelope && (
        <div>
          <div className="mb-1 font-medium text-muted-foreground">Envelope</div>
          <Code value={tool.envelope} />
        </div>
      )}
    </div>
  );
}

function CrossdomainSection({ crossdomain }: { crossdomain: TurnDetailCrossdomain[] }) {
  if (crossdomain.length === 0) return <Empty>No cross-domain probe this turn.</Empty>;
  return (
    <ul className="space-y-2 text-xs">
      {crossdomain.map((c, i) => (
        <li key={`${c.tool}-${i}`} className="rounded-md border px-2 py-1.5">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant="secondary" appearance="light" size="sm">
              rung {c.rung}
            </Badge>
            <span className="font-medium">{c.tool}</span>
            <span className="text-muted-foreground">{c.rows ?? 0} rows</span>
            {c.rendered ? (
              <Badge variant="success" appearance="light" size="sm">
                rendered
              </Badge>
            ) : (
              <Badge variant="secondary" appearance="light" size="sm">
                not rendered
              </Badge>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}

function RevealsSection({ reveals }: { reveals: TurnDetail['reveals'] }) {
  const seen = reveals.restricted_fields_seen.length > 0;
  if (!seen) return <Empty>No restricted field was on this answer.</Empty>;
  return (
    <div className="space-y-2 text-xs">
      <ChipRow label="Seen" chips={reveals.restricted_fields_seen} tone="secondary" />
      <ChipRow label="Granted" chips={reveals.granted} tone="success" />
      <ChipRow label="Dropped" chips={reveals.dropped} tone="destructive" />
    </div>
  );
}

function SessionSection({ session }: { session: TurnDetail['session'] }) {
  const gained = session.diff.filter((d) => d.change === 'gained').map((d) => d.key);
  const lost = session.diff.filter((d) => d.change === 'lost').map((d) => d.key);
  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-2 gap-3">
        <ChipRow label="Lost" chips={lost} tone="destructive" />
        <ChipRow label="Gained" chips={gained} tone="success" />
      </div>
      <div>
        <div className="mb-1 font-medium text-muted-foreground">Before / after</div>
        <Code value={{ before: session.before, after: session.after }} />
      </div>
    </div>
  );
}

function ChipRow({
  label,
  chips,
  tone,
}: {
  label: string;
  chips: string[];
  tone: BadgeProps['variant'];
}) {
  return (
    <div>
      <div className="mb-1 text-2xs font-medium text-muted-foreground">{label}</div>
      {chips.length === 0 ? (
        <span className="text-2xs text-muted-foreground/70">none</span>
      ) : (
        <div className="flex flex-wrap gap-1">
          {chips.map((c) => (
            <Badge key={c} variant={tone} appearance="light" size="sm">
              {c}
            </Badge>
          ))}
        </div>
      )}
    </div>
  );
}
