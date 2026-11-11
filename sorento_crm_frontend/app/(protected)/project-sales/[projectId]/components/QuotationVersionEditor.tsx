'use client';

import * as React from 'react';
import { RefreshCw } from 'lucide-react';
import { useDebouncedSearch } from '@/hooks/useDebouncedSearch';
import { richOneLine, richPlainText } from '@/lib/dealer-kit/rich-text';
import { ListSearchInput } from '@/components/common/ListSearchInput';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import type { SearchableSelectOption } from '@/components/common/SearchableSelect';
import { useUOMSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-uom-select-query';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
// The shared products `/select` mapper, keeping the fields a picked product decides.
import { getProductsForLineSelect } from '@/app/(protected)/master-data-management/products/services/productService';
import { getProductSetsForLineSelect } from '@/app/(protected)/master-data-management/product-sets/services/productSetService';
import {
  SET_OPTION_PREFIX,
  isSetOption,
} from '@/app/(protected)/scm/components/productOrSetPicker';
import type { ProductSetLineRef } from '@/app/(protected)/master-data-management/product-sets/types/productSet.types';
import type { ProductLineRef } from '@/app/(protected)/master-data-management/products/types/product.types';
import {
  useProjectQuotationVersions,
  useQuotationColumnsMutation,
  useQuotationLines,
  useQuotationLinesOf,
  useQuotationRecomputeMutation,
  useQuotationVersions,
  useSeriesPricedRows,
  useSeriesSetRows,
} from '../../_shared/hooks/useProjects';
import type {
  Project,
  ProjectQuotation,
  QuotationFeedbackRow,
  QuotationLine,
  QuotationLineBulkItem,
  QuotationRecomputeResult,
  StagedQuotationLine,
} from '../../_shared/types/project.types';
import { hasColumns, reshapeCells, type MatrixHeader } from '../../_shared/lib/quotationMatrix';
import { carryFeedback } from '../../_shared/lib/quotationFeedbackMarks';
import { ReviseQuotationDialog } from './ReviseQuotationDialog';
import { QuotationLinesGrid, type QuotationLinesMatrix } from './QuotationLinesGrid';
import { useLinesFacts, type LineFacts } from './QuotationLineFlags';
import {
  PICKED_CODE_KEY,
  cellsPatch,
  completeSetText,
  draftCells,
  lineErrors,
  isSectionDraft,
  serverToDraft,
  splitCarriedHeadings,
  toBody,
  totalFromDrafts,
  type LineDraft,
} from './quotationLineDraft';

/**
 * The lines filter's options (PROJECT-QUOTE-LINE-TOOLS), in the pills' own words, each read off
 * the same `lineFacts` the pill on the row shows.
 */
export const LINE_FLAG_FILTERS: { value: string; label: string; test: (facts: LineFacts) => boolean }[] = [
  { value: 'non_standard', label: 'Non-standard', test: (facts) => facts.nonStandard },
  { value: 'below_default', label: 'Below default price', test: (facts) => facts.belowDefault },
  { value: 'below_floor', label: 'Below minimum price', test: (facts) => facts.belowFloor },
];

/** The lines filter's chosen options, held by the page so it stays on across area tabs. */
export type LineFlagFilter = { value: string[]; onChange: (next: string[]) => void };

/** Staged lines that are not ready to be written. Counted so a refusal can say how many. */
export function unfinishedStagedLines(lines: StagedQuotationLine[]): number {
  return lines.filter(
    (line) => !line.removed && Object.keys(lineErrors(line.draft)).length > 0,
  ).length;
}

/**
 * A staged set as the body of the whole-set write.
 *
 * Removed lines are simply left out, which is exactly how the endpoint deletes them, and a line
 * added in this session carries no `id` so the server reads it as new. Order is array position;
 * `sort_order` is not sent at all. Exported because the SAVE lives on the document screen: one
 * button covers every scope, so it cannot live inside one scope's editor.
 */
export function stagedLinesToBody(lines: StagedQuotationLine[]): QuotationLineBulkItem[] {
  return lines
    // A heading row left without a name is not sent (the server would refuse it).
    .filter(
      (line) =>
        !line.removed && !(isSectionDraft(line.draft) && !(line.draft.band_label ?? '').trim()),
    )
    .map((line) =>
      line.id ? { id: line.id, ...toBody(line.draft, line.line) } : toBody(line.draft, line.line),
    );
}

/**
 * What the scope comes to, off the staged drafts, by the same rule the footer and the backend
 * both apply. Exported so the document header can sum the scopes itself rather than being told a
 * figure by whichever editor happens to be mounted.
 */
export function stagedScopeTotal(lines: StagedQuotationLine[]): string | null {
  return totalFromDrafts(lines.filter((line) => !line.removed).map((line) => line.draft));
}

/**
 * What the quotation form page hands down so one scope can be edited without writing anything.
 *
 * Its presence IS edit mode for this scope. Absent, the table is a clean read: no inputs, no
 * per-row saves, nothing to press by accident. That was the client's complaint in one sentence -
 * "every addition of line doesn't trigger a save ... very annoying" - and the answer is a view
 * that is a view, plus Edit quotation, whose form page stages every scope and saves them once
 * (#1341: the same editor, moved under the form's Lines tab).
 */
export type QuotationScopeEditing = {
  /** The scope's staged lines, or null until it has been seeded from the server's rows. */
  staged: StagedQuotationLine[] | null;
  seed: (versionId: string, lines: StagedQuotationLine[]) => void;
  stage: (lines: StagedQuotationLine[]) => void;
  toggleRemoved: (key: string) => void;
  /**
   * PS-QUOTE-MATRIX: true while a column removal counts down or a column write is on its way.
   * The page's Save waits: a line write racing a column write 422s on cells under a removed key.
   */
  setColumnsBusy?: (busy: boolean) => void;
  /**
   * PS-QUOTE-MATRIX: a scope with no saved version yet (added on the form) holds its column
   * headers here, edited through the same header controls, and Save sends them with its lines.
   * Ignored for a saved scope, whose columns are its version's (written at once).
   */
  columns?: MatrixHeader[];
  setColumns?: (next: MatrixHeader[]) => void;
};

/**
 * The versions of one scope, and the lines of whichever version is being looked at.
 *
 * Only the newest version is editable, and the editor works that out from the server's
 * `is_current` rather than from a local guess. Everything below it is history the
 * customer already holds (AC-E3), so an older version renders read-only with the reason
 * stated, not merely with its buttons missing.
 *
 * With no `edit` it is a READ. Every field is text, there is nothing to add and nothing to save,
 * because a screen that saves on blur cannot also be the screen somebody reads a quotation on.
 */
export function QuotationVersionEditor({
  project,
  quotation,
  seriesId,
  edit,
  locked = false,
  feedback,
  siblingScopes,
  formCopySources,
  headerVersion,
  flagFilter,
}: {
  project: Project;
  /**
   * The lines filter's choice, from the page, so it survives an area tab switch (the editor is
   * keyed per scope). Absent, the editor holds it itself.
   */
  flagFilter?: LineFlagFilter;
  /**
   * Set by the quotation page (PROPOSAL-HEADER-LAYOUT): the version is the record header's chip,
   * one number for the whole proposal, and Recheck alerts / Revise are its gear items. So this
   * editor shows no version row of its own, reads the version the chip picked (falling back to
   * the area's current one), and shows the header's last recheck answer for that version.
   */
  headerVersion?: {
    versionNo: number | null;
    /** The header's Recheck alerts answers, by the version id each one ran on. */
    recheckResults?: Record<string, QuotationRecomputeResult>;
    onDismissRecheck?: (versionId: string) => void;
  };
  /**
   * Open customer feedback on this document (PS-QUOTE-MATRIX): marked on the lines it names, and
   * on their copies in a later revision (same product, same occurrence), so a draft shows them.
   */
  feedback?: QuotationFeedbackRow[];
  /** The document's other scopes, offered by Copy columns from while editing. */
  siblingScopes?: ProjectQuotation[];
  /**
   * The form's other sections not saved yet, with the headers they hold (round 4): offered by
   * Copy columns from too, so on New proposal a second section can copy the first.
   */
  formCopySources?: { label: string; columns: MatrixHeader[] }[];
  /** The quotation is locked for approval: no per-scope revise is offered. */
  locked?: boolean;
  /**
   * The scope. Null on the form page for a scope added there and not saved yet (#1341): it has no
   * version, so there is nothing to read, and its lines start empty and are staged like any other.
   */
  quotation: ProjectQuotation | null;
  /** The series the form has staged for this scope, over the saved one. */
  seriesId?: string | null;
  /** Set by the form page, which holds the staged lines. See `QuotationScopeEditing`. */
  edit?: QuotationScopeEditing | null;
}) {
  const isUnsaved = quotation === null;
  const versions = useQuotationVersions(quotation?.id);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [revising, setRevising] = React.useState(false);
  const recompute = useQuotationRecomputeMutation(project.id);
  const [recomputed, setRecomputed] = React.useState<QuotationRecomputeResult | null>(null);
  const {
    value: lineSearchInput,
    setValue: setLineSearchInput,
    debouncedValue: lineSearch,
  } = useDebouncedSearch();

  const rows = React.useMemo(
    () => [...(versions.data ?? [])].sort((a, b) => b.version_no - a.version_no),
    [versions.data],
  );
  const current = rows.find((version) => version.is_current) ?? null;
  const selected =
    (headerVersion
      ? rows.find((version) => version.version_no === headerVersion.versionNo)
      : rows.find((version) => version.id === selectedId)) ?? current;
  // The version's column headers (PS-QUOTE-MATRIX); `[]` is today's single Qty column. A scope
  // added on the form has no version yet: its headers are the form's, until Save.
  const formColumns = isUnsaved ? edit?.columns : undefined;
  /**
   * A saved scope's header as edited here, ahead of the server: the source of truth until every
   * column write has answered (round 4). An answer never overwrites a change made after its
   * request went out; when the queue drains the server's columns take over again.
   */
  const [localColumns, setLocalColumns] = React.useState<MatrixHeader[] | null>(null);
  const matrixColumns = React.useMemo<MatrixHeader[]>(
    () => (isUnsaved ? (formColumns ?? []) : (localColumns ?? selected?.matrix_columns ?? [])),
    [formColumns, isUnsaved, localColumns, selected?.matrix_columns],
  );
  const withCells = hasColumns(matrixColumns);

  const lines = useQuotationLines(selected?.id);

  // `is_editable` from the server, NOT `is_current`. An issued version is still the highest
  // version until somebody revises, so gating on `is_current` left the fields open on a
  // quotation the customer already holds: the user typed a price, the server refused with 422,
  // and the number stayed on screen looking saved.
  // A scope added on the form has no version yet, and is editable by the one who is adding it.
  const editable =
    (isUnsaved || Boolean(selected?.is_editable ?? selected?.is_current)) && project.can_edit;
  const sortedLines = React.useMemo(
    () => [...(lines.data ?? [])].sort((a, b) => a.sort_order - b.sort_order),
    [lines.data],
  );

  // The line stores the CODE, not the id, so the option value is the code. Cached with an
  // infinite staleTime by the shared hook, so opening five versions costs one request.
  const uoms = useUOMSelectQuery();
  const uomOptions = React.useMemo(
    () =>
      (uoms.data ?? []).map((unit) => ({
        value: unit.uom_code,
        label: unit.uom_code,
        description: unit.uom_name,
      })),
    [uoms.data],
  );
  // The line snapshots the brand as TEXT (what was quoted, not who owns the SKU today), so the
  // product's brand_id has to be resolved to a name before it can go on a row. Same cached
  // master-data hook the rest of the app uses; no UUID reaches the cell.
  const brands = useBrandSelectQuery();
  // The brands master, offered by NAME: the line stores the name it was quoted under.
  const brandOptions = React.useMemo<SearchableSelectOption[]>(
    () => (brands.data ?? []).map((row) => ({ value: row.brand_name, label: row.brand_name })),
    [brands.data],
  );

  /**
   * The products the picker has shown, by id.
   *
   * The dropdown already holds the whole record when somebody chooses one, so the fill reads it
   * from here instead of asking the server again for a row it just rendered.
   */
  const productsById = React.useRef(new Map<string, ProductLineRef>());

  /** The sets the picker has shown, by id: a never-saved set line is named after one. */
  const setsById = React.useRef(new Map<string, ProductSetLineRef>());

  const fetchProducts = React.useCallback(async (query: string) => {
    const products = await getProductsForLineSelect(query || undefined);
    products.forEach((product) => productsById.current.set(product.id, product));
    // Sets and products in ONE list, sets first (a set code is almost never also a product
    // code). Best-effort: a reader without the product-set permission still gets the products.
    let setOptions: SearchableSelectOption[] = [];
    try {
      const sets = await getProductSetsForLineSelect({ query: query || undefined });
      setOptions = sets.map((set) => {
        setsById.current.set(set.id, set);
        return {
          value: `${SET_OPTION_PREFIX}${set.id}`,
          label: set.set_code,
          searchText: `${set.set_code} ${set.name}`,
        };
      });
    } catch {
      setOptions = [];
    }
    return [
      ...setOptions,
      ...products.map((product) => ({
        value: product.id,
        label: product.product_code,
        description: product.product_name,
      })),
    ];
  }, []);

  /**
   * What picking a product decides for the rest of its line.
   *
   * Every one of these fields is the product's, so a line quoting SRT-WC-01 reads the same
   * whoever typed it. The shared table applies this AS STATED, over hand-typed text included
   * (the client's call: one product, one set of fields, every time), so this returns a key even
   * when the product has nothing for it - that is how the previous product's wording is cleared.
   *
   * `list_price` has no column: it is the annotation under the unit price, and it must follow
   * the product from the moment it is picked rather than waiting for the save to come back.
   *
   * NOT filled, both deliberately:
   * - `technical_spec`. The client asked for it, and the products table has no such column -
   *   only the quotation line does. Nothing to copy, so the cell is left for the salesperson
   *   rather than filled with a guess, and returning it blank would wipe what they wrote.
   * - `unit_price`. It is the QUOTED price, not the product's, and under an always-overwrite
   *   fill a re-pick would throw away a negotiated figure. The list price is shown beside it
   *   so the discount is visible; the number that gets charged stays a decision.
   */
  /**
   * What THIS scope's series sells each product for (T5, AC-C1).
   *
   * Only fetched when the scope is actually quoted from a series; most are not, and an
   * unconditional request would be a round trip for an answer of "nothing".
   */
  const seriesRows = useSeriesPricedRows(
    (seriesId !== undefined ? seriesId : quotation?.series_id) ?? undefined,
  );
  const seriesPriceByProduct = React.useMemo(() => {
    const map = new Map<string, string>();
    (seriesRows.data ?? []).forEach((row) => {
      if (row.selling_price) map.set(row.product_id, row.selling_price);
    });
    return map;
  }, [seriesRows.data]);

  const setRows = useSeriesSetRows(
    (seriesId !== undefined ? seriesId : quotation?.series_id) ?? undefined,
  );
  const seriesPriceBySet = React.useMemo(() => {
    const map = new Map<string, string>();
    (setRows.data ?? []).forEach((row) => {
      if (row.selling_price) map.set(row.product_set_id, row.selling_price);
    });
    return map;
  }, [setRows.data]);

  /**
   * What picking a SET decides for the rest of its line: the set name as the description, UOM
   * SET, the set's resolved list price, the parts as the Complete set text, and the series' price for the
   * set where it names one. The parts themselves are not shown on the line; the server freezes them when the line is saved.
   */
  const fillFromSet = React.useCallback(
    async (setId: string): Promise<LineDraft> => {
      const [set] = await getProductSetsForLineSelect({ ids: [setId] });
      if (!set) return {};
      const filled: LineDraft = {
        description: set.name,
        uom: 'SET',
        list_price: set.list_price != null ? String(set.list_price) : '',
        complete_set: completeSetText(set.parts),
      };
      // The grid applies the brand only to a line whose brand is blank.
      if (set.brand_name) filled.brand_snapshot = set.brand_name;
      const agreed = seriesPriceBySet.get(setId);
      if (agreed) filled.unit_price = agreed;
      return filled;
    },
    [seriesPriceBySet],
  );

  const fillFromProduct = React.useCallback(
    (option: { value: string }): LineDraft => {
      const product = productsById.current.get(option.value);
      if (!product) return {};
      const brand = (brands.data ?? []).find((row) => row.id === product.brand_id);
      const unit = (uoms.data ?? []).find((row) => row.id === product.base_uom_id);
      const filled: LineDraft = {
        // The rule the backend snapshots by, so what shows now is what gets stored.
        description: product.description || product.product_name || '',
        brand_snapshot: brand?.brand_name ?? '',
        uom: unit?.uom_code ?? '',
        list_price: product.list_price ?? '',
      };
      // The SERIES price, where this scope is quoted from one that names the product
      // (AC-C1). That is the price actually agreed for this scope, so it is the one the
      // line should open at - the salesperson can still type over it, and the below-floor
      // check then judges whatever they typed. Where the series says nothing, `unit_price`
      // is left untouched and the line behaves exactly as it did before (AC-C2).
      const agreed = seriesPriceByProduct.get(option.value);
      if (agreed) filled.unit_price = agreed;
      return filled;
    },
    [brands.data, seriesPriceByProduct, uoms.data],
  );

  /**
   * The product the picker trigger names, read off the DRAFT: nothing refetches during an edit
   * session, so resolving it from the stored line would name the product that was there before
   * the pick, right up until Save. Async mode fetches a page at a time, so a saved row's own
   * product has to be handed in or it would read as empty until somebody searched for it.
   */
  const resolveProduct = React.useCallback(
    (stored: QuotationLine | null, draft: LineDraft): SearchableSelectOption | undefined => {
      const setId = draft.product_set_id;
      if (setId && !draft.product_id) {
        const picked = setsById.current.get(setId);
        const storedSet = stored?.product_set_id === setId;
        return {
          value: `${SET_OPTION_PREFIX}${setId}`,
          label:
            picked?.set_code ??
            (storedSet ? stored?.product_code : null) ??
            (draft[PICKED_CODE_KEY] || 'Selected set'),
          description:
            picked?.name ?? (storedSet ? richOneLine(stored?.description) || undefined : undefined),
        };
      }
      const productId = draft.product_id;
      if (!productId) return undefined;
      const picked = productsById.current.get(productId);
      if (picked) {
        return {
          value: productId,
          label: picked.product_code,
          description: picked.product_name ?? undefined,
        };
      }
      return {
        value: productId,
        // The stored code, else the code carried on the draft since the pick (a line not saved
        // yet, after a section switch rebuilt this editor and its lookup).
        label:
          (stored?.product_id === productId ? stored.product_code : null) ??
          (draft[PICKED_CODE_KEY] || 'Selected product'),
        description:
          stored?.product_id === productId ? richOneLine(stored.description) || undefined : undefined,
      };
    },
    [],
  );

  /** A product picked in this session, by id: what a never-saved line is named after. */
  const productCodeOf = React.useCallback(
    (productId: string) =>
      (isSetOption(productId)
        ? setsById.current.get(productId.slice(SET_OPTION_PREFIX.length))?.set_code
        : productsById.current.get(productId)?.product_code) ?? null,
    [],
  );

  /**
   * Edit mode for THIS scope: the screen asked for it, and the server still allows it.
   *
   * Both halves matter. A frozen version stays a read even inside an open edit session - the
   * customer holds it, and the way to change it is a revision, which the shell offers.
   */
  const isEditing = Boolean(edit) && editable;
  const staged = edit?.staged ?? null;

  /**
   * The scope's starting point, taken from the server's rows the first time it is opened for
   * editing. Seeded through the shell, never held here: this component unmounts on a tab switch
   * and on a scope switch, and the staged work has to survive both.
   */
  const seedScope = edit?.seed;
  React.useEffect(() => {
    if (!seedScope || !isEditing || staged !== null) return;
    // Nothing on the server to start from: an unsaved scope starts with no lines.
    if (isUnsaved) {
      seedScope('', []);
      return;
    }
    // Not while the rows are being fetched: cached rows from before a Save would be seeded once
    // and the fresh ones that land a moment later ignored, so a reopened edit would lose them.
    if (!selected || lines.isLoading || lines.isFetching) return;
    seedScope(
      selected.id,
      // A heading still carried by a line is seeded as its own row (PROPOSAL-FORM-COLLAPSE), so
      // the session's baseline is already split and an untouched scope stays clean.
      splitCarriedHeadings(
        sortedLines.map((line) => ({
          id: line.id,
          key: line.id,
          line,
          draft: serverToDraft(line, withCells),
          removed: false,
        })),
      ),
    );
  }, [
    withCells,
    isEditing,
    isUnsaved,
    lines.isFetching,
    lines.isLoading,
    seedScope,
    selected,
    sortedLines,
    staged,
  ]);

  /**
   * What the grid draws, in display order: the staged set while editing, the server's rows
   * otherwise, in one shape so there is one set of columns rather than two that can drift apart.
   * Until the session has seeded this scope the server's rows show as a read.
   */
  const gridEditing = isEditing && staged !== null;
  const gridLines = React.useMemo<StagedQuotationLine[]>(
    () =>
      gridEditing && staged
        ? staged
        : splitCarriedHeadings(
            sortedLines.map((line) => ({
              id: line.id,
              key: line.id,
              line,
              draft: serverToDraft(line, withCells),
              removed: false,
            })),
          ),
    [gridEditing, sortedLines, staged, withCells],
  );

  /**
   * The header editor (PS-QUOTE-MATRIX R11): only on the editable version, in an edit session.
   * A change is written at once (the server moves quantities in and out); the lines staged in
   * this session are reshaped by the same rule, so unsaved typing survives the change.
   */
  const columnsMutation = useQuotationColumnsMutation(project.id);
  const stagedRef = React.useRef(staged);
  stagedRef.current = staged;
  const stageForColumns = edit?.stage;
  const versionForColumns = selected?.id ?? null;
  // One editor for create and edit (owner, 28 Oct): a scope not saved yet edits its header too,
  // held by the form; a saved one needs its version to be editable.
  const setFormColumns = edit?.setColumns;
  const canEditColumns =
    gridEditing &&
    project.can_edit &&
    (isUnsaved ? Boolean(setFormColumns) : Boolean(selected?.is_editable));
  const siblingVersions = useProjectQuotationVersions(canEditColumns ? siblingScopes : undefined);
  const copySources = React.useMemo(
    () =>
      (canEditColumns ? (siblingScopes ?? []) : []).map((scope) => ({
        label: scope.scope_label,
        columns:
          siblingVersions.rows.find(
            (row) => row.quotation.id === scope.id && row.version.is_current,
          )?.version.matrix_columns ?? [],
      })).concat(canEditColumns ? (formCopySources ?? []) : []),
    [canEditColumns, formCopySources, siblingScopes, siblingVersions.rows],
  );
  /** The staged lines carried across a header change, by the server's own rule (R12). */
  const reshapeStaged = React.useCallback(
    (before: MatrixHeader[], after: MatrixHeader[]) => {
      const held = stagedRef.current;
      if (!held || !stageForColumns) return;
      stageForColumns(
        held.map((line) => {
          const reshaped = reshapeCells(before, after, draftCells(line.draft), line.draft.quantity ?? '');
          return { ...line, draft: { ...line.draft, ...cellsPatch(reshaped.cells, reshaped.quantity) } };
        }),
      );
    },
    [stageForColumns],
  );
  /**
   * Column writes for a saved scope, one in flight at a time (round 4). Each is the WHOLE matrix,
   * so two racing writes let the later ANSWER win: a rename made while "+ Column" was saving went
   * back to "Column 1", on screen and in the database. A change made while a write is out only
   * replaces `queued`; when the write answers, the latest matrix goes out once. A refused write
   * puts the header and the staged lines back as they were before the batch, and toasts (the
   * mutation's own toast).
   */
  const writes = React.useRef<{
    inFlight: boolean;
    queued: MatrixHeader[] | null;
    /** The staged lines and header before the first unanswered change, for a rollback. */
    before: { lines: StagedQuotationLine[] | null; columns: MatrixHeader[] } | null;
  }>({ inFlight: false, queued: null, before: null });
  const [writing, setWriting] = React.useState(false);
  const pump = React.useCallback(async () => {
    const queue = writes.current;
    if (queue.inFlight || !queue.queued || !versionForColumns) return;
    queue.inFlight = true;
    setWriting(true);
    try {
      while (queue.queued) {
        const columns = queue.queued;
        queue.queued = null;
        await columnsMutation.mutateAsync({ versionId: versionForColumns, columns });
      }
      queue.before = null;
      // Drained: the server's columns (set from the last answer) take over.
      setLocalColumns(null);
    } catch {
      const before = queue.before;
      queue.queued = null;
      queue.before = null;
      setLocalColumns(null);
      if (before?.lines && stageForColumns) stageForColumns(before.lines);
    } finally {
      queue.inFlight = false;
      setWriting(false);
    }
  }, [columnsMutation, stageForColumns, versionForColumns]);
  const changeColumns = React.useCallback(
    async (next: MatrixHeader[]): Promise<boolean> => {
      const before = matrixColumns;
      if (isUnsaved) {
        // Nothing to write yet: the form holds the header and sends it with the lines on Save.
        if (!setFormColumns) return false;
        setFormColumns(next);
        reshapeStaged(before, next);
        return true;
      }
      if (!versionForColumns) return false;
      const queue = writes.current;
      if (!queue.before) queue.before = { lines: stagedRef.current, columns: before };
      // Optimistic, like create: the header and the moved quantities are on screen at once.
      setLocalColumns(next);
      reshapeStaged(before, next);
      queue.queued = next;
      void pump();
      return true;
    },
    [isUnsaved, matrixColumns, pump, reshapeStaged, setFormColumns, versionForColumns],
  );
  /**
   * The notes as marks on the version on screen (R20, E6). They name the ISSUED version's lines;
   * when a note's line is not on screen, the other versions' lines are read (cached per version)
   * to carry it to its copy here.
   */
  const scopeNotes = React.useMemo(
    () =>
      (feedback ?? []).filter(
        (note) => !note.scope_id || !quotation || note.scope_id === quotation.id,
      ),
    [feedback, quotation],
  );
  const shownIds = React.useMemo(() => new Set(sortedLines.map((line) => line.id)), [sortedLines]);
  const needsSources = scopeNotes.some((note) => !shownIds.has(note.line_id));
  const sourceVersionIds = React.useMemo(
    () =>
      needsSources
        ? rows.filter((version) => version.id !== selected?.id).map((version) => version.id)
        : [],
    [needsSources, rows, selected?.id],
  );
  const sourceLines = useQuotationLinesOf(sourceVersionIds);
  const gridFeedback = React.useMemo(
    () => carryFeedback(scopeNotes, sourceLines, sortedLines),
    [scopeNotes, sourceLines, sortedLines],
  );

  const [removalPending, setRemovalPending] = React.useState(false);
  const setColumnsBusy = edit?.setColumnsBusy;
  // Save waits only while a removal counts down or a column write is out (normally well under a
  // second): lines sent across a column write would 422 on cells under keys not stored yet. The
  // screen is already right meanwhile (optimistic), so nothing reads blank or 0.
  const columnsBusy = removalPending || writing;
  React.useEffect(() => {
    setColumnsBusy?.(columnsBusy);
  }, [columnsBusy, setColumnsBusy]);
  // Leaving the scope never leaves the page's Save waiting on a grid that is gone.
  React.useEffect(() => () => setColumnsBusy?.(false), [setColumnsBusy]);

  const matrix = React.useMemo<QuotationLinesMatrix>(
    () => ({
      columns: matrixColumns,
      onChange: canEditColumns ? changeColumns : undefined,
      // Never locks the header: changes made while a write is out are queued and merged.
      saving: false,
      copySources,
      onRemovalPending: setRemovalPending,
    }),
    [canEditColumns, changeColumns, copySources, matrixColumns],
  );

  // The flags filter (PROJECT-QUOTE-LINE-TOOLS): the page's choice when it holds one.
  const [ownFlags, setOwnFlags] = React.useState<string[]>([]);
  const chosenFlags = flagFilter?.value ?? ownFlags;
  const setChosenFlags = flagFilter?.onChange ?? setOwnFlags;
  const verdictSeriesId = (seriesId !== undefined ? seriesId : quotation?.series_id) ?? null;
  const facts = useLinesFacts(
    { quotationId: quotation?.id ?? null, seriesId: verdictSeriesId },
    gridLines,
  );
  /**
   * Lines added or edited while the filter is on stay on screen until the filter changes, so a
   * row never vanishes from under the caret: a duplicated copy before its verdict answers, or a
   * rate typed past the flag the filter was set on (owner ruling: alerts live, never lost work).
   * Worked out during render, so the input being typed into is never unmounted.
   */
  const flagsKey = chosenFlags.join(',');
  const touched = React.useRef<{ flags: string; keys: Set<string>; drafts: Map<string, unknown> }>({
    flags: flagsKey,
    keys: new Set(),
    drafts: new Map(),
  });
  if (touched.current.flags !== flagsKey) {
    touched.current = { flags: flagsKey, keys: new Set(), drafts: touched.current.drafts };
  }
  {
    const held = touched.current;
    const known = held.drafts.size > 0;
    gridLines.forEach((line) => {
      const before = held.drafts.get(line.key);
      if (flagsKey && known && before !== line.draft) held.keys.add(line.key);
      held.drafts.set(line.key, line.draft);
    });
  }
  const pinned = touched.current.keys;
  const flagOptions = React.useMemo(
    () =>
      LINE_FLAG_FILTERS.map((option) => {
        const count = gridLines.filter((line) => {
          const fact = facts.get(line.key);
          return !line.removed && fact != null && option.test(fact);
        }).length;
        return { value: option.value, label: option.label, badgeText: String(count) };
      }),
    [facts, gridLines],
  );

  // Matched on the LIVE draft, so a description typed seconds ago is already findable, plus the
  // saved code the draft does not carry as text.
  const needle = lineSearch.trim().toLowerCase();
  const rowFilter = React.useMemo(() => {
    const tests = LINE_FLAG_FILTERS.filter((option) => chosenFlags.includes(option.value));
    if (!needle && tests.length === 0) return undefined;
    return (line: StagedQuotationLine) => {
      if (pinned.has(line.key)) return true;
      const fact = facts.get(line.key);
      const flagged =
        tests.length === 0 || (fact != null && tests.some((option) => option.test(fact)));
      const found =
        !needle ||
        [
          line.line?.product_code,
          richPlainText(line.draft.description),
          line.draft.brand_snapshot,
          line.draft.band_label,
        ].some((value) => (value ?? '').toLowerCase().includes(needle));
      return flagged && found;
    };
    // `pinned` is read through the ref; `gridLines` is what changes it.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chosenFlags, facts, needle, gridLines]);
  const filterEmptyHint = needle
    ? `No line matches "${lineSearch.trim()}".`
    : 'No line matches these flags.';

  const stageLines = edit?.stage;
  const toggleRemoved = edit?.toggleRemoved;

  if (versions.isLoading) return <Skeleton className="h-24 w-full" />;

  // `min-w-0` so a wide line table scrolls in its own gutter instead of stretching the
  // panel it sits in, which at 375px would take the whole page sideways with it.
  return (
    <div className="min-w-0 space-y-3">
      {!headerVersion && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-wrap items-center gap-1.5">
            {rows.map((version) => (
              <button
                key={version.id}
                type="button"
                onClick={() => setSelectedId(version.id)}
                aria-current={selected?.id === version.id}
                className={
                  selected?.id === version.id
                    ? 'rounded-md border border-primary bg-primary/10 px-2.5 py-1 text-xs font-medium'
                    : 'rounded-md border border-border px-2.5 py-1 text-xs text-muted-foreground hover:bg-muted'
                }
              >
                {`v${version.version_no}`}
                {version.is_current ? '' : ' (frozen)'}
              </button>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            {/* Re-ask both alerts against today's master data (S19). On the version that is
                being looked at, and only while it is still open: the flags on a frozen
                version are what was true when the customer was sent the paper.

                Withheld while an edit session is open on this scope. Recompute writes to the
                server, and the staged rows on screen would silently be answering for a state
                the database no longer holds. */}
            {project.can_edit && editable && selected && !locked && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={recompute.isPending || isEditing}
                title={
                  isEditing
                    ? 'Save or cancel your changes first'
                    : 'Re-check every line against the series and price floors as they stand today'
                }
                onClick={async () => {
                  try {
                    setRecomputed(await recompute.mutateAsync(selected.id));
                  } catch {
                    // The mutation already toasted the reason.
                  }
                }}
              >
                <RefreshCw className="size-4" aria-hidden />
                {recompute.isPending ? 'Rechecking...' : 'Recheck alerts'}
              </Button>
            )}

            {/* Not on the form page: a revise writes a new version at once, under lines the form
                has staged against the current one and saves by scope. The quotation page's Edit
                quotation already asks to revise before it opens the form. */}
            {project.can_edit && current && !edit && !locked && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setRevising(true)}
              >
                {`Revise to v${current.version_no + 1}`}
              </Button>
            )}
          </div>
        </div>
      )}

      {recomputed && !headerVersion && (
        <RecomputeSummary result={recomputed} onDismiss={() => setRecomputed(null)} />
      )}
      {headerVersion && selected && headerVersion.recheckResults?.[selected.id] && (
        <RecomputeSummary
          result={headerVersion.recheckResults[selected.id]}
          onDismiss={() => headerVersion.onDismissRecheck?.(selected.id)}
        />
      )}

      {/* No "Issued by / Opened" strip above the table: the owner moved it into the Header tab's
          details ("this one should be in header details", #1341). */}
      {/* No "The customer holds vN. Edit quotation opens vN+1" line (owner, 5 Nov 2026): Edit's
          own prompt says it at the moment it matters (ReviseToEditDialog). */}

      {selected && !selected.is_current && (
        <p className="text-xs text-muted-foreground">
          {`Frozen. Make changes on ${current ? `v${current.version_no}` : 'the current version'}.`}
        </p>
      )}

      {/* Search over the lines. Hides rows rather than removing them, so item numbers hold,
          totals still sum the whole version, and an unsaved draft on a hidden line survives
          the search that hid it. Ctrl-F cannot do this job: it only finds what is scrolled
          into the DOM, so on a 59-line version it answers 0/0 for lines that plainly exist. */}
      {lines.isLoading && !isUnsaved ? (
        <Skeleton className="h-24 w-full" />
      ) : (
        <QuotationLinesGrid
          // A fresh grid when the session opens and again when it closes, so Cancel puts every
          // row back the way the server has it.
          key={gridEditing ? 'editing' : 'reading'}
          lines={gridLines}
          editing={gridEditing}
          quotationId={quotation?.id ?? null}
          seriesId={verdictSeriesId}
          rowFilter={rowFilter}
          emptyHint={
            gridEditing
              ? 'Nothing quoted yet.'
              : editable
                ? 'No lines yet.'
                : 'This version was frozen without any lines.'
          }
          filterEmptyHint={filterEmptyHint}
          fetchProducts={fetchProducts}
          resolveProduct={resolveProduct}
          productCodeOf={productCodeOf}
          toolbar={
            gridLines.length > 0 ? (
              <>
                <ListSearchInput
                  value={lineSearchInput}
                  onChange={setLineSearchInput}
                  placeholder="Search lines"
                  aria-label="Search lines by product or description"
                  className="w-full sm:max-w-xs"
                />
                <SearchableMultiSelect
                  aria-label="Flags"
                  value={chosenFlags}
                  onChange={setChosenFlags}
                  options={flagOptions}
                  placeholder="Flags"
                  clearable
                  triggerClassName="w-full sm:w-48"
                />
              </>
            ) : null
          }
          fillFromProduct={fillFromProduct}
          fillFromSet={fillFromSet}
          uomOptions={uomOptions}
          uomError={uoms.error}
          onUomRetry={() => void uoms.refetch()}
          brandOptions={brandOptions}
          onStage={gridEditing ? stageLines : undefined}
          onToggleRemoved={gridEditing ? toggleRemoved : undefined}
          matrix={matrix}
          feedback={gridFeedback}
        />
      )}

      {revising && current && quotation && (
        <ReviseQuotationDialog
          projectId={project.id}
          scopes={[
            { quotation, currentVersionNo: current.version_no, lineCount: sortedLines.length },
          ]}
          onDone={(newVersionId) => {
            setRevising(false);
            // Land on the version that was just opened, not the one being read a moment ago.
            if (newVersionId) setSelectedId(newVersionId);
          }}
        />
      )}

    </div>
  );
}

/**
 * What a recompute changed, in the words a reader would use (S19).
 *
 * Composed here rather than on the server: the counts are facts, the sentence is copy, and
 * copy belongs on the screen that shows it. "Nothing changed" is a REAL answer and gets its
 * own sentence - a reader has to be able to tell "I checked and it was already right" from
 * "I pressed a button and nothing happened".
 */
export function describeRecompute(result: QuotationRecomputeResult): string {
  const parts: string[] = [];
  if (result.no_longer_non_standard > 0) {
    parts.push(
      `${result.no_longer_non_standard} ${result.no_longer_non_standard === 1 ? 'line is' : 'lines are'} no longer non-standard`,
    );
  }
  if (result.now_non_standard > 0) {
    parts.push(
      `${result.now_non_standard} ${result.now_non_standard === 1 ? 'line is' : 'lines are'} now non-standard`,
    );
  }
  if (result.no_longer_below_floor > 0) {
    parts.push(
      `${result.no_longer_below_floor} ${result.no_longer_below_floor === 1 ? 'line is' : 'lines are'} no longer below minimum price`,
    );
  }
  if (result.now_below_floor > 0) {
    parts.push(
      `${result.now_below_floor} ${result.now_below_floor === 1 ? 'line is' : 'lines are'} now below minimum price`,
    );
  }
  if (result.floor_changed > 0) {
    parts.push(
      `${result.floor_changed} ${result.floor_changed === 1 ? 'line' : 'lines'} picked up a different minimum price`,
    );
  }
  if (parts.length === 0) {
    return `Nothing changed. All ${result.line_count} ${
      result.line_count === 1 ? 'line' : 'lines'
    } already match the series and price floors as they stand today.`;
  }
  return `${parts.join(', ')}.`;
}

/** The report, on the page rather than in a toast that takes it away after four seconds. */
function RecomputeSummary({
  result,
  onDismiss,
}: {
  result: QuotationRecomputeResult;
  onDismiss: () => void;
}) {
  return (
    <div
      role="status"
      className="flex flex-col gap-2 rounded-md border border-border bg-muted/40 px-3 py-2 text-xs sm:flex-row sm:items-start sm:justify-between"
    >
      <div className="min-w-0">
        <p className="font-medium">{describeRecompute(result)}</p>
        {result.changed_lines.length > 0 && (
          <p className="mt-0.5 break-words text-muted-foreground">
            {result.changed_lines.join(', ')}
          </p>
        )}
        {/* Why some lines could not move. Without this the reader gets "nothing changed"
            over a set of lines naming products this company does not stock, which is true
            and tells them nothing about what to do next. */}
        {result.unresolved_products > 0 && (
          <p className="mt-0.5 text-muted-foreground">
            {`${result.unresolved_products} ${
              result.unresolved_products === 1 ? 'line names a product' : 'lines name products'
            } this company's catalogue does not carry, so ${
              result.unresolved_products === 1 ? 'it reads as non-standard' : 'they read as non-standard'
            }. Re-pick the product to clear it.`}
          </p>
        )}
      </div>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="shrink-0 self-start"
        onClick={onDismiss}
      >
        Dismiss
      </Button>
    </div>
  );
}
