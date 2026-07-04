import { Badge } from '@/components/ui/badge';

/**
 * Base/Variant pill for the products list Type column. A product is a "Variant"
 * when it points at a parent (`is_variant` from the variant graph); otherwise
 * it is a "Base". Extracted so the list badge is unit-testable in isolation.
 */
export function ProductTypeBadge({ isVariant }: { isVariant?: boolean }) {
  return isVariant ? (
    <Badge variant="info" appearance="ghost">
      Variant
    </Badge>
  ) : (
    <Badge variant="secondary" appearance="ghost">
      Base
    </Badge>
  );
}

export default ProductTypeBadge;
