'use client';

import * as React from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { MoveLeft, Settings2, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from '@/components/ui/breadcrumb';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Container } from '@/components/common/container';
import { ConfirmDeleteDialog } from '@/components/common/ConfirmDeleteDialog';
import RecordNavigation from '@/components/common/RecordNavigation';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SearchableSelect } from '@/components/common/SearchableSelect';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { Skeleton } from '@/components/ui/skeleton';
import { Textarea } from '@/components/ui/textarea';
import {
  Toolbar,
  ToolbarActions,
  ToolbarHeading,
  ToolbarTitle,
} from '@/components/common/toolbar';
import { useBrandSelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-brand-select-query';
import { useProductCategorySelectQuery } from '@/app/(protected)/master-data-management/shared/hooks/use-product-category-select-query';
import { useProjectSeries, useSeriesMutations } from '../../../_shared/hooks/useProjects';
import type { ProjectSeries } from '../../../_shared/types/project.types';
import { SeriesProductsTable } from './SeriesProductsTable';
import { SeriesSheetLoader } from './SeriesSheetLoader';

const NEW = 'new';

/**
 * One series, on its own page.
 *
 * A page and not a dialog, on the client's instruction: they want to click a row, see the
 * form, and edit it. The layout vocabulary is the users detail page - Container, Toolbar with
 * the title, breadcrumb and a Back button, then stacked section cards - but NOT its editing
 * model, which puts the form in a modal.
 *
 * There is no explanatory prose anywhere on this screen. The previous version described what a
 * series was for above the fields; the rule is that a screen needing that has already failed.
 */
export function SeriesDetailClient({ seriesId }: { seriesId: string }) {
  const router = useRouter();
  const isNew = seriesId === NEW;
  const series = useProjectSeries(true);
  const { create, update, remove } = useSeriesMutations();
  const brands = useBrandSelectQuery();
  const categories = useProductCategorySelectQuery();

  const row: ProjectSeries | null = React.useMemo(
    () => (series.data ?? []).find((item) => item.id === seriesId) ?? null,
    [series.data, seriesId],
  );

  const [name, setName] = React.useState('');
  const [brandId, setBrandId] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [isActive, setIsActive] = React.useState(true);
  const [categoryIds, setCategoryIds] = React.useState<string[]>([]);
  const [seeded, setSeeded] = React.useState(false);
  const [confirmingDelete, setConfirmingDelete] = React.useState(false);

  // Seed ONCE from the server row. Re-seeding on every render of a refetched list would
  // overwrite what somebody is halfway through typing - the same trap the line table avoids.
  React.useEffect(() => {
    if (isNew || seeded || !row) return;
    setName(row.name);
    setBrandId(row.brand_id ?? '');
    setDescription(row.description ?? '');
    setIsActive(row.is_active);
    setCategoryIds(row.category_ids ?? []);
    setSeeded(true);
  }, [isNew, row, seeded]);

  const pending = create.isPending || update.isPending;
  const loading = series.isLoading && !isNew;
  const dirty = isNew
    ? name.trim().length > 0
    : Boolean(
        row &&
          (name !== row.name ||
            brandId !== (row.brand_id ?? '') ||
            description !== (row.description ?? '') ||
            isActive !== row.is_active ||
            categoryIds.join(',') !== (row.category_ids ?? []).join(',')),
      );

  const save = async () => {
    if (!name.trim()) {
      toast.error('The series needs a name');
      return;
    }
    const body = {
      name: name.trim(),
      brand_id: brandId || null,
      description: description.trim() || null,
      is_active: isActive,
      category_ids: categoryIds,
    };
    if (isNew) {
      const created = await create.mutateAsync(body);
      // Land on the saved series so its products table becomes reachable: a brand-new series
      // has no id to hang products off until this moment.
      router.replace(`/project-sales/series/${created.id}`);
      return;
    }
    await update.mutateAsync({ id: seriesId, body });
    setSeeded(false);
  };

  const brandOptions = React.useMemo(
    () =>
      (brands.data ?? [])
        .filter((brand) => brand.is_active || brand.id === brandId)
        .map((brand) => ({
          value: brand.id,
          label: brand.brand_name,
          description: brand.brand_code,
        })),
    [brandId, brands.data],
  );

  const categoryOptions = React.useMemo(
    () =>
      (categories.data ?? [])
        .filter((category) => category.is_active || categoryIds.includes(category.id))
        .map((category) => ({
          value: category.id,
          label: category.category_name,
          description: category.category_code,
        })),
    [categories.data, categoryIds],
  );

  return (
    <Container>
      <Toolbar>
        <ToolbarHeading>
          <ToolbarTitle>{isNew ? 'New series' : row?.name || 'Series'}</ToolbarTitle>
          <Breadcrumb>
            <BreadcrumbList>
              <BreadcrumbItem>
                <BreadcrumbLink href="/">Home</BreadcrumbLink>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbPage>Project Sales</BreadcrumbPage>
              </BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                <BreadcrumbLink href="/project-sales/series">Series</BreadcrumbLink>
              </BreadcrumbItem>
            </BreadcrumbList>
          </Breadcrumb>
        </ToolbarHeading>
        <ToolbarActions>
          {/* Step through the series without going back to the list, the way the users
              detail does. List mode rather than a neighbours endpoint: the whole series
              list is already in memory here (it is what resolves this page's row), so
              asking the server for two ids would be a round trip to learn what we hold. */}
          {!isNew && row && (series.data ?? []).length > 1 && (
            <RecordNavigation
              basePath="/project-sales/series"
              currentId={seriesId}
              items={series.data ?? []}
              ariaLabel="series"
            />
          )}
          <Button asChild variant="outline">
            <Link href="/project-sales/series">
              <MoveLeft /> Back to series
            </Link>
          </Button>
          {/* Destructive actions live behind the gear, not beside Back: Delete sat one
              button away from the thing people click to leave the page. */}
          {!isNew && row && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" mode="icon" aria-label="Series actions">
                  <Settings2 className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  variant="destructive"
                  onSelect={(event) => {
                    // The menu closes on select and would unmount the dialog's trigger
                    // context mid-open; defer so the confirmation actually appears.
                    event.preventDefault();
                    setConfirmingDelete(true);
                  }}
                >
                  <Trash2 className="size-4" aria-hidden />
                  Delete
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          )}
        </ToolbarActions>
      </Toolbar>

      <div className="space-y-6">
        <Card>
          <CardContent className="space-y-5 pt-5">
            {loading ? (
              <div className="space-y-3">
                <Skeleton className="h-9 w-full max-w-md" />
                <Skeleton className="h-9 w-full max-w-md" />
              </div>
            ) : (
              <>
                <div className="grid gap-5 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="series-name">Name</Label>
                    <Input
                      id="series-name"
                      value={name}
                      onChange={(event) => setName(event.target.value)}
                      placeholder="Sanitaryware template"
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="series-brand">Brand</Label>
                    <SearchableSelect
                      id="series-brand"
                      value={brandId}
                      onChange={setBrandId}
                      options={brandOptions}
                      placeholder="Any brand"
                      emptyMessage="No brands found"
                    />
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Categories</Label>
                  <SearchableMultiSelect
                    value={categoryIds}
                    onChange={setCategoryIds}
                    options={categoryOptions}
                    placeholder="No categories"
                    emptyMessage="No categories found"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="series-description">Description</Label>
                  <Textarea
                    id="series-description"
                    value={description}
                    onChange={(event) => setDescription(event.target.value)}
                    rows={2}
                  />
                </div>

                <div className="flex items-center gap-2">
                  <Checkbox
                    id="series-active"
                    checked={isActive}
                    onCheckedChange={(next) => setIsActive(Boolean(next))}
                  />
                  <Label htmlFor="series-active">Active</Label>
                </div>

                <div className="flex flex-wrap justify-end gap-2 pt-1">
                  <Button
                    variant="outline"
                    onClick={() => router.push('/project-sales/series')}
                  >
                    Cancel
                  </Button>
                  <Button onClick={() => void save()} disabled={!dirty || pending}>
                    {isNew ? 'Create series' : 'Save changes'}
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        {/* The sheet, in the system. Only once the series exists: products hang off its id. */}
        {!isNew && row && (
          <Card>
            <CardHeader>
              <CardTitle>Load the sheet</CardTitle>
            </CardHeader>
            <CardContent>
              <SeriesSheetLoader series={row} />
            </CardContent>
          </Card>
        )}

        {!isNew && (
          <Card>
            <CardHeader>
              <CardTitle>Products</CardTitle>
            </CardHeader>
            <CardContent>
              <SeriesProductsTable seriesId={seriesId} />
            </CardContent>
          </Card>
        )}
      </div>

      {row && (
        <ConfirmDeleteDialog
          open={confirmingDelete}
          onOpenChange={setConfirmingDelete}
          description={`Delete the series "${row.name}"? This action cannot be undone. A series still used by a quotation cannot be deleted, so deactivate it instead.`}
          onDelete={async () => {
            await remove.mutateAsync(row.id);
            router.push('/project-sales/series');
          }}
        />
      )}
    </Container>
  );
}
