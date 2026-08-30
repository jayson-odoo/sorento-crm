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
  /** The portal contact this agent IS. It decides which debtors that salesperson may
   *  pick from on the price tag request form. Null = nobody has linked it yet. */
  contact_id: string | null;
  /** Read-only, resolved by the backend: the person behind `contact_id`, so no screen
   *  ever has to print the id. */
  contact_name: string | null;
  source: 'autocount' | 'manual' | 'import';
  created_at: string;
  updated_at: string | null;
}

/** One row of the "Linked portal contact" picker. Name plus a masked phone, never an
 *  id: the id is the value, and the value is never what a person reads. */
export interface ContactSelectOption {
  id: string;
  name: string;
  masked_phone: string | null;
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
  contact_id?: string | null;
}

export type SalesAgentAnnotationPayload = MirrorAnnotationPayload;
