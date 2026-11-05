/**
 * A tag template's hand-picked price type (PRICETAG-COMBO-FORMAT): LP, SP, both, or not set.
 * An unset template is offered on both kinds of line, so nothing changes until the owner picks.
 */

export type TemplatePriceType = 'list' | 'selling' | 'both';
export type LinePriceType = 'list' | 'selling';

export const TEMPLATE_PRICE_TYPE_LABEL: Record<TemplatePriceType, string> = {
  list: 'LP',
  selling: 'SP',
  both: 'LP & SP',
};

export const TEMPLATE_PRICE_TYPE_OPTIONS: Array<{ value: TemplatePriceType; label: string }> = [
  { value: 'list', label: 'LP' },
  { value: 'selling', label: 'SP' },
  { value: 'both', label: 'LP & SP' },
];

/** Whether a template of this type may print a line of `lineType` (unset fits both; a line with
 * no type fits everything). Same rule as the server's `fits`. */
export function templateFitsLine(
  templateType: TemplatePriceType | null | undefined,
  lineType: LinePriceType | null | undefined,
): boolean {
  if (!lineType || !templateType) return true;
  return templateType === 'both' || templateType === lineType;
}

export function lineTypeLabel(lineType: LinePriceType): 'LP' | 'SP' {
  return lineType === 'list' ? 'LP' : 'SP';
}

/** The options that fit a line of `lineType` (all of them for a line with no type). */
export function fittingOptions<T extends { price_type?: TemplatePriceType | null }>(
  options: T[],
  lineType: LinePriceType | null | undefined,
): T[] {
  return options.filter((option) => templateFitsLine(option.price_type, lineType));
}

/**
 * The template a line of `lineType` starts on: that type's default among the fitting links, else
 * the only fitting link, else none (several and no default = the salesperson picks).
 */
export function defaultOptionFor<
  T extends {
    price_type?: TemplatePriceType | null;
    default_list?: boolean;
    default_selling?: boolean;
    is_default?: boolean;
  },
>(options: T[], lineType: LinePriceType | null | undefined): T | null {
  const fitting = fittingOptions(options, lineType);
  // An older payload carries only `is_default`; it stands for both types.
  const flagged = fitting.find((option) =>
    lineType === 'selling'
      ? (option.default_selling ?? option.is_default)
      : lineType === 'list'
        ? (option.default_list ?? option.is_default)
        : option.is_default,
  );
  return flagged ?? (fitting.length === 1 ? fitting[0] : null);
}
