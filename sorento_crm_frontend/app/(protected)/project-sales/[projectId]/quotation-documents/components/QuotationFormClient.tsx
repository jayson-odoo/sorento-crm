'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { FileText, ListOrdered, Mail, Plus, ScrollText, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/common/PageHeader';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { useHasPermission } from '@/hooks/usePermissions';
import { projectCrumbs } from '../../../_shared/lib/crumbs';
import {
  useProject,
  useProjectSeries,
  useQuotationLines,
  useQuotations,
  useQuotationVersions,
} from '../../../_shared/hooks/useProjects';
import {
  useQuotationDocument,
  useQuotationDocumentMutations,
  useQuotationLetterTemplates,
} from '../../../_shared/hooks/useQuotationDocuments';
import type {
  QuotationDocument,
  QuotationDocumentBody,
  QuotationFormScopeBody,
} from '../../../_shared/services/quotationDocumentService';
import type { QuotationLine } from '../../../_shared/types/project.types';
import {
  formLinesToBody,
  formLinesTotal,
  lineToFormLine,
  invalidNumberLines,
  unfinishedLines,
  type QuotationFormLine,
} from '../../../_shared/lib/quotationLineDraft';
import { sumMoney } from '../../../_shared/lib/money';
import { QuotationLinesGrid } from '../../components/QuotationLinesGrid';
import {
  QuotationDocumentHeader,
  useQuotationHeaderDetails,
} from '../[documentId]/components/QuotationDocumentHeader';
import {
  QuotationCoverLetterPanel,
  QuotationTermsPanel,
} from '../[documentId]/components/QuotationLetterPanels';

/** One scope as the form holds it until Save. */
type FormScope = {
  key: string;
  /** The saved scope's id, or null for one added on this form. */
  id: string | null;
  scope_label: string;
  series_id: string;
  lines: QuotationFormLine[];
  /**
   * Whether its lines may change: the server's `is_editable` on the current version. A version
   * the customer holds (or a superseded one) is read here and never sent back, the same rule the
   * server enforces with its 422.
   */
  editable: boolean;
  /** A saved scope's lines have arrived from the server. A new scope starts seeded. */
  seeded: boolean;
  /**
   * Any version of it was sent to the customer. Such a scope cannot be removed (#1341, owner on
   * Q2: "yes can", while nothing in it has been issued); the server refuses it too.
   */
  issued: boolean;
};

type FormTab = 'header' | 'lines' | 'cover-letter' | 'terms';

/**
 * The form's tabs, the read page's minus Signatures (#1341, owner: "header stays in header tab").
 * Same order, same labels, same icons, so view and edit read as one layout.
 */
const FORM_TABS: {
  key: FormTab;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { key: 'header', title: 'Header', icon: FileText },
  { key: 'lines', title: 'Lines', icon: ListOrdered },
  { key: 'cover-letter', title: 'Cover letter', icon: Mail },
  { key: 'terms', title: 'Terms', icon: ScrollText },
];

const HEADER_FIELDS = [
  'your_ref',
  'doc_date',
  'attn_name',
  'subject_title',
  'recipient_name_snapshot',
  'recipient_address_snapshot',
  'recipient_phone_snapshot',
] as const;

let scopeCounter = 0;
function newScope(): FormScope {
  scopeCounter += 1;
  return {
    key: `new-scope:${scopeCounter}`,
    id: null,
    scope_label: '',
    series_id: '',
    lines: [],
    editable: true,
    seeded: true,
    issued: false,
  };
}

/**
 * A scope added on this form and never touched: no name, no line. Header-only is a real save
 * (owner on Q3: "yes can, header only is fine"), so this one is left out rather than refused.
 */
function isUntouchedNewScope(scope: FormScope): boolean {
  return (
    !scope.id && !scope.scope_label.trim() && !scope.series_id && scope.lines.length === 0
  );
}

