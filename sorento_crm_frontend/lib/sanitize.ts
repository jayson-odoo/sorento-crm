import DOMPurify from 'isomorphic-dompurify';

/**
 * Sanitize an untrusted HTML string before feeding it to
 * `dangerouslySetInnerHTML`. Use for ANY HTML that originated from a user or an
 * external system (chat messages, ticket/notes/email bodies) — see
 * PLAN-fix-security-cluster Sub-plan E-2. Strips scripts, event handlers, and
 * other XSS vectors while keeping ordinary formatting.
 *
 * Returns an object ready to spread into the prop:
 *   <div dangerouslySetInnerHTML={sanitizedHtml(message.text)} />
 */
export function sanitizeHtml(dirty: string | null | undefined): string {
  if (!dirty) return '';
  return DOMPurify.sanitize(dirty, {
    // Links are common in chat/email bodies; force them safe.
    ADD_ATTR: ['target', 'rel'],
    // Block javascript:/data: URL schemes and inline event handlers by default
    // (DOMPurify does this out of the box; kept explicit for intent).
    FORBID_ATTR: ['onerror', 'onload', 'onclick', 'onmouseover'],
    FORBID_TAGS: ['script', 'style', 'iframe', 'object', 'embed', 'form'],
  });
}

/** Convenience: returns the `{ __html }` object for `dangerouslySetInnerHTML`. */
export function sanitizedHtml(dirty: string | null | undefined): { __html: string } {
  return { __html: sanitizeHtml(dirty) };
}
