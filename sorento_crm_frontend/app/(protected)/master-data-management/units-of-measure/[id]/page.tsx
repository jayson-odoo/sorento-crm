'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft, Edit, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import { PageHeader } from '@/components/common/PageHeader';
import { useUOM } from '../hooks/useUOM';
import { useDeferredAction } from '@/hooks/useDeferredAction';
import { useBackToListHref } from '@/components/common/BackToList';
import { formatDate } from '@/lib/helpers';

export default function UOMDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  // The list wrote its page, sort and search into this URL when the row was
  // clicked; Back hands the same string back rather than a fresh page 1.
  const backHref = useBackToListHref('/master-data-management/units-of-measure');
  const { data: uom, isLoading } = useUOM(id);

  // Delete asks nothing (D7). It parks the deletion for ten seconds and the
  // countdown takes the Delete button's place, so the way back is Cancel.
  const deletion = useDeferredAction({
    actionKey: 'uom.delete',
    entityType: 'uom',
    entityId: id,
    verb: 'Deleting',
    subject: uom ? `${uom.uom_name} (${uom.uom_code})` : '',
    surface: 'inline',
    watchFromMount: true,
    successMessage: 'Unit of measure deleted',
    // The select is what every product form picks a UOM from; the immediate mutation
    // refetched both, and only refetching the list leaves a deleted unit selectable.
    invalidateKeys: [['uoms'], ['uom-select']],
    onCommitted: () => router.push(backHref),
  });

  if (isLoading) {
    return (
      <>
        <Container>
          <PageHeader
            title="Unit of Measure"
            actions={
              <Button asChild variant="outline">
                <Link href={backHref}>
                  <MoveLeft /> Back to UOMs
                </Link>
              </Button>
            }
          />
        </Container>
        <Container>
          <div className="space-y-6">
            <Skeleton className="h-10 w-64" />
            <Skeleton className="h-96 w-full" />
          </div>
        </Container>
      </>
    );
  }

  if (!uom) {
    return (
      <>
        <Container>
          <PageHeader
            title="Unit of Measure"
            actions={
              <Button asChild variant="outline">
                <Link href={backHref}>
                  <MoveLeft /> Back to UOMs
                </Link>
              </Button>
            }
          />
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">UOM not found</p>
            <Button
              variant="outline"
              onClick={() => router.push(backHref)}
              className="mt-4"
            >
              <MoveLeft className="size-4" />
              Back to Units of Measure
            </Button>
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Container>
        <PageHeader
          title="Unit of Measure"
          actions={
            <Button asChild variant="outline">
              <Link href={backHref}>
                <MoveLeft /> Back to UOMs
              </Link>
            </Button>
          }
        />
      </Container>

      <Container>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <h2 className="text-2xl font-bold">{uom.uom_name}</h2>
              <p className="text-sm text-muted-foreground">
                UOM Code: {uom.uom_code}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => router.push(`/master-data-management/units-of-measure/${id}/edit`)}
              >
                <Edit className="size-4" />
                Edit
              </Button>
              {deletion.countdown ?? (
                <Button
                  variant="destructive"
                  onClick={() => deletion.start()}
                  disabled={deletion.isPending}
                >
                  <Trash2 className="size-4" />
                  Delete
                </Button>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">UOM Code</p>
                  <p className="font-medium">{uom.uom_code}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">UOM Name</p>
                  <p className="font-medium">{uom.uom_name}</p>
                </div>
                {uom.base_uom && (
                  <div>
                    <p className="text-sm text-muted-foreground">Base UOM</p>
                    <p className="font-medium">
                      {uom.base_uom.uom_name} ({uom.base_uom.uom_code})
                    </p>
                  </div>
                )}
                {uom.conversion_factor && (
                  <div>
                    <p className="text-sm text-muted-foreground">Conversion Factor</p>
                    <p className="font-medium">{uom.conversion_factor}</p>
                  </div>
                )}
                {/* Always rendered: 0 is a real answer (whole units only), and a
                    section that disappears on 0 reads as a missing value. */}
                <div>
                  <p className="text-sm text-muted-foreground">Decimal Places</p>
                  <p className="font-medium">
                    {uom.decimal_places === null || uom.decimal_places === undefined
                      ? 'Not set'
                      : uom.decimal_places === 0
                        ? '0 (whole units only)'
                        : uom.decimal_places}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-sm">
                    {formatDate(new Date(uom.created_at))}
                  </p>
                </div>
                {uom.updated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Last Updated</p>
                    <p className="font-medium text-sm">
                      {formatDate(new Date(uom.updated_at))}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>

            {uom.description && (
              <Card>
                <CardHeader>
                  <CardTitle>Description</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="whitespace-pre-wrap">{uom.description}</p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </Container>
    </>
  );
}
