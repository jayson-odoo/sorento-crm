'use client';

import { use } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { MoveLeft, Edit, Trash2 } from 'lucide-react';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Container } from '@/components/common/container';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { useBrand, useDeleteBrand } from '../hooks/useBrands';
import { formatDate } from '@/lib/helpers';
import { toast } from 'sonner';

export default function BrandDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const router = useRouter();
  const { data: brand, isLoading } = useBrand(id);
  const deleteMutation = useDeleteBrand();

  const handleDelete = async () => {
    if (!confirm('Are you sure you want to deactivate this brand?')) {
      return;
    }
    try {
      await deleteMutation.mutateAsync(id);
      router.push('/master-data-management/brands');
    } catch (error) {
      // Error is handled by the mutation hook
    }
  };

  if (isLoading) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Brand</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Product Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/master-data-management/brands">
                      Brands
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/master-data-management/brands">
                  <MoveLeft /> Back to brands
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
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

  if (!brand) {
    return (
      <>
        <Container>
          <Toolbar>
            <ToolbarHeading>
              <ToolbarTitle>Brand</ToolbarTitle>
              <Breadcrumb>
                <BreadcrumbList>
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/">Home</BreadcrumbLink>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>Product Management</BreadcrumbPage>
                  </BreadcrumbItem>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbLink href="/master-data-management/brands">
                      Brands
                    </BreadcrumbLink>
                  </BreadcrumbItem>
                </BreadcrumbList>
              </Breadcrumb>
            </ToolbarHeading>
            <ToolbarActions>
              <Button asChild variant="outline">
                <Link href="/master-data-management/brands">
                  <MoveLeft /> Back to brands
                </Link>
              </Button>
            </ToolbarActions>
          </Toolbar>
        </Container>
        <Container>
          <div className="text-center py-12">
            <p className="text-muted-foreground">Brand not found</p>
            <Button
              variant="outline"
              onClick={() => router.push('/master-data-management/brands')}
              className="mt-4"
            >
              <MoveLeft className="size-4" />
              Back to Brands
            </Button>
          </div>
        </Container>
      </>
    );
  }

  return (
    <>
      <Container>
        <Toolbar>
          <ToolbarHeading>
            <ToolbarTitle>Brand</ToolbarTitle>
            <Breadcrumb>
              <BreadcrumbList>
                <BreadcrumbItem>
                  <BreadcrumbLink href="/">Home</BreadcrumbLink>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbPage>Product Management</BreadcrumbPage>
                </BreadcrumbItem>
                <BreadcrumbSeparator />
                <BreadcrumbItem>
                  <BreadcrumbLink href="/master-data-management/brands">
                    Brands
                  </BreadcrumbLink>
                </BreadcrumbItem>
              </BreadcrumbList>
            </Breadcrumb>
          </ToolbarHeading>
          <ToolbarActions>
            <Button asChild variant="outline">
              <Link href="/master-data-management/brands">
                <MoveLeft /> Back to brands
              </Link>
            </Button>
          </ToolbarActions>
        </Toolbar>
      </Container>

      <Container>
        <div className="space-y-6">
          {/* Header */}
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-bold">{brand.brand_name}</h1>
                <Badge
                  variant={brand.is_active ? 'success' : 'secondary'}
                  appearance="ghost"
                >
                  {brand.is_active ? 'Active' : 'Inactive'}
                </Badge>
              </div>
              <p className="text-sm text-muted-foreground">
                Brand Code: {brand.brand_code}
              </p>
            </div>
            <div className="flex gap-2">
              <Button
                variant="outline"
                onClick={() => router.push(`/master-data-management/brands/${id}/edit`)}
              >
                <Edit className="size-4" />
                Edit
              </Button>
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={deleteMutation.isPending}
              >
                <Trash2 className="size-4" />
                Delete
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <Card>
              <CardHeader>
                <CardTitle>Basic Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <p className="text-sm text-muted-foreground">Brand Code</p>
                  <p className="font-medium">{brand.brand_code}</p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Brand Name</p>
                  <p className="font-medium">{brand.brand_name}</p>
                </div>
                {brand.manufacturer && (
                  <div>
                    <p className="text-sm text-muted-foreground">Manufacturer</p>
                    <p className="font-medium">{brand.manufacturer}</p>
                  </div>
                )}
                {brand.website && (
                  <div>
                    <p className="text-sm text-muted-foreground">Website</p>
                    <a
                      href={brand.website}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-primary hover:underline"
                    >
                      {brand.website}
                    </a>
                  </div>
                )}
                {brand.logo_url && (
                  <div>
                    <p className="text-sm text-muted-foreground mb-2">Logo</p>
                    <img
                      src={brand.logo_url}
                      alt={brand.brand_name}
                      className="size-20 rounded object-contain"
                    />
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge
                    variant={brand.is_active ? 'success' : 'secondary'}
                    appearance="ghost"
                  >
                    {brand.is_active ? 'Active' : 'Inactive'}
                  </Badge>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Additional Information</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                {brand.description && (
                  <div>
                    <p className="text-sm text-muted-foreground">Description</p>
                    <p className="font-medium whitespace-pre-wrap">{brand.description}</p>
                  </div>
                )}
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="font-medium text-sm">
                    {formatDate(new Date(brand.created_at))}
                  </p>
                </div>
                {brand.updated_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Last Updated</p>
                    <p className="font-medium text-sm">
                      {formatDate(new Date(brand.updated_at))}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </div>
      </Container>
    </>
  );
}
