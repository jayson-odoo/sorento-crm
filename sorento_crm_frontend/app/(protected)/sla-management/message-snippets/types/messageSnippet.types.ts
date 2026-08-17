/**
 * Composer message snippets (UAC AC-L4).
 *
 * A snippet is canned wording an admin manages once and every agent inserts
 * from the ticket composer. Workspace-global in v1: no owner, no scope.
 */

export interface MessageSnippet {
  id: string;
  name: string;
  /** The "/" keyword, stored WITHOUT the slash. Null when the snippet has none. */
  shortcut: string | null;
  /** The stored wording, `$tokens` intact. */
  body: string;
  is_active: boolean;
  created_at: string;
  updated_at: string | null;
}

export interface MessageSnippetFormData {
  name: string;
  shortcut?: string | null;
  body: string;
  is_active: boolean;
}

/** One row of the composer's "/" picker. */
export interface MessageSnippetOption {
  id: string;
  name: string;
  shortcut: string | null;
  /** What the admin typed, with `$tokens` still in it (shown as the preview). */
  body: string;
  /** The same text with this ticket's context substituted. THIS is inserted. */
  resolved_body: string;
}

/**
 * The `$variables` a snippet body may use. Everything else that looks like a
 * token is left literal by the backend, so "$50 deposit" survives an insert.
 */
export const SNIPPET_VARIABLES: { token: string; description: string }[] = [
  { token: '$contact_name', description: "The contact's name" },
  { token: '$assignee_name', description: 'Your name' },
  { token: '$ticket_ref', description: 'The enquiry reference' },
];
