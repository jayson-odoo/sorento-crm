'use client';

import { Fragment, useState } from 'react';
import { ChevronDown, ChevronUp, Download, LoaderCircle } from 'lucide-react';
import { Alert, AlertContent, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { FileDropzone } from '@/components/common/FileDropzone';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { toast } from '@/lib/toast';
import { saveBlobAs } from '@/lib/save-blob';
import { useCustomerMultiPicker } from '@/app/(protected)/order-management/customers/hooks/useCustomerMultiPicker';
import type {
  AccessSheetAccount,
  AccessSheetBlock,
  AccessSheetContact,
  AccessSheetResult,
} from '@/services/contactAccessSheetService';
import { useApplyAccessSheet, usePreviewAccessSheet } from '../hooks/useAccessSheetImport';
import {
  allExactConfirmed,
  changeLines,
  confirmAllExact,
  initialSelection,
  resultCsv,
  setConfirmed,
  setTicked,
  toConfirmedPayload,
  toggleTicked,
  unchangedFacets,
  type AccessSheetSelection,
  type ChangeItem,
} from '../lib/accessSheet';

type Step = 'upload' | 'preview' | 'result';

const BLOCK_BADGE = {
  exact: { label: 'Exact', variant: 'success' },
  pick: { label: 'Needs a pick', variant: 'warning' },
  none: { label: 'No match', variant: 'destructive' },
} as const;

const SKIP_TEXT: Record<string, string> = {
  not_in_crm: 'Not in CRM yet',
  ambiguous_phone: 'Phone matches two contacts',
  dealer_not_confirmed: 'Dealer not confirmed',
  row_error: 'Row error',
};

const WARNING_TEXT: Record<string, string> = {
  holds_more: 'Holds more than the template',
  rows_disagree: 'Rows disagree on companies',
};

const FACET_TEXT: Record<string, string> = {
  access_types: 'Access types',
  companies: 'Companies',
  brands: 'Brands',
  stock_check_mode: 'Stock mode',
  stock_mode: 'Stock mode',
  stock_locations: 'Locations',
  market_segments: 'Segments',
  media: 'Media',
  agent_access: 'Agent access',
  customers: 'Accounts',
  chatbot_stock_allowed: 'Stock',
  chatbot_eta_offset_applied: 'ETA buffer',
  chatbot_allowed: 'AI replies',
  escalation_allowed: 'Escalation',
  packing_list_allowed: 'Packing list',
};

const ROLE_TEXT = { owner: 'Business Owner', employee: 'Employee' } as const;

// BULK-ACCESS-PREVIEW (owner 27 Oct): the preview shows everything, so cells wrap, never truncate.
function Cell({ children }: { children: React.ReactNode }) {
  return <td className="px-2 py-1.5 align-top break-words">{children}</td>;
}

/**
 * BULK-CONTACT-ACCESS (UAC U11, U13-U15, U20): Import access sheet. Upload the Respond export,
 * read the server's preview (a dry run, nothing written), confirm each dealer's accounts, apply
 * in one call, read the result. A failed read stays on upload; a failed apply stays on preview.
 */
export default function AccessSheetImportDialog({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const [step, setStep] = useState<Step>('upload');
  const [files, setFiles] = useState<File[]>([]);
  const [preview, setPreview] = useState<AccessSheetResult | null>(null);
  const [result, setResult] = useState<AccessSheetResult | null>(null);
  const [selection, setSelection] = useState<AccessSheetSelection | null>(null);
  // Labels of customers found by search, kept here so a collapsed block remembers its picks.
  const [extraLabels, setExtraLabels] = useState<Record<string, string>>({});
  const previewMutation = usePreviewAccessSheet();
  const applyMutation = useApplyAccessSheet();
  const file = files[0] ?? null;
  const busy = previewMutation.isPending || applyMutation.isPending;

  const reset = () => {
    setStep('upload');
    setFiles([]);
    setPreview(null);
    setResult(null);
    setSelection(null);
    setExtraLabels({});
  };
  const close = (next: boolean) => {
    if (!next) reset();
    onOpenChange(next);
  };

  const runPreview = async () => {
    if (!file) return;
    try {
      const out = await previewMutation.mutateAsync(file);
      setPreview(out);
      setSelection(initialSelection(out));
      setStep('preview');
    } catch {
      // The hook toasted the reason; the dialog stays on upload.
    }
  };

  const runApply = async () => {
    if (!file || !selection) return;
    try {
      const out = await applyMutation.mutateAsync({ file, confirmed: toConfirmedPayload(selection) });
      setResult(out);
      setStep('result');
    } catch {
      // The hook toasted the reason; the dialog stays on the preview.
    }
  };

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="max-h-[90dvh] sm:max-w-5xl">
        <DialogHeader>
          <DialogTitle>
            {step === 'upload'
              ? 'Import access sheet'
              : step === 'preview'
                ? `Preview: ${file?.name ?? ''}`
                : 'Import finished'}
          </DialogTitle>
        </DialogHeader>
        <DialogBody className="space-y-4">
          {step === 'upload' ? (
            <FileDropzone
              files={files}
              onFilesChange={setFiles}
              onReject={(rejected, reason) =>
                toast.error(
                  reason === 'size'
                    ? `${rejected.name} is larger than 2 MB.`
                    : reason === 'extra'
                      ? `${rejected.name} was not used - one file at a time.`
                      : `${rejected.name} is not a CSV file.`,
                )
              }
              accept=".csv,text/csv"
              maxSizeMb={2}
              disabled={busy}
              inputTestId="access-sheet-file"
              aria-label="Access sheet file"
            />
          ) : null}
          {busy ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <LoaderCircle className="size-4 animate-spin" aria-hidden />
              {previewMutation.isPending ? 'Reading the file...' : 'Applying...'}
            </div>
          ) : null}
          {step === 'preview' && preview && selection ? (
            <PreviewStep
              preview={preview}
              selection={selection}
              onChange={setSelection}
              extraLabels={extraLabels}
              onExtraLabels={(found) => setExtraLabels((prev) => ({ ...prev, ...found }))}
            />
          ) : null}
          {step === 'result' && result ? <ResultStep result={result} /> : null}
        </DialogBody>
        <DialogFooter>
          {step === 'upload' ? (
            <>
              <Button variant="outline" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button onClick={() => void runPreview()} disabled={!file || busy}>
                Preview
              </Button>
            </>
          ) : null}
          {step === 'preview' ? (
            <>
              <Button variant="outline" onClick={() => setStep('upload')} disabled={busy}>
                Back
              </Button>
              <Button onClick={() => void runApply()} disabled={busy}>
                Apply access
              </Button>
            </>
          ) : null}
          {step === 'result' && result ? (
            <>
              <Button
                variant="outline"
                onClick={() =>
                  saveBlobAs(new Blob([resultCsv(result)], { type: 'text/csv;charset=utf-8' }), 'access-sheet-result.csv')
                }
              >
                <Download className="size-4" />
                Download result
              </Button>
              <Button onClick={() => close(false)}>Done</Button>
            </>
          ) : null}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function Chips({ items }: { items: (string | null)[] }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {items.filter(Boolean).map((text) => (
        <Badge key={text} variant="secondary" appearance="light" size="sm">
          {text}
        </Badge>
      ))}
    </div>
  );
}

function PreviewStep({
  preview,
  selection,
  onChange,
  extraLabels,
  onExtraLabels,
}: {
  preview: AccessSheetResult;
  selection: AccessSheetSelection;
  onChange: (next: AccessSheetSelection) => void;
  extraLabels: Record<string, string>;
  onExtraLabels: (found: Record<string, string>) => void;
}) {
  const { counts } = preview;
  const allConfirmed = allExactConfirmed(preview, selection);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <Chips
          items={[
            `${counts.rows} contacts in sheet`,
            `${counts.contacts_found} found in CRM`,
            counts.not_in_crm ? `${counts.not_in_crm} not in CRM yet` : null,
            counts.ambiguous ? `${counts.ambiguous} with a shared phone` : null,
            counts.row_errors ? `${counts.row_errors} rows with errors` : null,
            counts.already_configured ? `${counts.already_configured} already have access` : null,
            `${counts.blocks} dealers`,
          ]}
        />
        <span className="flex-1" />
        <Button
          variant="outline"
          size="sm"
          disabled={counts.blocks_exact === 0 || allConfirmed}
          onClick={() => onChange(confirmAllExact(preview, selection))}
        >
          {allConfirmed ? 'All exact confirmed' : 'Confirm all exact'}
        </Button>
      </div>
      {preview.errors.length ? (
        <ul className="space-y-0.5 text-xs text-muted-foreground">
          {preview.errors.map((e) => (
            <li key={`${e.line}:${e.reason}`} className="break-words">
              {`Line ${e.line}: ${e.reason}`}
            </li>
          ))}
        </ul>
      ) : null}
      <BlockList
        blocks={preview.blocks}
        dryRun
        selection={selection}
        onChange={onChange}
        extraLabels={extraLabels}
        onExtraLabels={onExtraLabels}
      />
    </div>
  );
}

