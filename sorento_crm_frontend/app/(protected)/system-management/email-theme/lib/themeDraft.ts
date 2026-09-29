import type { EmailTheme, EmailThemeSocialLink } from '../types/emailTheme.types';

/**
 * The form's own shape: every field is a plain string (numbers included, so a
 * number input can hold "" while it's being cleared) instead of `string |
 * null`. `toDraft` / `draftToPayload` are the one place that convert between
 * this and the wire shape, so a blank input always means the same thing:
 * "unset, use the default" (D1, AC-EM020/021).
 */
export interface ThemeDraft {
  logo_url: string;
  logo_alignment: string;
  logo_height: string;
  header_style: string;
  primary_color: string;
  accent_color: string;
  page_background: string;
  button_color: string;
  button_text_color: string;
  button_radius: string;
  button_width: string;
  card_radius: string;
  font: string;
  company_name: string;
  address: string;
  help_email: string;
  help_url: string;
  footer_note: string;
  social_links: EmailThemeSocialLink[];
}

function s(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

export function toDraft(theme: EmailTheme | null | undefined): ThemeDraft {
  return {
    logo_url: s(theme?.logo_url),
    logo_alignment: s(theme?.logo_alignment),
    logo_height: s(theme?.logo_height),
    header_style: s(theme?.header_style),
    primary_color: s(theme?.primary_color),
    accent_color: s(theme?.accent_color),
    page_background: s(theme?.page_background),
    button_color: s(theme?.button_color),
    button_text_color: s(theme?.button_text_color),
    button_radius: s(theme?.button_radius),
    button_width: s(theme?.button_width),
    card_radius: s(theme?.card_radius),
    font: s(theme?.font),
    company_name: s(theme?.company_name),
    address: s(theme?.address),
    help_email: s(theme?.help_email),
    help_url: s(theme?.help_url),
    footer_note: s(theme?.footer_note),
    social_links: theme?.social_links ? theme.social_links.map((l) => ({ ...l })) : [],
  };
}

function textOrNull(value: string): string | null {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
}

function numberOrNull(value: string): number | null {
  const trimmed = value.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

export function draftToPayload(draft: ThemeDraft): EmailTheme {
  const socialLinks = draft.social_links
    .map((l) => ({ label: l.label.trim(), url: l.url.trim() }))
    .filter((l) => l.label || l.url);

  return {
    logo_url: textOrNull(draft.logo_url),
    logo_alignment: textOrNull(draft.logo_alignment) as EmailTheme['logo_alignment'],
    logo_height: numberOrNull(draft.logo_height),
    header_style: textOrNull(draft.header_style) as EmailTheme['header_style'],
    primary_color: textOrNull(draft.primary_color),
    accent_color: textOrNull(draft.accent_color),
    page_background: textOrNull(draft.page_background),
    button_color: textOrNull(draft.button_color),
    button_text_color: textOrNull(draft.button_text_color),
    button_radius: numberOrNull(draft.button_radius),
    button_width: textOrNull(draft.button_width) as EmailTheme['button_width'],
    card_radius: numberOrNull(draft.card_radius),
    font: textOrNull(draft.font) as EmailTheme['font'],
    company_name: textOrNull(draft.company_name),
    address: textOrNull(draft.address),
    help_email: textOrNull(draft.help_email),
    help_url: textOrNull(draft.help_url),
    footer_note: textOrNull(draft.footer_note),
    social_links: socialLinks.length ? socialLinks : null,
  };
}
