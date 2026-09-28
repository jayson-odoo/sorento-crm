export type LogoAlignment = 'left' | 'center';
export type HeaderStyle = 'brand' | 'white';
export type ButtonWidth = 'auto' | 'full';
export type EmailFont = 'system' | 'arial' | 'helvetica' | 'verdana' | 'trebuchet' | 'georgia';

export interface EmailThemeSocialLink {
  label: string;
  url: string;
}

/** Every field optional/nullable - null means "use the default" (D1, AC-EM020). */
export interface EmailTheme {
  logo_url?: string | null;
  logo_alignment?: LogoAlignment | null;
  logo_height?: number | null;
  header_style?: HeaderStyle | null;
  primary_color?: string | null;
  accent_color?: string | null;
  page_background?: string | null;
  button_color?: string | null;
  button_text_color?: string | null;
  button_radius?: number | null;
  button_width?: ButtonWidth | null;
  card_radius?: number | null;
  font?: EmailFont | null;
  company_name?: string | null;
  address?: string | null;
  help_email?: string | null;
  help_url?: string | null;
  footer_note?: string | null;
  social_links?: EmailThemeSocialLink[] | null;
}

/** Same keys as `EmailTheme`, every field filled - what an unset field falls back to. */
export type ResolvedEmailTheme = Required<{
  [K in keyof EmailTheme]: NonNullable<EmailTheme[K]>;
}>;

export interface EmailThemeFontOption {
  value: string;
  label: string;
}

export interface EmailThemeResponse {
  theme: EmailTheme;
  defaults: ResolvedEmailTheme;
  fonts: EmailThemeFontOption[];
}

export interface EmailThemePreview {
  subject: string;
  body_html: string;
  body_text: string;
}
