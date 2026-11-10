'use client';

import * as React from 'react';
import { useRouter } from 'next/navigation';
import { FileText, Mail, Plus, ScrollText } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { PageHeader } from '@/components/common/PageHeader';
import { RecordHeaderCard } from '@/components/common/RecordHeaderCard';
import { FormSection } from '@/components/common/FormSection';
import { formatDateInMalaysia } from '@/lib/helpers';
import { STATUS_PILL_BASE, statusPillClass } from '@/lib/status-pill';
import { useHasPermission } from '@/hooks/usePermissions';
import { projectCrumbs } from '../../../_shared/lib/crumbs';
import {
  useProject,
  useProjectQuotationVersions,
  useProjectSeries,
  useQuotations,
  useQuotationVersions,
} from '../../../_shared/hooks/useProjects';
import { quotationStanding } from '../../../_shared/lib/quotationDecision';
import {
  useQuotationDocument,
  useQuotationCoverPreview,
  useQuotationDocumentMutations,
  useQuotationFeedback,
  useQuotationLetterTemplates,
} from '../../../_shared/hooks/useQuotationDocuments';
import {
  documentNoun,
  type QuotationCoverPreviewBody,
  type QuotationDocument,
  type QuotationDocumentBody,
  type QuotationFormScopeBody,
  type QuotationScope,
} from '../../../_shared/services/quotationDocumentService';
import type {
  Project,
  ProjectQuotation,
  QuotationFeedbackRow,
  StagedQuotationLine,
} from '../../../_shared/types/project.types';
import { formatMyrExact, isDecimalString, sumMoney } from '../../../_shared/lib/money';
import type { MatrixHeader } from '../../../_shared/lib/quotationMatrix';
import { QuotationDialog, soleActiveSeriesId } from '../../components/QuotationDialog';
import {
  QuotationVersionEditor,
  stagedLinesToBody,
  stagedScopeTotal,
  unfinishedStagedLines,
  type QuotationScopeEditing,
} from '../../components/QuotationVersionEditor';
import { QuotationNameDialog } from '../[documentId]/components/QuotationNameDialog';
import { QuotationScopeTabs } from '../[documentId]/components/QuotationScopeTabs';
import { useQuotationEditSession } from '../[documentId]/components/useQuotationEditSession';
import {
  QuotationDocumentHeader,
  useQuotationHeaderDetails,
} from '../[documentId]/components/QuotationDocumentHeader';
import {
  QuotationCoverLetterPanel,
  QuotationTermsPanel,
} from '../[documentId]/components/QuotationLetterPanels';
import type { QuoteTermsPatch } from '../../../_shared/components/QuoteTermsFields';

/**
 * One scope as the form holds it until Save: its name, series and notes. Its LINES are not held
 * here. They live in the same staged edit session the quotation page used on origin/main
 * (`useQuotationEditSession`), keyed by `key`, and are edited by the same editor
 * (`QuotationVersionEditor`), so the Lines tab is the quotation page's lines editing moved under
 * the form (#1341, round 3: "we shouldn't revamp the Lines tab, it was good, we should reuse that").
 */
type FormScope = {
  key: string;
  /** The saved scope's id, or null for one added on this form. */
  id: string | null;
  scope_label: string;
  series_id: string;
  /** Undefined until the Edit scope dialog sets it, so an untouched saved note is not sent. */
  notes?: string | null;
  /**
   * PS-QUOTE-MATRIX: a NEW scope's column headers, set in its table header like a saved one's and
   * sent with its lines on Save. A saved scope's columns are its version's, written at once.
   */
  matrix_columns?: MatrixHeader[];
};

type FormTab = 'header' | 'cover-letter' | 'terms';

/**
 * The form's tabs, the read page's minus Signatures (#1341, owner: "header stays in header tab").
 * Same order, same labels, same icons, so view and edit read as one layout. No Lines tab
 * (PROPOSAL-HEADER-LAYOUT, owner hand test 5 Nov 2026: "the Lines also should be align with the
 * view page"): the lines sit on the Header tab under the letterhead, as on the view page.
 */
