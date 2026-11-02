/**
 * The promo price a promotion line displays. A line with no stored price shows its list
 * price (a promotion that only lists the product), except for a brand whose promotions
 * carry no selling price (CABANA-NO-SELLING-PRICE): that line shows none, never the list
 * price dressed up as a promotion price.
 */
export function displayPromoPrice(line: {
  promotion_price?: number | string | null;
  no_selling_price?: boolean;
  product?: { list_price?: number | string | null } | null;
}): number | null {
  if (line.no_selling_price) return null;
  return Number(line.promotion_price) || Number(line.product?.list_price) || 0;
}
