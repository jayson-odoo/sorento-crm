'use client';

import { useState } from 'react';
import { ChevronDown, ChevronUp, Download, LoaderCircle } from 'lucide-react';
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
  AccessSheetChange,
  AccessSheetContact,
  AccessSheetResult,
} from '@/services/contactAccessSheetService';
import { useApplyAccessSheet, usePreviewAccessSheet } from '../hooks/useAccessSheetImport';
import {
  allExactConfirmed,
  confirmAllExact,
  initialSelection,
  resultCsv,
  setConfirmed,
  setTicked,
  toConfirmedPayload,
  toggleTicked,
  type AccessSheetSelection,
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

function describeChange(change: AccessSheetChange): string {
  const label = FACET_TEXT[change.facet] ?? change.facet;
  const { before, after } = change;
  if (Array.isArray(before) && Array.isArray(after)) {
    const added = after.filter((v) => !before.includes(v));
    return `${label}: + ${added.join(', ')}`;
  }
  if (Array.isArray(after) && typeof before === 'string') return `${label}: ${before} -> ${after.join(', ')}`;
  if (typeof after === 'boolean') return `${label}: ${after ? 'on' : 'off'}`;
  return `${label}: ${String(after ?? '')}`;
}

function Cell({ children, title, className = '' }: { children: React.ReactNode; title?: string; className?: string }) {
  return (
    <td className={`px-2 py-1.5 ${className}`}>
      <div className="truncate" title={title}>
        {children}
      </div>
    </td>
  );
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
            <li key={`${e.line}:${e.reason}`} className="truncate" title={e.reason}>
              {`Line ${e.line}: ${e.reason}`}
            </li>
          ))}
        </ul>
      ) : null}
      <BlockList
        blocks={preview.blocks}
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
  selection,
  onChange,
  extraLabels = {},
  onExtraLabels,
}: {
  blocks: AccessSheetBlock[];
  selection?: AccessSheetSelection;
  onChange?: (next: AccessSheetSelection) => void;
  extraLabels?: Record<string, string>;
  onExtraLabels?: (found: Record<string, string>) => void;
}) {
  const [openKeys, setOpenKeys] = useState<Record<string, boolean>>(() =>
    blocks[0] ? { [blocks[0].key]: true } : {},
  );
  return (
    <div className="max-h-[50dvh] space-y-2 overflow-auto">
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
                <span className="min-w-0 truncate font-medium" title={block.dealer}>
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
                <ContactsTable contacts={block.contacts} />
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
      <table className="w-full min-w-[40rem] table-fixed text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="w-10 px-2 py-1 text-start font-medium" />
            <th className="w-28 px-2 py-1 text-start font-medium">Debtor code</th>
            <th className="w-64 px-2 py-1 text-start font-medium">Account name</th>
            <th className="w-20 px-2 py-1 text-start font-medium">Company</th>
            <th className="w-20 px-2 py-1 text-start font-medium">Active</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Account agent</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Sheet agent</th>
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
              <Cell title={a.customer_code}>{a.customer_code}</Cell>
              <Cell title={a.customer_name}>
                {a.customer_name}
                {a.match === 'candidate' && a.score !== null ? ` (${a.score.toFixed(2)})` : ''}
              </Cell>
              <Cell>{a.company_code ?? '-'}</Cell>
              <Cell>{a.is_active ? 'Yes' : 'No'}</Cell>
              <Cell title={a.sales_agent ?? undefined}>{a.sales_agent ?? '-'}</Cell>
              <Cell title={a.sheet_agent ?? undefined}>{a.sheet_agent ?? '-'}</Cell>
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

function ContactsTable({ contacts }: { contacts: AccessSheetContact[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[56rem] table-fixed text-sm">
        <thead className="text-xs text-muted-foreground">
          <tr>
            <th className="w-28 px-2 py-1 text-start font-medium">Name</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Phone</th>
            <th className="w-20 px-2 py-1 text-start font-medium">In CRM</th>
            <th className="w-32 px-2 py-1 text-start font-medium">Role</th>
            <th className="w-36 px-2 py-1 text-start font-medium">Template</th>
            <th className="w-72 px-2 py-1 text-start font-medium">Changes</th>
            <th className="w-48 px-2 py-1 text-start font-medium">Warnings</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {contacts.map((c) => {
            const changes = c.changes.map(describeChange).join('; ');
            const warnings = [
              ...c.warnings.map((w) => WARNING_TEXT[w] ?? w),
              ...c.not_applied.map((f) => `Not applied: ${FACET_TEXT[f] ?? f}`),
            ].join('; ');
            const outcome = c.skip_reason
              ? SKIP_TEXT[c.skip_reason] ?? c.skip_reason
              : c.status === 'no_change'
                ? 'No changes'
                : changes;
            return (
              <tr key={`${c.line}:${c.phone}`}>
                <Cell title={c.name}>{c.name || '-'}</Cell>
                <Cell title={c.phone}>{c.phone}</Cell>
                <Cell>{c.in_crm ? 'Yes' : 'No'}</Cell>
                <Cell>{ROLE_TEXT[c.role] ?? c.role}</Cell>
                <Cell title={c.template}>{c.template}</Cell>
                <Cell title={outcome}>{outcome}</Cell>
                <Cell title={warnings}>{warnings || '-'}</Cell>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