/** Today in the browser's own calendar, as the ISO date the API speaks. */
function todayIso(): string {
  const now = new Date();
  const month = String(now.getMonth() + 1).padStart(2, '0');
  const day = String(now.getDate()).padStart(2, '0');
  return `${now.getFullYear()}-${month}-${day}`;
}

/**
 * The quotation form page, create and edit (#1341).
 *
 * The owner: "I should be able to add product straight away and save when I am satisfied, if I
 * want to edit I can click on the gear button to edit". So Add a quotation lands HERE with nothing
 * written, the page holds the letterhead and the scopes with their lines, and Save is ONE request:
 * a POST that creates the quotation, its scopes and every line in one transaction, or, in edit
 * mode, one PATCH carrying the header and every scope. Cancel leaves exactly what was there.
 *
 * Edit is the same page with the same tabs in the same order (view and edit share a layout):
 * Header, Lines, Cover letter, Terms, the read page's own tabs minus Signatures. The owner: "header
 * stays in header tab", and the letter and terms "show them on create as well", prefilled from the
 * company templates. Status rules are the server's: a scope the customer holds shows its lines
 * read-only, and a scope any version of which was sent cannot be removed.
 */
export function QuotationFormClient({
  projectId,
  documentId,
}: {
  projectId: string;
  documentId?: string;
}) {
  const router = useRouter();
  const isEdit = Boolean(documentId);
  const project = useProject(projectId);
  const saved = useQuotationDocument(projectId, documentId);
  const quotations = useQuotations(isEdit ? projectId : undefined);
  const series = useProjectSeries();
  const mutations = useQuotationDocumentMutations(projectId, documentId);
  // The company's letter and terms, for the create form's own tabs. Edit reads the saved text.
  const letterTemplates = useQuotationLetterTemplates(projectId, !isEdit);
  // Removing a saved scope is a hard delete: the same grant as the scope DELETE route.
  const canRemoveSaved = useHasPermission('projects.projects.delete');

  const [header, setHeader] = React.useState<QuotationDocumentBody | null>(
    null,
  );
  const [letter, setLetter] = React.useState<QuotationDocumentBody>({});
  /** The create form's letter tabs have taken the templates, once. */
  const [letterSeeded, setLetterSeeded] = React.useState(false);
  const [scopes, setScopes] = React.useState<FormScope[] | null>(null);
  /** Saved scopes removed on this form, deleted by the one PATCH (#1341, Q2). */
  const [removedIds, setRemovedIds] = React.useState<string[]>([]);
  const [tab, setTab] = React.useState<FormTab>('header');
  const savedScopes = saved.data?.scopes;
  const keptScopes = React.useMemo(
    () => (savedScopes ?? []).filter((scope) => !removedIds.includes(scope.id)),
    [savedScopes, removedIds],
  );
  const details = useQuotationHeaderDetails(isEdit ? projectId : undefined, keptScopes);
  const [error, setError] = React.useState<string | null>(null);
  const [isSaving, setIsSaving] = React.useState(false);
  /** Anything typed since the page opened. Drives the warning on leaving the site. */
  const [dirty, setDirty] = React.useState(false);

  // Everything on this page lives only in the browser until Save, so a refresh or a closed tab
  // would lose it silently. Warn while there is something to lose.
  React.useEffect(() => {
    if (!dirty || isSaving) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty, isSaving]);

  // The starting point, taken ONCE: a refetch landing mid-edit must not overwrite what somebody
  // is typing.
  React.useEffect(() => {
    if (header !== null) return;
    if (!isEdit && project.data) {
      setHeader({
        your_ref: '',
        doc_date: todayIso(),
        attn_name: '',
        subject_title: project.data.title ?? '',
        recipient_name_snapshot: project.data.developer_name ?? '',
        recipient_address_snapshot: '',
        recipient_phone_snapshot: '',
      });
      setScopes([newScope()]);
    }
    if (isEdit && saved.data && quotations.data) {
      const document = saved.data;
      setHeader(
        Object.fromEntries(
          HEADER_FIELDS.map((field) => [
            field,
            (document[field] as string | null) ?? '',
          ]),
        ) as QuotationDocumentBody,
      );
      setScopes(
        document.scopes.map((scope) => ({
          key: scope.id,
          id: scope.id,
          scope_label: scope.scope_label,
          series_id:
            (quotations.data ?? []).find((row) => row.id === scope.id)
              ?.series_id ?? '',
          lines: [],
          editable: false,
          seeded: false,
          issued: false,
        })),
      );
    }
  }, [header, isEdit, project.data, quotations.data, saved.data]);

  // Create: the letter and terms tabs start from the company templates, taken once so a late
  // refetch cannot overwrite what was typed. No template leaves the tab empty and editable.
  React.useEffect(() => {
    if (isEdit || letterSeeded || !letterTemplates.isFetched) return;
    setLetter({
      cover_letter_html: letterTemplates.data?.cover_letter_html ?? '',
      terms_html: letterTemplates.data?.terms_html ?? '',
    });
    setLetterSeeded(true);
  }, [isEdit, letterSeeded, letterTemplates.isFetched, letterTemplates.data]);

  /** A saved scope's lines arriving from the server: a starting point, not an edit. */
  const seedScope = React.useCallback(
    (key: string, patch: Partial<FormScope>) => {
      setScopes((previous) =>
        (previous ?? []).map((scope) =>
          scope.key === key ? { ...scope, ...patch } : scope,
        ),
      );
    },
    [],
  );

  const updateScope = React.useCallback(
    (key: string, patch: Partial<FormScope>) => {
      setDirty(true);
      setScopes((previous) =>
        (previous ?? []).map((scope) =>
          scope.key === key ? { ...scope, ...patch } : scope,
        ),
      );
    },
    [],
  );

  const liveTotal = React.useMemo(
    () =>
      sumMoney(
        (scopes ?? []).map((scope) => formLinesTotal(scope.lines) ?? '0'),
      ),
    [scopes],
  );

  const backPath = isEdit
    ? `/project-sales/${projectId}/quotation-documents/${documentId}`
    : `/project-sales/${projectId}?tab=quotations`;
  const title = isEdit
    ? (saved.data?.document_no ?? 'Edit quotation')
    : 'New quotation';
  const allSeeded = (scopes ?? []).every((scope) => scope.seeded);
  const letterReady = isEdit || letterSeeded;

  /** The scopes Save sends: an untouched new scope is not one (header-only save). */
  function scopesToSave(): FormScope[] {
    return (scopes ?? []).filter((scope) => !isUntouchedNewScope(scope));
  }

  function validate(): string | null {
    const list = scopesToSave();
    if (list.some((scope) => !scope.scope_label.trim())) {
      return 'Every scope needs a name, e.g. Townhouse or Guard House.';
    }
    const unfinished = list
      .filter((scope) => scope.editable)
      .reduce((total, scope) => total + unfinishedLines(scope.lines), 0);
    if (unfinished > 0) {
      return unfinished === 1
        ? 'One line still needs a product or a description.'
        : `${unfinished} lines still need a product or a description.`;
    }
    // Caught here rather than as a 422 toast: the field already says "Must be a number".
    const badNumbers = list
      .filter((scope) => scope.editable)
      .reduce((total, scope) => total + invalidNumberLines(scope.lines), 0);
    if (badNumbers > 0) {
      return badNumbers === 1
        ? 'One line has a quantity or unit price that is not a number.'
        : `${badNumbers} lines have a quantity or unit price that is not a number.`;
    }
    return null;
  }

  function headerBody(): QuotationDocumentBody {
    const body: QuotationDocumentBody = {};
    HEADER_FIELDS.forEach((field) => {
      const value = ((header ?? {})[field] as string | null | undefined) ?? '';
      (body as Record<string, string | null>)[field] = value.trim()
        ? value
        : null;
    });
    return body;
  }

  function scopesBody(): QuotationFormScopeBody[] {
    return scopesToSave().map((scope) => {
      const item: QuotationFormScopeBody = {
        scope_label: scope.scope_label.trim(),
        series_id: scope.series_id || null,
      };
      if (scope.id) item.id = scope.id;
      // A version the customer holds is never sent: the server would refuse the whole save.
      if (scope.editable && scope.seeded)
        item.lines = formLinesToBody(scope.lines);
      return item;
    });
  }

  /** Create: the letter tabs' text, when there is any. Empty lets the server render the template. */
  function createLetterBody(): QuotationDocumentBody {
    const body: QuotationDocumentBody = {};
    if ((letter.cover_letter_html ?? '').trim()) body.cover_letter_html = letter.cover_letter_html;
    if ((letter.terms_html ?? '').trim()) body.terms_html = letter.terms_html;
    return body;
  }

  async function save() {
    const problem = validate();
    setError(problem);
    // Every refusal is about a scope or a line, so show the tab it is on.
    if (problem) {
      setTab('lines');
      return;
    }
    setIsSaving(true);
    try {
      if (isEdit && documentId) {
        await mutations.update.mutateAsync({
          id: documentId,
          body: {
            ...headerBody(),
            ...letter,
            scopes: scopesBody(),
            ...(removedIds.length > 0 ? { remove_scope_ids: removedIds } : {}),
          },
        });
        router.push(
          `/project-sales/${projectId}/quotation-documents/${documentId}`,
        );
      } else {
        const created = await mutations.create.mutateAsync({
          ...headerBody(),
          ...createLetterBody(),
          scopes: scopesBody(),
        });
        router.push(
          `/project-sales/${projectId}/quotation-documents/${created.id}`,
        );
      }
    } catch {
      // The mutation toasted the server's reason; the form keeps everything that was typed.
    } finally {
      setIsSaving(false);
    }
  }

  const loading =
    project.isLoading ||
    (isEdit && (saved.isLoading || quotations.isLoading)) ||
    !header;
  const failed = isEdit && (saved.isError || (!saved.isLoading && !saved.data));

  const shownDocument: QuotationDocument = {
    ...(saved.data ?? placeholderDocument(projectId)),
    ...(header ?? {}),
  } as QuotationDocument;

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        crumbs={projectCrumbs(projectId, { title })}
        actions={
          <>
            <Button
              type="button"
              variant="outline"
              onClick={() => router.push(backPath)}
            >
              Cancel
            </Button>
            <Button
              type="button"
              disabled={isSaving || loading || failed || !allSeeded || !letterReady}
              onClick={() => void save()}
            >
              {isSaving ? 'Saving...' : 'Save quotation'}
            </Button>
          </>
        }
      />

      {error && (
        <p
          role="alert"
          className="rounded-md border border-destructive/40 bg-destructive/5 px-4 py-2 text-sm text-destructive"
        >
          {error}
        </p>
      )}

      {failed ? (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 px-6 py-10 text-center">
          <h2 className="text-sm font-semibold text-destructive">
            This quotation could not be loaded
          </h2>
        </div>
      ) : loading ? (
        <div className="space-y-4">
          <Skeleton className="h-48 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <Tabs value={tab} onValueChange={(value) => setTab(value as FormTab)} className="min-w-0">
          {/* The strip scrolls in its own gutter so the page never drags sideways at 375px. */}
          <div className="min-w-0 overflow-x-auto">
            <TabsList variant="line" className="mb-4 w-max">
              {FORM_TABS.map(({ key, title: tabTitle, icon: Icon }) => (
                <TabsTrigger key={key} value={key}>
                  <Icon className="size-4" aria-hidden />
                  <span>{tabTitle}</span>
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          {/* Every panel stays mounted and is only hidden: a saved scope's lines load inside the
              Lines tab, and Save must be able to wait for them without that tab being opened. */}
          <FormPanel open={tab === 'header'} label="Header">
            <QuotationDocumentHeader
              document={shownDocument}
              liveGrandTotal={liveTotal}
              details={details}
              onChange={(patch) => {
                setDirty(true);
                setHeader((previous) => ({ ...(previous ?? {}), ...patch }));
              }}
            />
          </FormPanel>

          <FormPanel open={tab === 'lines'} label="Lines">
            <div className="space-y-4">
              {(scopes ?? []).map((scope, index) => (
                <ScopeSection
                  key={scope.key}
                  index={index + 1}
                  scope={scope}
                  seriesOptions={(series.data ?? [])
                    .filter((row) => row.is_active || row.id === scope.series_id)
                    .map((row) => ({ value: row.id, label: row.name }))}
                  onChange={(patch) => updateScope(scope.key, patch)}
                  onSeed={(patch) => seedScope(scope.key, patch)}
                  onRemove={
                    // A saved scope goes only once its versions have answered and none was
                    // ever sent to the customer; the server refuses the rest anyway.
                    scope.id && (!canRemoveSaved || !scope.seeded || scope.issued)
                      ? undefined
                      : () => {
                          setDirty(true);
                          if (scope.id) {
                            const savedId = scope.id;
                            setRemovedIds((previous) => [...previous, savedId]);
                          }
                          setScopes((previous) =>
                            (previous ?? []).filter((row) => row.key !== scope.key),
                          );
                        }
                  }
                />
              ))}
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setDirty(true);
                  setScopes((previous) => [...(previous ?? []), newScope()]);
                }}
              >
                <Plus className="size-4" aria-hidden />
                Add a scope
              </Button>
            </div>
          </FormPanel>

          <FormPanel open={tab === 'cover-letter'} label="Cover letter">
            {letterReady ? (
              <QuotationCoverLetterPanel
                html={letter.cover_letter_html ?? saved.data?.cover_letter_html ?? ''}
                onChange={(html) => {
                  setDirty(true);
                  setLetter((previous) => ({ ...previous, cover_letter_html: html }));
                }}
              />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </FormPanel>

          <FormPanel open={tab === 'terms'} label="Terms">
            {letterReady ? (
              <QuotationTermsPanel
                html={letter.terms_html ?? saved.data?.terms_html ?? ''}
                onChange={(html) => {
                  setDirty(true);
                  setLetter((previous) => ({ ...previous, terms_html: html }));
                }}
              />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </FormPanel>
        </Tabs>
      )}
    </div>
  );
}

/**
 * One tab's body. Hidden rather than unmounted when another tab is open, so typed work, a saved
 * scope's loading lines and the letter editors all survive a tab switch.
 */
function FormPanel({
  open,
  label,
  children,
}: {
  open: boolean;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div role="tabpanel" aria-label={label} hidden={!open} className="min-w-0">
      {children}
    </div>
  );
}

/** What the letterhead reads before the server has numbered the quotation. */
function placeholderDocument(projectId: string): QuotationDocument {
  return {
    id: '',
    project_id: projectId,
    document_no: 'Numbered on save',
    our_ref: 'Numbered on save',
    your_ref: null,
    doc_date: null,
    recipient_party_id: null,
    recipient_name_snapshot: null,
    recipient_address_snapshot: null,
    recipient_phone_snapshot: null,
    attn_name: null,
    subject_title: null,
    cover_letter_html: null,
    terms_html: null,
    signatory_name: null,
    signatory_phone: null,
    scopes: [],
    grand_total: '0',
    issue_count: 0,
    current_issue_no: null,
    is_issued: false,
    created_at: null,
    updated_at: null,
  };
}

function ScopeSection({
  index,
  scope,
  seriesOptions,
  onChange,
  onSeed,
  onRemove,
}: {
  index: number;
  scope: FormScope;
  seriesOptions: { value: string; label: string }[];
  onChange: (patch: Partial<FormScope>) => void;
  onSeed: (patch: Partial<FormScope>) => void;
  onRemove?: () => void;
}) {
  const nameId = `quotation-scope-${scope.key}-name`;
  const seriesId = `quotation-scope-${scope.key}-series`;

  return (
    <section aria-label={`Scope ${index}`}>
      <Card>
        <CardHeader className="flex flex-col items-start gap-3 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-sm">
            {scope.scope_label.trim() || `Scope ${index}`}
          </CardTitle>
          {onRemove && (
            <Button
              type="button"
              size="sm"
              variant="outline"
              onClick={onRemove}
            >
              <Trash2 className="size-4" aria-hidden />
              Remove scope
            </Button>
          )}
        </CardHeader>
        <CardContent className="min-w-0 space-y-4 py-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="min-w-0 space-y-1.5">
              <Label htmlFor={nameId}>Scope name</Label>
              <Input
                id={nameId}
                value={scope.scope_label}
                maxLength={150}
                placeholder="e.g. Townhouse, Guard house"
                onChange={(event) =>
                  onChange({ scope_label: event.target.value })
                }
              />
            </div>
            <div className="min-w-0 space-y-1.5">
              <Label htmlFor={seriesId}>Series</Label>
              <SearchableSelect
                id={seriesId}
                value={scope.series_id}
                onChange={(value) => onChange({ series_id: value })}
                options={seriesOptions}
                clearable
                placeholder="No series"
                emptyMessage="No series configured yet"
              />
            </div>
          </div>

          {scope.id && !scope.seeded ? (
            <SavedScopeLines scope={scope} onSeed={onSeed} />
          ) : (
            <>
              {!scope.editable && (
                <p className="text-xs text-muted-foreground">
                  The customer holds this version, so its lines stay as issued.
                </p>
              )}
              <QuotationLinesGrid
                lines={scope.lines}
                onChange={
                  scope.editable ? (lines) => onChange({ lines }) : undefined
                }
                quotationId={scope.id}
                seriesId={scope.series_id || null}
                listingKey="projects.projects.view::project-quotation-lines"
              />
            </>
          )}
        </CardContent>
      </Card>
    </section>
  );
}

/**
 * A saved scope's lines and whether they may change, read once from the server and handed to the
 * form. The version's own `is_editable` decides, never a local guess from its number.
 */
function SavedScopeLines({
  scope,
  onSeed,
}: {
  scope: FormScope;
  onSeed: (patch: Partial<FormScope>) => void;
}) {
  const versions = useQuotationVersions(scope.id ?? undefined);
  const current =
    (versions.data ?? []).find((version) => version.is_current) ?? null;
  const lines = useQuotationLines(current?.id);

  const noVersion = !versions.isLoading && !versions.isError && !current;
  React.useEffect(() => {
    // A scope with no version has nowhere to put a line: it is saved as named, lines untouched.
    if (noVersion) {
      onSeed({ lines: [], editable: false, seeded: true, issued: false });
      return;
    }
    if (!current || !lines.data) return;
    const sorted: QuotationLine[] = [...lines.data].sort(
      (a, b) => a.sort_order - b.sort_order,
    );
    onSeed({
      lines: sorted.map(lineToFormLine),
      editable: Boolean(current.is_editable ?? current.is_current),
      seeded: true,
      // ANY version, not only the open one: a revision opened since does not change what the
      // customer holds, and the server refuses the delete on the same rule.
      issued: (versions.data ?? []).some((version) => Boolean(version.is_issued)),
    });
  }, [current, lines.data, noVersion, onSeed, versions.data]);

  if (versions.isError || lines.isError) {
    // Save stays off: sending this scope without its lines would be a guess about them.
    return (
      <p role="alert" className="text-sm text-destructive">
        This scope&apos;s lines could not be loaded. Reload the page to try
        again.
      </p>
    );
  }
  return <Skeleton className="h-32 w-full" />;
}
