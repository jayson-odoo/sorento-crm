'use client';

import Link from 'next/link';
import { GitBranch, CornerLeftUp } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { ProductVariantRef } from '../../types/product.types';

interface ProductVariantsTabProps {
  /** The current product's code — used to highlight each child's distinguishing suffix. */
  productCode: string;
  /** Parent product when this product is itself a variant; null for a base product. */
  variantOf?: ProductVariantRef | null;
  /** Direct child variants of this product. */
  variants?: ProductVariantRef[];
}

const PRODUCT_BASE_PATH = '/master-data-management/products';

/**
 * When the child code starts with the base code, dim the shared prefix and
 * bold the distinguishing suffix (e.g. SRTKT71SS **-BL**). Falls back to the
 * plain code when there is no clean prefix match — kept deliberately simple.
 */
function renderCode(childCode: string, baseCode: string) {
  if (baseCode && childCode.toLowerCase().startsWith(baseCode.toLowerCase())) {
    const prefix = childCode.slice(0, baseCode.length);
    const suffix = childCode.slice(baseCode.length);
    if (suffix) {
      return (
        <>
          <span className="text-muted-foreground">{prefix}</span>
          <span className="font-semibold">{suffix}</span>
        </>
      );
    }
  }
  return <span className="font-medium">{childCode}</span>;
}

export default function ProductVariantsTab({
  productCode,
  variantOf,
  variants,
}: ProductVariantsTabProps) {
  const children = variants ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Variants</CardTitle>
        <p className="text-sm text-muted-foreground">
          How this product relates to its variant family.
        </p>
      </CardHeader>
      <CardContent className="space-y-6">
        {/* Parent — only meaningful when this product is itself a variant */}
        <div>
          <h3 className="font-semibold mb-2">Variant of</h3>
          {variantOf ? (
            <Link
              href={`${PRODUCT_BASE_PATH}/${variantOf.id}`}
              className="flex items-center gap-2 rounded-md border px-3 py-2 hover:bg-muted transition-colors"
            >
              <CornerLeftUp className="size-4 text-muted-foreground shrink-0" />
              <Badge variant="secondary" appearance="ghost">
                Base
              </Badge>
              <div className="min-w-0 flex-1">
                <div
                  className="font-medium truncate"
                  title={`${variantOf.product_code} — ${variantOf.product_name}`}
                >
                  {variantOf.product_code}
                </div>
                <div className="text-xs text-muted-foreground truncate">
                  {variantOf.product_name}
                </div>
              </div>
            </Link>
          ) : (
            <p className="text-sm text-muted-foreground">
              This is a base product — it is not a variant of another product.
            </p>
          )}
        </div>

        {/* Children — the variant list */}
        <div>
          <h3 className="font-semibold mb-2">
            Variants{children.length ? ` (${children.length})` : ''}
          </h3>
          {children.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No variants of this product.
            </p>
          ) : (
            <div className="flex flex-col gap-2">
              {children.map((child) => (
                <Link
                  key={child.id}
                  href={`${PRODUCT_BASE_PATH}/${child.id}`}
                  className="flex items-center gap-2 rounded-md border px-3 py-2 hover:bg-muted transition-colors"
                >
                  <GitBranch className="size-4 text-muted-foreground shrink-0" />
                  <div className="min-w-0 flex-1">
                    <div
                      className="truncate"
                      title={`${child.product_code} — ${child.product_name}`}
                    >
                      {renderCode(child.product_code, productCode)}
                    </div>
                    <div className="text-xs text-muted-foreground truncate">
                      {child.product_name}
                    </div>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