const FORM_TABS: {
  key: FormTab;
  title: string;
  icon: React.ComponentType<{ className?: string }>;
}[] = [
  { key: 'header', title: 'Header', icon: FileText },
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
  'recipient_fax_snapshot',
  'recipient_email_snapshot',
  'payment_terms',
  'validity',
] as const;

let scopeCounter = 0;
function newScope(): FormScope {
  scopeCounter += 1;
  return {
    key: `new-scope:${scopeCounter}`,
    id: null,
    scope_label: '',
    series_id: '',
  };
}

/**
 * A scope added on this form and never touched: no name, no line. Header-only is a real save
 * (owner on Q3: "yes can, header only is fine"), so this one is left out rather than refused.
 * Its series does not count: a new scope starts on the only active series by itself, and the
 * Edit scope dialog, the one place a series is picked, always writes a name with it.
 */
function isUntouchedNewScope(scope: FormScope, lines: StagedQuotationLine[]): boolean {
  return (
    !scope.id &&
    !scope.scope_label.trim() &&
    lines.length === 0 &&
    !(scope.matrix_columns?.length ?? 0)
  );
}

/** Staged lines whose quantity or unit price is typed but is not a number: the server would 422. */
function badNumberLines(lines: StagedQuotationLine[]): number {
  return lines.filter(
    (line) =>
      !line.removed &&
      [line.draft.quantity, line.draft.unit_price].some(
        (value) => (value ?? '').trim() !== '' && !isDecimalString((value ?? '').trim()),
      ),
  ).length;
}

