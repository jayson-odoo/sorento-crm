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
