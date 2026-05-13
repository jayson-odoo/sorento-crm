'use client';

import { useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Eye } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { getPromotionsByProductId } from '@/app/(protected)/marketing-management/promotions/services/promotionService';
import type { PromotionProduct } from '@/app/(protected)/marketing-management/promotions/types/promotion.types';

interface ProductPromotionsTabProps {
  productId: string;
  listPrice?: number | null;
}

const fmtMyr = (v: number | null | undefined) =>
  v == null
    ? '-'
    : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'MYR' }).format(Number(v));

function formatDiscount(line: PromotionProduct, listPrice?: number | null): string {
  const pct = line.discount_percent != null ? Number(line.discount_percent) : null;
  if (pct != null && pct > 0) return `${pct.toFixed(2)}%`;

  const amt = line.discount_amount != null ? Number(line.discount_amount) : null;
  if (amt != null && amt > 0) return fmtMyr(amt);

  const sell = line.promotion_price != null ? Number(line.promotion_price) : null;
  const lp = listPrice != null ? Number(listPrice) : null;
  if (sell != null && lp != null && lp > 0 && sell < lp) {
    const derived = ((lp - sell) / lp) * 100;
    return `${derived.toFixed(2)}%`;
  }
  return '-';
}

export default function ProductPromotionsTab({ productId, listPrice }: ProductPromotionsTabProps) {
  const router = useRouter();
  const { data, isLoading } = useQuery({
    queryKey: ['product-promotions', productId],
    queryFn: () => getPromotionsByProductId(productId),
    enabled: !!productId,
  });

  const lines = data ?? [];

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Promotions</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
            <Skeleton className="h-10 w-full" />
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Promotions</CardTitle>
        <p className="text-sm text-muted-foreground">
          Promotions that include this product.
        </p>
      </CardHeader>
      <CardContent className="p-0">
        {lines.length === 0 ? (
          <div className="text-center py-8 text-muted-foreground">
            <p>No promotions linked to this product.</p>
            <p className="text-sm mt-2">Add this product to a promotion from Marketing → Promotions.</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[140px]">Promotion Code</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="w-[120px] text-right">List Price</TableHead>
                <TableHead className="w-[100px] text-right">Discount</TableHead>
                <TableHead className="w-[140px] text-right">Selling Price</TableHead>
                <TableHead className="w-[90px] text-right">Action</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {lines.map((line) => {
                const promo = line.promotion;
                const desc = promo?.description?.trim() || promo?.name || '-';
                const sell = line.promotion_price != null ? Number(line.promotion_price) : null;
                return (
                  <TableRow key={line.id}>
                    <TableCell className="font-medium">
                      <div className="flex items-center gap-2">
                        <span>{promo?.promo_code || '-'}</span>
                        {promo?.is_active === false && (
                          <Badge variant="secondary" appearance="ghost">
                            Inactive
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="max-w-[360px] truncate" title={desc}>
                      {desc}
                    </TableCell>
                    <TableCell className="text-right">{fmtMyr(listPrice)}</TableCell>
                    <TableCell className="text-right">{formatDiscount(line, listPrice)}</TableCell>
                    <TableCell className="text-right">{fmtMyr(sell)}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="outline"
                        disabled={!promo?.id}
                        onClick={() =>
                          promo?.id && router.push(`/marketing-management/promotions/${promo.id}`)
                        }
                      >
                        <Eye className="size-4" />
                        View
                      </Button>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