/** What the strip calls a scope that has no name yet. */
function scopeTitle(scope: FormScope, index: number): string {
  return scope.scope_label.trim() || `Scope ${index + 1}`;
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

/** The page title: "New proposal", or the document's number (PS-PROPOSAL-QUOTATION). */
export function formTitle({
  isEdit,
  documentNo,
  kind,
}: {
  isEdit: boolean;
  documentNo?: string | null;
  kind?: string | null;
}): string {
  if (!isEdit) return 'New proposal';
  return documentNo ?? `Edit ${kind === 'quotation' ? 'quotation' : 'proposal'}`;
}

/** The Save button: "Save proposal" / "Save quotation". */
export function saveLabel(kind?: string | null): string {
  return kind === 'quotation' ? 'Save quotation' : 'Save proposal';
}

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
  const soleSeriesId = soleActiveSeriesId(useProjectSeries().data);
  /** New scopes already given the only active series: once each, so clearing it sticks. */
  const seriesDefaulted = React.useRef(new Set<string>());
  React.useEffect(() => {
    if (!soleSeriesId || !scopes) return;
    const keys = new Set(
      scopes
        .filter((scope) => !scope.id && !scope.series_id && !seriesDefaulted.current.has(scope.key))
        .map((scope) => scope.key),
    );
    if (keys.size === 0) return;
    keys.forEach((key) => seriesDefaulted.current.add(key));
    setScopes((previous) =>
      (previous ?? []).map((scope) =>
        keys.has(scope.key) && !scope.series_id ? { ...scope, series_id: soleSeriesId } : scope,
      ),
    );
  }, [scopes, soleSeriesId]);
  /** The staged lines of every scope opened on this form: the quotation page's own session. */
  const edit = useQuotationEditSession();
  const [activeKey, setActiveKey] = React.useState<string | null>(null);
  const [addingScope, setAddingScope] = React.useState(false);
  const [editingScopeKey, setEditingScopeKey] = React.useState<string | null>(null);
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
  // A grid column removal counting down, or a column write on its way (PS-QUOTE-MATRIX): Save
  // waits, because lines sent across a column write 422 on cells under a removed key.
  const [columnsBusy, setColumnsBusy] = React.useState(false);
  // Open customer feedback, marked on the lines being edited (PS-QUOTE-MATRIX R20, E6): the
  // salesperson acts on a note in this form, so it has to show here, not only on the read.
  const feedbackQuery = useQuotationFeedback(projectId, documentId);
  const openFeedback = React.useMemo(
    () =>
      (feedbackQuery.data?.requests ?? []).flatMap((request) =>
        request.rows.filter((row) => !row.handled_at),
      ),
    [feedbackQuery.data],
  );
  /** Anything typed since the page opened. Drives the warning on leaving the site. */
  const [dirty, setDirty] = React.useState(false);
  /**
   * QUOTE-TERMS-SELECT: the picked term and validity, and what changed since the page opened.
   * Only the changes are sent, so a legacy free text nobody picked over keeps printing.
   */
  const [termsPicks, setTermsPicks] = React.useState<QuoteTermsPatch>({});
  const [termsPatch, setTermsPatch] = React.useState<QuoteTermsPatch>({});
  /** False while the Validity on screen cannot be saved; Save refuses, so what is shown is
   *  always what is sent (crew pass 538d14b7). */
  const [validityOk, setValidityOk] = React.useState(true);

  // Everything on this page lives only in the browser until Save, so a refresh or a closed tab
  // would lose it silently. Warn while there is something to lose.
  const isDirty = dirty || edit.changedScopes.length > 0;
  React.useEffect(() => {
    if (!isDirty || isSaving) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = '';
    };
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [isDirty, isSaving]);

  // The starting point, taken ONCE: a refetch landing mid-edit must not overwrite what somebody
  // is typing.
  React.useEffect(() => {
    if (header !== null) return;
    if (!isEdit && project.data) {
      // Name, Phone and Attn come from the project's customer master data (owner, 13 Oct);
      // with no customer known yet the letter still goes to the developer.
      setHeader({
        your_ref: '',
        doc_date: todayIso(),
        attn_name: project.data.customer_attn ?? '',
        subject_title: project.data.title ?? '',
        recipient_name_snapshot:
          project.data.customer_name ?? project.data.developer_name ?? '',
        recipient_address_snapshot: '',
        recipient_phone_snapshot: project.data.customer_phone ?? '',
        recipient_email_snapshot: project.data.customer_email ?? '',
        payment_terms: '',
        validity: '',
      });
      setScopes([newScope()]);
    }
    if (isEdit && saved.data && quotations.data) {
      const document = saved.data;
      setTermsPicks({
        payment_term_id: document.payment_term_id ?? null,
        validity_value: document.validity_value ?? null,
        validity_unit: document.validity_unit ?? null,
      });
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
      cover_closing_html: letterTemplates.data?.cover_closing_html ?? '',
      terms_html: letterTemplates.data?.terms_html ?? '',
    });
    setLetterSeeded(true);
  }, [isEdit, letterSeeded, letterTemplates.isFetched, letterTemplates.data]);

  // Create: Payment Terms and Validity start from the active terms template, once, as soon as both
  // the header and the templates are ready (either can arrive first).
  const [termsDefaulted, setTermsDefaulted] = React.useState(false);
  React.useEffect(() => {
    if (isEdit || termsDefaulted || !letterSeeded || header === null) return;
    setHeader((previous) => ({
      ...(previous ?? {}),
      payment_terms: letterTemplates.data?.payment_terms ?? '',
      validity: letterTemplates.data?.validity ?? '',
    }));
    // The template's picks ride with the create, so the new quotation keeps them.
    const defaults: QuoteTermsPatch = {};
    if (letterTemplates.data?.payment_term_id)
      defaults.payment_term_id = letterTemplates.data.payment_term_id;
    if (letterTemplates.data?.validity_value != null && letterTemplates.data?.validity_unit) {
      defaults.validity_value = letterTemplates.data.validity_value;
      defaults.validity_unit = letterTemplates.data.validity_unit;
    }
    setTermsPicks(defaults);
    setTermsPatch(defaults);
    setTermsDefaulted(true);
  }, [isEdit, termsDefaulted, letterSeeded, header, letterTemplates.data]);

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

  /** The lines staged for a scope, or none while it has not been opened on the Lines tab. */
  const stagedScopes = edit.scopes;
  const stagedLinesOf = React.useCallback(
    (key: string): StagedQuotationLine[] => stagedScopes[key]?.lines ?? [],
    [stagedScopes],
  );

  /**
   * Each scope's figure: its staged lines once opened, the server's own total until then. The
   * same rule the quotation page's header used for its live total.
   */
  const scopeTotal = React.useCallback(
    (scope: FormScope): string =>
      (stagedScopes[scope.key] ? stagedScopeTotal(stagedScopes[scope.key].lines) : null) ??
      savedScopes?.find((row) => row.id === scope.id)?.scope_total ??
      '0',
    [savedScopes, stagedScopes],
  );

  // Both sections open on arrival; folding is per visit, not remembered.
  const [headerOpen, setHeaderOpen] = React.useState(true);
  const [linesOpen, setLinesOpen] = React.useState(true);

  const liveTotal = React.useMemo(
    () => sumMoney((scopes ?? []).map(scopeTotal)),
    [scopeTotal, scopes],
  );

  const backPath = isEdit
    ? `/project-sales/${projectId}/quotation-documents/${documentId}`
    : `/project-sales/${projectId}?tab=quotations`;
  const title = formTitle({
    isEdit,
    documentNo: saved.data?.document_no,
    kind: saved.data?.kind,
  });
  const letterReady = isEdit || letterSeeded;

  // What the Cover letter tab previews: the header and text as typed, saved or not. A saved
  // quotation also names itself, so the server fills in what is not typed (its number).
  const coverPreviewBody = React.useMemo<QuotationCoverPreviewBody>(() => {
    const h = header ?? {};
    return {
      ...(documentId ? { document_id: documentId } : {}),
      doc_date: h.doc_date || null,
      attn_name: h.attn_name ?? null,
      subject_title: h.subject_title ?? null,
      recipient_name_snapshot: h.recipient_name_snapshot ?? null,
      recipient_address_snapshot: h.recipient_address_snapshot ?? null,
      recipient_phone_snapshot: h.recipient_phone_snapshot ?? null,
      recipient_fax_snapshot: h.recipient_fax_snapshot ?? null,
      recipient_email_snapshot: h.recipient_email_snapshot ?? null,
      payment_terms: h.payment_terms ?? null,
      validity: h.validity ?? null,
      ...termsPatch,
      terms_html: letter.terms_html ?? saved.data?.terms_html ?? null,
      cover_letter_html: letter.cover_letter_html ?? saved.data?.cover_letter_html ?? null,
      cover_closing_html: letter.cover_closing_html ?? saved.data?.cover_closing_html ?? null,
    };
  }, [documentId, header, letter, saved.data, termsPatch]);
  const coverPreview = useQuotationCoverPreview(
    projectId,
    coverPreviewBody,
    tab === 'cover-letter' && letterReady && header !== null,
  );

  /** The scopes Save sends: an untouched new scope is not one (header-only save). */
  function scopesToSave(): FormScope[] {
    return (scopes ?? []).filter(
      (scope) => !isUntouchedNewScope(scope, stagedLinesOf(scope.key)),
    );
  }

  function validate(): string | null {
    const list = scopesToSave();
    if (list.some((scope) => !scope.scope_label.trim())) {
      return 'Every scope needs a name, e.g. Townhouse or Guard House.';
    }
    const unfinished = list.reduce(
      (total, scope) => total + unfinishedStagedLines(stagedLinesOf(scope.key)),
      0,
    );
    if (unfinished > 0) {
      return unfinished === 1
        ? 'One line still needs a catalogue product or set.'
        : `${unfinished} lines still need a catalogue product or set.`;
    }
    // Caught here rather than as a 422 toast: the field already says "Must be a number".
    const badNumbers = list.reduce(
      (total, scope) => total + badNumberLines(stagedLinesOf(scope.key)),
      0,
    );
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
    const changed = new Set(edit.changedScopes.map((scope) => scope.scopeId));
    return scopesToSave().map((scope) => {
      const item: QuotationFormScopeBody = {
        scope_label: scope.scope_label.trim(),
        series_id: scope.series_id || null,
      };
      if (scope.id) item.id = scope.id;
      if (scope.notes !== undefined) item.notes = scope.notes;
      // A new scope carries whatever was staged under it. A saved one carries its lines only when
      // they moved, the rule the quotation page's Save kept: the write replaces the WHOLE set, and
      // a scope the customer holds is never staged, so it is never sent.
      if (!scope.id) item.lines = stagedLinesToBody(stagedLinesOf(scope.key));
      // A new scope's column headers ride with its lines; the server sets them first.
      if (!scope.id && scope.matrix_columns?.length) item.matrix_columns = scope.matrix_columns;
      else if (changed.has(scope.key)) item.lines = stagedLinesToBody(stagedLinesOf(scope.key));
      return item;
    });
  }

  /** Create: the letter tabs' text, when there is any. Empty lets the server render the template. */
  function createLetterBody(): QuotationDocumentBody {
    const body: QuotationDocumentBody = {};
    if ((letter.cover_letter_html ?? '').trim()) body.cover_letter_html = letter.cover_letter_html;
    if ((letter.cover_closing_html ?? '').trim()) body.cover_closing_html = letter.cover_closing_html;
    if ((letter.terms_html ?? '').trim()) body.terms_html = letter.terms_html;
    return body;
  }

  async function save() {
    if (!validityOk) {
      setError('Validity needs a whole number from 1 to 999 and a unit.');
      setTab('terms');
      return;
    }
    const problem = validate();
    setError(problem);
    // Every refusal is about a scope or a line, so show the tab it is on.
    if (problem) {
      setTab('header');
      return;
    }
    setIsSaving(true);
    try {
      if (isEdit && documentId) {
        await mutations.update.mutateAsync({
          id: documentId,
          body: {
            ...headerBody(),
            ...termsPatch,
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
          ...termsPatch,
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

  /**
   * The version for the record card: the highest current version across the kept areas. No
   * Recheck alerts here (owner hand test, 5 Nov 2026): it lives in the view page's gear.
   */
  const keptQuotations = React.useMemo(
    () => (quotations.data ?? []).filter((row) => keptScopes.some((scope) => scope.id === row.id)),
    [quotations.data, keptScopes],
  );
  const keptVersions = useProjectQuotationVersions(keptQuotations);
  const currentVersionNo = keptVersions.rows.reduce<number | null>(
    (max, row) =>
      row.version.is_current ? Math.max(max ?? 0, row.version.version_no) : max,
    null,
  );

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
        crumbs={projectCrumbs(projectId, { tab: 'quotations' }, { title })}
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
              disabled={isSaving || columnsBusy || loading || failed || !letterReady}
              onClick={() => void save()}
            >
              {isSaving ? 'Saving...' : saveLabel(saved.data?.kind)}
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

      {/* The view page's record card (PROPOSAL-HEADER-LAYOUT): number, status and version, the
          title under them. A new proposal has none of these yet. */}
      {isEdit && saved.data && !failed && (
        <RecordHeaderCard
          title={saved.data.document_no}
          badges={
            <>
              <span
                className={`${STATUS_PILL_BASE} ${statusPillClass(quotationStanding(saved.data).label)}`}
              >
                {quotationStanding(saved.data).label}
              </span>
              {currentVersionNo !== null && (
                <span className="inline-flex h-6 items-center rounded-md border border-border px-2 text-xs font-medium">
                  {`v${currentVersionNo}`}
                </span>
              )}
            </>
          }
          subtitle={header?.subject_title ?? saved.data.subject_title}
        />
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

          {/* Every panel stays mounted and is only hidden: the letter editors and the staged
              lines survive a tab switch, and Save can wait on them from any tab. */}
          <FormPanel open={tab === 'header'} label="Header">
            {/* Header and Lines each fold (PROPOSAL-FORM-COLLAPSE, owner 10 Nov), open on
                arrival; folded, they stay mounted so nothing typed is lost. The letterhead is
                its own card, so the section drops its padding and that card's frame. */}
            <FormSection
              title="Header"
              summary={headerSummary(shownDocument, liveTotal)}
              open={headerOpen}
              onOpenChange={setHeaderOpen}
              keepMounted
              bodyClassName="p-0 *:rounded-none *:border-0 *:shadow-none"
            >
              <QuotationDocumentHeader
                document={shownDocument}
                liveGrandTotal={liveTotal}
                details={details}
                preparedBy={project.data?.owner_name ?? null}
                onChange={(patch) => {
                  setDirty(true);
                  setHeader((previous) => ({ ...(previous ?? {}), ...patch }));
                }}
              />
            </FormSection>

            {/* The lines, under the letterhead on the same tab, as on the view page. */}
            {project.data && (
              <FormSection
                title="Lines"
                summary={linesSummary((scopes ?? []).length, liveTotal)}
                open={linesOpen}
                onOpenChange={setLinesOpen}
                keepMounted
                className="mt-5"
              >
              <FormLines
                project={project.data}
                scopes={scopes ?? []}
                savedScopes={savedScopes ?? []}
                quotations={quotations.data ?? []}
                activeKey={activeKey}
                onSelect={setActiveKey}
                scopeTotal={scopeTotal}
                edit={edit}
                onColumns={(key, next) => updateScope(key, { matrix_columns: next })}
                onColumnsBusy={setColumnsBusy}
                feedback={openFeedback}
                canRemoveSaved={canRemoveSaved}
                onAddScope={() => setAddingScope(true)}
                onEditScope={setEditingScopeKey}
                onRemove={(scope) => {
                  setDirty(true);
                  if (scope.id) {
                    const savedId = scope.id;
                    setRemovedIds((previous) => [...previous, savedId]);
                  }
                  setScopes((previous) =>
                    (previous ?? []).filter((row) => row.key !== scope.key),
                  );
                  setActiveKey(null);
                }}
              />
              </FormSection>
            )}

            {/* The quotation page's own Add a scope dialog. It names the scope, which is staged
                and created by Save, not at once. */}
            <QuotationNameDialog
              open={addingScope}
              onOpenChange={setAddingScope}
              initialLabel={null}
              addTitle="Add a scope"
              renameTitle="Rename scope"
              fieldLabel="Scope name"
              placeholder="e.g. Townhouse, Guard house"
              hint="A part of the development priced on its own."
              onSave={(label) => {
                const scope = { ...newScope(), scope_label: label };
                setDirty(true);
                setScopes((previous) => [...(previous ?? []), scope]);
                setActiveKey(scope.key);
                setAddingScope(false);
              }}
            />

            {/* The quotation page's own Edit scope dialog: name, series and notes, staged. */}
            {editingScopeKey && project.data && (() => {
              const scope = (scopes ?? []).find((row) => row.key === editingScopeKey);
              if (!scope) return null;
              const savedRow = (quotations.data ?? []).find((row) => row.id === scope.id);
              return (
                <QuotationDialog
                  project={project.data}
                  quotation={
                    {
                      ...(savedRow ?? {}),
                      id: scope.id ?? '',
                      // The name the tab shows, so an unnamed scope opens as "Scope 2", not blank.
                      scope_label: scopeTitle(scope, (scopes ?? []).indexOf(scope)),
                      series_id: scope.series_id || null,
                      notes: scope.notes !== undefined ? scope.notes : (savedRow?.notes ?? null),
                    } as ProjectQuotation
                  }
                  onSubmit={(body) =>
                    updateScope(scope.key, {
                      scope_label: body.scope_label,
                      series_id: body.series_id ?? '',
                      notes: body.notes,
                    })
                  }
                  // A new scope this form already defaulted: an empty series was cleared on purpose.
                  preselectSoleSeries={!seriesDefaulted.current.has(scope.key)}
                  onDone={() => setEditingScopeKey(null)}
                />
              );
            })()}
          </FormPanel>

          <FormPanel open={tab === 'cover-letter'} label="Cover letter">
            {letterReady ? (
              <QuotationCoverLetterPanel
                cover={coverPreview.data}
                isLoading={coverPreview.isLoading}
                noun={documentNoun(saved.data)}
                error={coverPreview.error?.message}
                html={letter.cover_letter_html ?? saved.data?.cover_letter_html ?? ''}
                closingHtml={letter.cover_closing_html ?? saved.data?.cover_closing_html ?? ''}
                onChange={(html) => {
                  setDirty(true);
                  setLetter((previous) => ({ ...previous, cover_letter_html: html }));
                }}
                onClosingChange={(html) => {
                  setDirty(true);
                  setLetter((previous) => ({ ...previous, cover_closing_html: html }));
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
                paymentTerms={header?.payment_terms ?? ''}
                validity={header?.validity ?? ''}
                paymentTermId={termsPicks.payment_term_id ?? null}
                validityValue={termsPicks.validity_value ?? null}
                validityUnit={termsPicks.validity_unit ?? null}
                projectId={projectId}
                onValidityChange={setValidityOk}
                onFieldChange={(patch) => {
                  setDirty(true);
                  const { payment_terms, validity, ...picks } = patch;
                  setHeader((previous) => ({
                    ...(previous ?? {}),
                    ...('payment_terms' in patch ? { payment_terms: payment_terms ?? '' } : {}),
                    ...('validity' in patch ? { validity: validity ?? '' } : {}),
                  }));
                  setTermsPicks((previous) => ({ ...previous, ...picks }));
                  setTermsPatch((previous) => ({ ...previous, ...picks }));
                }}
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

/** The folded Header's one line: To, Subject, Date, Total; blanks are left out. */
function headerSummary(document: QuotationDocument, total: string | null): string {
  return [
    document.recipient_name_snapshot,
    document.subject_title,
    document.doc_date ? formatDateInMalaysia(document.doc_date) : null,
    formatMyrExact(total),
  ]
    .filter(Boolean)
    .join(' · ');
}

/** The folded Lines' one line: how many scopes, and their total. */
function linesSummary(count: number, total: string | null): string {
  return `${count} ${count === 1 ? 'scope' : 'scopes'} · ${formatMyrExact(total)}`;
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
    cover_closing_html: null,
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

/**
 * The Lines tab of the form: the quotation page's Lines tab from origin/main, moved here (#1341,
 * round 3). The same scope strip (`QuotationScopeTabs`, with Add a scope at its end; its tabs carry
 * Rename and Remove scope, there is no scope card), and under it the same `QuotationVersionEditor`
 * in its staged edit mode, bound to the same `useQuotationEditSession` handlers the quotation
 * page's Edit used. Only one scope's editor is mounted at a time, exactly as there; the staged
 * lines live in the session, so switching scope or tab loses nothing.
 */
function FormLines({
  project,
  scopes,
  savedScopes,
  quotations,
  activeKey,
  onSelect,
  scopeTotal,
  edit,
  onColumns,
  onColumnsBusy,
  feedback,
  canRemoveSaved,
  onAddScope,
  onEditScope,
  onRemove,
}: {
  project: Project;
  scopes: FormScope[];
  savedScopes: QuotationScope[];
  quotations: ProjectQuotation[];
  activeKey: string | null;
  onSelect: (key: string) => void;
  scopeTotal: (scope: FormScope) => string;
  edit: ReturnType<typeof useQuotationEditSession>;
  /** A new scope's column headers, held here until Save (PS-QUOTE-MATRIX). */
  onColumns: (key: string, next: MatrixHeader[]) => void;
  onColumnsBusy: (busy: boolean) => void;
  /** Open customer feedback on this document: marked on the draft being edited (R20). */
  feedback: QuotationFeedbackRow[];
  canRemoveSaved: boolean;
  onAddScope: () => void;
  onEditScope: (key: string) => void;
  onRemove: (scope: FormScope) => void;
}) {
  const active = scopes.find((scope) => scope.key === activeKey) ?? scopes[0] ?? null;
  const savedRow = active?.id ? (quotations.find((row) => row.id === active.id) ?? null) : null;

  // Whether any version of the open scope was sent: such a scope cannot be removed (#1341, owner
  // on Q2: "yes can", while nothing in it has been issued). The same cached query its editor uses.
  const versions = useQuotationVersions(active?.id ?? undefined);
  const issued = (versions.data ?? []).some((version) => Boolean(version.is_issued));
  const canRemove =
    active !== null &&
    (!active.id || (canRemoveSaved && Boolean(versions.data) && !issued));

  /** The open scope's edit handles, bound to its key, exactly as the quotation page bound them. */
  const { scopes: stagedScopes, seedScope, stageScope, toggleRemoved } = edit;
  const activeKeyForEdit = active?.key ?? null;
  const activeColumns = active?.matrix_columns;
  const scopeEditing = React.useMemo<QuotationScopeEditing | null>(() => {
    if (!activeKeyForEdit) return null;
    const key = activeKeyForEdit;
    return {
      staged: stagedScopes[key]?.lines ?? null,
      seed: (versionId, lines) => seedScope(key, versionId, lines),
      stage: (lines) => stageScope(key, lines),
      toggleRemoved: (lineKey) => toggleRemoved(key, lineKey),
      setColumnsBusy: onColumnsBusy,
      // Read by the editor only while the scope has no saved version (the same header controls).
      columns: activeColumns ?? [],
      setColumns: (next) => onColumns(key, next),
    };
  }, [
    activeColumns,
    activeKeyForEdit,
    onColumns,
    onColumnsBusy,
    seedScope,
    stageScope,
    stagedScopes,
    toggleRemoved,
  ]);

  if (!active) {
    return (
      <Card>
        <CardContent className="px-6 py-10 text-center">
          <h3 className="text-sm font-semibold">No scopes on this quotation yet</h3>
          <Button type="button" variant="outline" size="sm" className="mt-4" onClick={onAddScope}>
            <Plus className="size-4" aria-hidden />
            Add a scope
          </Button>
        </CardContent>
      </Card>
    );
  }

  const strip: QuotationScope[] = scopes.map((scope, index) => {
    const saved = savedScopes.find((row) => row.id === scope.id);
    return {
      id: scope.key,
      scope_label: scopeTitle(scope, index),
      sort_order: index,
      current_version_id: saved?.current_version_id ?? null,
      current_version_no: saved?.current_version_no ?? null,
      line_count: saved?.line_count ?? 0,
      scope_total: scopeTotal(scope),
    };
  });

  return (
    <div className="space-y-3">
      {/* The strip alone: no per-area outcome (owner, 5 Nov 2026: outcome is per project). */}
      <div className="flex min-w-0 items-center justify-between gap-3">
        <QuotationScopeTabs
          scopes={strip}
          activeScopeId={active.key}
          onSelect={onSelect}
          canEdit={project.can_edit}
          onAddScope={onAddScope}
          onRename={onEditScope}
          onRemove={(key) => {
            const scope = scopes.find((row) => row.key === key);
            if (scope) onRemove(scope);
          }}
          // The open scope's own rule; another tab becomes the open one on the right-click, so
          // a saved scope is only offered once its versions are known.
          canRemove={(key) =>
            key === active.key ? canRemove : !scopes.find((row) => row.key === key)?.id
          }
        />
      </div>

      {/* No card and no header (QUOTE-SCOPE-COMPACT, owner 4 Nov: "why do I need a section for
          the scope where my scope is already at the top?"). The tab strip IS the scope header:
          its right-click and the open tab's ⋯ carry Rename and Remove scope, and the editor's
          own bordered box is the one container. min-w-0 is load-bearing: without it the line
          table stretches the region and the whole PAGE scrolls sideways at phone width. */}
      <section aria-label={scopeTitle(active, scopes.indexOf(active))} className="min-w-0">
        {active.id && !savedRow ? (
          <Skeleton className="h-64 w-full" />
        ) : (
          <QuotationVersionEditor
            key={active.key}
            project={project}
            quotation={savedRow}
            seriesId={active.series_id || null}
            edit={scopeEditing}
            feedback={feedback}
            // The version is the record card's (PROPOSAL-HEADER-LAYOUT): no version row here, and
            // the form always works on the current version.
            headerVersion={{ versionNo: null }}
            // Copy columns from: the document's other saved scopes, as their versions hold them...
            siblingScopes={scopes
              .filter((scope) => scope.id && scope.id !== active.id)
              .map((scope) => quotations.find((row) => row.id === scope.id))
              .filter((row): row is ProjectQuotation => Boolean(row))}
            // ...and its sections not saved yet (New proposal): their headers as the form
            // holds them. Copying takes headers and columns with fresh keys, never quantities.
            formCopySources={scopes
              .filter((scope) => !scope.id && scope.key !== active.key)
              .map((scope) => ({
                label: scopeTitle(scope, scopes.indexOf(scope)),
                columns: scope.matrix_columns ?? [],
              }))}
          />
        )}
      </section>
    </div>
  );
}
