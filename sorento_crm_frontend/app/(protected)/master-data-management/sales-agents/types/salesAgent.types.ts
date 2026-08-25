/**
 * The salesperson master, as the backend serialises it.
 *
 * `source` carries `import` as well as the two the AutoCount mirror knows: a row an
 * outstanding-SO upload created on meeting a code nobody held. Those are the rows the
 * captain comes to this page to classify, so the type has to admit them.
 */
export interface SalesAgent {
  id: string;
  sales_agent: string;
  description: string | null;
  is_active: boolean;
  internal_note: string | null;
  follow_up: boolean;
  /** Who the codes belong to. Metadata, never identity. */
  person_label: string | null;
  /** What this agent's orders are for. Null = nobody has decided yet. */
  demand_class: string | null;
  /** Which warehouse-suffix ownership group this agent's stock lives in (e.g. `BB` for
   *  BRW-BB/MWH-BB/DC1-BB). Null = nobody has decided yet. */
  location_group: string | null;
  source: 'autocount' | 'manual' | 'import';
  created_at: string;
  updated_at: string | null;
}

/**
 * PATCH body for `/{id}/annotation`. The backend forbids unknown keys and treats an
 * omitted key as "leave it alone", so only the fields the modal actually edited are sent
 * and `null` means "unset this".
 *
 * Named `MirrorAnnotationPayload` because that is the name the AutoCount branch's detail
 * page imports; `SalesAgentAnnotationPayload` is an alias for it, so both spellings
 * resolve and the merge does not have to rename a call site.
 */
export interface MirrorAnnotationPayload {
  person_label?: string | null;
  demand_class?: string | null;
  location_group?: string | null;
  internal_note?: string | null;
  follow_up?: boolean;
  /** Whether the code is still sold under. Sales-agent only (the other mirror entities'
   *  PATCH does not accept it): a retired code has to leave the Agent pickers, and until
   *  the record page carried this switch there was no way to retire one at all. */
  is_active?: boolean;
}

export type SalesAgentAnnotationPayload = MirrorAnnotationPayload;

/**
 * POST body for `/bulk-annotate`. Same key semantics as the single-row PATCH - an omitted
 * field is left alone, `null` clears it - so the bulk action is that PATCH applied N times.
 *
 * No `person_label`: a label names ONE human, and applying one across a selection is the
 * write nobody means to make.
 */
export interface SalesAgentBulkAnnotatePayload {
  sales_agent_ids: string[];
  demand_class?: string | null;
  location_group?: string | null;
}