function ResultStep({ result }: { result: AccessSheetResult }) {
  const { counts } = result;
  return (
    <div className="space-y-3">
      <Chips
        items={[
          `Applied ${counts.applied} contacts`,
          `Skipped ${counts.skipped}`,
          counts.no_change ? `No change ${counts.no_change}` : null,
        ]}
      />
      <BlockList blocks={result.blocks} />
    </div>
  );
}

function BlockList({
  blocks,
  dryRun = false,
  selection,
  onChange,
  extraLabels = {},
  onExtraLabels,
}: {
  blocks: AccessSheetBlock[];
  dryRun?: boolean;
  selection?: AccessSheetSelection;
  onChange?: (next: AccessSheetSelection) => void;
  extraLabels?: Record<string, string>;
  onExtraLabels?: (found: Record<string, string>) => void;
}) {
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>(() =>
    blocks[0] ? { [blocks[0].key]: true } : {},
  );
  return (
    <div className="max-h-[60dvh] space-y-2 overflow-auto">
      {blocks.map((block) => {
        const isOpen = !!openKeys[block.key];
        const badge = BLOCK_BADGE[block.status];
        return (
          <div key={block.key} className="rounded-lg border">
            <div className="flex flex-wrap items-center gap-2 px-3 py-2">
              {selection && onChange ? (
                <Checkbox
                  aria-label={`Confirm ${block.dealer}`}
                  checked={!!selection.confirmed[block.key]}
                  onCheckedChange={(v) => onChange(setConfirmed(selection, block.key, v === true))}
                />
              ) : null}
              <button
                type="button"
                className="flex min-w-0 flex-1 items-center gap-2 text-start"
                aria-expanded={isOpen}
                onClick={() => setOpenKeys((prev) => ({ ...prev, [block.key]: !isOpen }))}
              >
                <span className="min-w-0 break-words font-medium">
                  {block.dealer}
                </span>
                {block.companies.map((c) => (
                  <Badge key={c} variant="secondary" appearance="light" size="sm">
                    {c}
                  </Badge>
                ))}
                <Badge variant={badge.variant} appearance="light" size="sm">
                  {badge.label}
                </Badge>
                {block.warnings.map((w) => (
                  <Badge key={w} variant="warning" appearance="light" size="sm">
                    {WARNING_TEXT[w] ?? w}
                  </Badge>
                ))}
                <span className="flex-1" />
                {isOpen ? <ChevronUp className="size-4" aria-hidden /> : <ChevronDown className="size-4" aria-hidden />}
              </button>
            </div>
            {isOpen ? (
              <div className="space-y-3 border-t px-3 py-3">
                {selection && onChange ? (
                  <AccountsTable block={block} selection={selection} onChange={onChange} />
                ) : null}
                {selection && onChange && block.status !== 'exact' ? (
                  <ExtraCustomers
                    block={block}
                    selection={selection}
                    onChange={onChange}
                    labels={extraLabels}
                    onLabels={onExtraLabels}
                  />
                ) : null}
                <div className="space-y-2">
                  {block.contacts.map((c) => (
                    <ContactPanel key={`${c.line}:${c.phone}`} contact={c} dryRun={dryRun} />
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

/** An admin CHOICE: a ticked account that is not a pre-ticked exact one (a candidate or a searched account). */
function hasChoice(block: AccessSheetBlock, sel: AccessSheetSelection): boolean {
  const exact = new Set(block.accounts.filter((a) => a.match === 'exact').map((a) => a.customer_id));
  return (sel.ticked[block.key] ?? []).some((id) => !exact.has(id));
}

function AccountsTable({
  block,
  selection,
  onChange,
}: {
  block: AccessSheetBlock;
  selection: AccessSheetSelection;
  onChange: (next: AccessSheetSelection) => void;
}) {
  if (!block.accounts.length) return null;
  const ticked = selection.ticked[block.key] ?? [];
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[46rem] table-fixed text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="w-10 px-2 py-1 text-start font-medium" />
            <th className="w-28 px-2 py-1 text-start font-medium">Debtor code</th>
            <th className="w-64 px-2 py-1 text-start font-medium">Account name</th>
            <th className="w-20 px-2 py-1 text-start font-medium">Company</th>
            <th className="w-20 px-2 py-1 text-start font-medium">Active</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Account agent</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Sheet agent</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Links to</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {block.accounts.map((a: AccessSheetAccount) => (
            <tr key={a.customer_id}>
              <td className="px-2 py-1.5">
                <Checkbox
                  aria-label={`Link ${a.customer_code}`}
                  checked={ticked.includes(a.customer_id)}
                  onCheckedChange={() => {
                    const next = toggleTicked(selection, block.key, a.customer_id);
                    // Ticking an account is the admin's say-so for a pick/none dealer; none ticked = not confirmed.
                    onChange(
                      block.status === 'exact'
                        ? next
                        : setConfirmed(next, block.key, hasChoice(block, next)),
                    );
                  }}
                />
              </td>
              <Cell>{a.customer_code}</Cell>
              <Cell>
                {a.customer_name}
                {a.match === 'candidate' && a.score !== null ? ` (${a.score.toFixed(2)})` : ''}
              </Cell>
              <Cell>{a.company_code ?? '-'}</Cell>
              <Cell>{a.is_active ? 'Yes' : 'No'}</Cell>
              <Cell>{a.sales_agent ?? '-'}</Cell>
              <Cell>{a.sheet_agent ?? '-'}</Cell>
              <Cell>
                {a.links_to.length ? (
                  <ul>
                    {a.links_to.map((name, i) => (
                      <li key={`${name}:${i}`}>{name}</li>
                    ))}
                  </ul>
                ) : (
                  <span className="text-muted-foreground">Nobody</span>
                )}
              </Cell>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Customers found by search, for a dealer the sheet text did not match exactly. */
function ExtraCustomers({
  block,
  selection,
  onChange,
  labels,
  onLabels,
}: {
  block: AccessSheetBlock;
  selection: AccessSheetSelection;
  onChange: (next: AccessSheetSelection) => void;
  labels: Record<string, string>;
  onLabels?: (found: Record<string, string>) => void;
}) {
  const picker = useCustomerMultiPicker(() => false, undefined, { allGrantedCompanies: true });
  const known = new Set(block.accounts.map((a) => a.customer_id));
  const ticked = selection.ticked[block.key] ?? [];
  const extra = ticked.filter((id) => !known.has(id));
  const fetchOptions = async (query: string) => {
    const options = await picker.fetchOptions(query);
    onLabels?.(Object.fromEntries(options.map((o) => [o.value, o.label])));
    return options;
  };
  return (
    <SearchableMultiSelect
      value={extra}
      onChange={(ids) => {
        const next = setTicked(selection, block.key, [...ticked.filter((id) => known.has(id)), ...ids]);
        // Picking an account is the admin's say-so for this dealer; none ticked = not confirmed.
        onChange(setConfirmed(next, block.key, hasChoice(block, next)));
      }}
      fetchOptions={fetchOptions}
      selectedOptions={extra.map((id) => ({ value: id, label: labels[id] ?? 'Customer' }))}
      placeholder="Search customers"
      emptyMessage="No customers match."
      className="w-full"
    />
  );
}

const HOLDS_MORE_FACET: Record<string, string> = {
  access_types: 'Access types',
  companies: 'Companies',
  stock_locations: 'Locations',
  brands: 'Brands',
};

function ItemList({ label, items }: { label: string; items: ChangeItem[] }) {
  return (
    <div className="border-t px-3 py-1.5 sm:border-t">
      <div className="text-xs text-muted-foreground sm:hidden">{label}</div>
      <ul className="break-words">
        {items.length ? (
          items.map((item, i) => (
            <li key={`${item.text}:${i}`} className={item.added ? 'font-medium text-success' : undefined}>
              {item.added ? (
                <>
                  <span aria-hidden>+ </span>
                  <span className="sr-only">added: </span>
                  <span data-testid="added-item">{item.text}</span>
                </>
              ) : (
                item.text
              )}
            </li>
          ))
        ) : (
          <li className="text-muted-foreground">None</li>
        )}
      </ul>
    </div>
  );
}

/** One contact: header, every changed setting as before -> after, then the info lines. */
function ContactPanel({ contact: c, dryRun }: { contact: AccessSheetContact; dryRun: boolean }) {
  const status = c.skip_reason
    ? { label: SKIP_TEXT[c.skip_reason] ?? c.skip_reason, variant: 'secondary' as const }
    : c.status === 'no_change'
      ? { label: 'No changes', variant: 'secondary' as const }
      : { label: dryRun ? 'Will change' : 'Applied', variant: 'success' as const };
  const planned = c.in_crm && !c.skip_reason;
  const unchanged = planned ? unchangedFacets(c).map((f) => FACET_TEXT[f] ?? f) : [];
  return (
    <div className="rounded-lg border text-sm" data-testid={`contact-${c.name}`}>
      <div className="flex flex-wrap items-center gap-2 bg-muted/40 px-3 py-2">
        <span className="font-medium break-words">{c.name || '-'}</span>
        <span className="text-muted-foreground">{c.phone}</span>
        <Badge variant="secondary" appearance="light" size="sm">
          {ROLE_TEXT[c.role] ?? c.role}
        </Badge>
        <Badge variant="secondary" appearance="light" size="sm">
          {`Template ${c.template}`}
        </Badge>
        <span className="flex-1" />
        <Badge variant={status.variant} appearance="light" size="sm">
          {status.label}
        </Badge>
      </div>
      {c.changes.length ? (
        <div className="grid grid-cols-1 sm:grid-cols-[9rem_minmax(0,1fr)_1.5rem_minmax(0,1fr)]">
          <div className="hidden border-t px-3 py-1 text-xs text-muted-foreground sm:block">Setting</div>
          <div className="hidden border-t px-3 py-1 text-xs text-muted-foreground sm:block">Before</div>
          <div className="hidden border-t sm:block" />
          <div className="hidden border-t px-3 py-1 text-xs text-muted-foreground sm:block">After</div>
          {c.changes.map((change) => {
            const lines = changeLines(change);
            return (
              <Fragment key={change.facet}>
                <div className="border-t bg-muted/20 px-3 py-1.5 font-medium sm:bg-transparent">
                  {FACET_TEXT[change.facet] ?? change.facet}
                </div>
                <ItemList label="Before" items={lines.before} />
                <div className="hidden border-t py-1.5 text-center text-muted-foreground sm:block" aria-hidden>
                  &rarr;
                </div>
                <ItemList label="After" items={lines.after} />
              </Fragment>
            );
          })}
        </div>
      ) : null}
      {unchanged.length ? (
        <div className="border-t px-3 py-1.5 text-xs text-muted-foreground">{`No change: ${unchanged.join(', ')}`}</div>
      ) : null}
      {c.not_applied.length ? (
        <div className="border-t px-3 py-1.5 text-xs text-muted-foreground">
          {`Not applied (no permission): ${c.not_applied.map((f) => FACET_TEXT[f] ?? f).join(', ')}`}
        </div>
      ) : null}
      {c.holds_more_items.length ? (
        <div className="border-t p-2">
          <Alert variant="warning" appearance="light" size="sm">
            <AlertContent>
              <AlertTitle>Holds more than the template (kept)</AlertTitle>
              <AlertDescription>
                <ul className="list-disc ps-4">
                  {c.holds_more_items.map((h) => (
                    <li key={h.facet}>{`${HOLDS_MORE_FACET[h.facet] ?? h.facet}: ${h.items.join(', ')}`}</li>
                  ))}
                </ul>
              </AlertDescription>
            </AlertContent>
          </Alert>
        </div>
      ) : null}
      {c.outside_links.length ? (
        <div className="border-t p-2">
          <Alert variant="info" appearance="light" size="sm">
            <AlertContent>
              <AlertTitle>Linked outside this row&apos;s companies (kept, not removed)</AlertTitle>
              <AlertDescription>
                <ul className="list-disc ps-4">
                  {c.outside_links.map((label) => (
                    <li key={label}>{label}</li>
                  ))}
                </ul>
              </AlertDescription>
            </AlertContent>
          </Alert>
        </div>
      ) : null}
    </div>
  );
}
