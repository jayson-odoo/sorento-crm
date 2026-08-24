'use client';

/**
 * Presentational WHO primitive for form-detail banners (SLA / handling-lock /
 * rejection). Renders a person's display NAME as a `https://wa.me/{digits}`
 * hyperlink when a phone is resolvable, otherwise as plain text. This is the ONLY
 * place the wa.me URL is built, so the "correct rel attrs / never render a UUID"
 * rules are enforced once (PLAN §6.1, UAC Group FB / UUID).
 *
 * - `name` is trimmed; blank/absent → renders nothing (never an empty link).
 * - `waPhone` is stripped to bare digits (defence-in-depth; the backend already
 *   sends bare digits like `60123...`). No digits → plain `<span>`.
 * - Only ever renders the `name` string it is given - never an id. Callers MUST
 *   pass a resolved display name, never a raw `users.id` / `respond_contact_id`.
 */
export function PersonLink({
  name,
  waPhone,
  className,
}: {
  name?: string | null;
  waPhone?: string | null;
  className?: string;
}) {
  const label = name?.trim();
  if (!label) return null; // FB-3: never an empty link, never a UUID placeholder

  const digits = waPhone?.replace(/\D/g, ''); // defence-in-depth; BE already sends digits
  if (!digits) {
    return <span className={className}>{label}</span>; // FB-1: no phone → plain text
  }

  return (
    <a
      href={`https://wa.me/${digits}`}
      target="_blank"
      rel="noopener noreferrer"
      // Underline so a reviewer can see the name is a click-to-WhatsApp link
      // (the plain-text no-phone case above is intentionally NOT underlined).
      className={`underline decoration-dotted underline-offset-2 hover:decoration-solid${
        className ? ` ${className}` : ''
      }`}
    >
      {label}
    </a>
  ); // FB-2
}
