'use client';

/**
 * Choosing which photo of a product goes in a brochure (S7.0).
 *
 * **Why this screen exists.** `product_attachments.is_primary` has always been
 * the flag that decides a catalogue tile's photo - `product_images.py` already
 * orders by it - and it is false on every one of the 1,087 photo rows behind the
 * flyer's products. So a tile shows whichever row happened to be linked first.
 * `SRTWC286-SH` has 31 linked images, among them a blank page and two other
 * products' photographs. There is nothing to fix in the renderer; somebody has
 * to say which picture is the product.
 *
 * **Nothing is chosen on the user's behalf.** A filename matching the product
 * code would identify the right image for 509 of 535 products, and that is
 * deliberately not used: a wrong photo is a wrong product in front of a
 * customer, and the same wrong photo fed to a mesh generator is that plus a
 * bill. Even a product with exactly one candidate takes a click.
 */

import { useEffect, useMemo, useState } from 'react';

import { SearchableSelect } from '@/components/common/SearchableSelect';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertIcon, AlertTitle } from '@/components/ui/alert';
import { Input } from '@/components/ui/input';
import { Switch } from '@/components/ui/switch';
import { Label } from '@/components/ui/label';
import { TriangleAlert, Check, ImageOff } from 'lucide-react';

import { BROCHURE_IMAGE_PAGE_SIZE, PROMOTION_PAGE_SIZE } from '../../services/brochureImageService';
import {
  useBrochureImagePromotionOptions,
  useBrochureImagesQuery,
  useSetBrochureImage,
} from '../hooks/useBrochureImages';

export function BrochureImagePicker() {
  const [promotionId, setPromotionId] = useState('');
  const [onlyUnset, setOnlyUnset] = useState(true);
  const [searchInput, setSearchInput] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const promotionOptions = useBrochureImagePromotionOptions();

  // Debounced so typing a product code is one request, not one per keystroke.
  useEffect(() => {
    const timer = setTimeout(() => setSearch(searchInput), 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  // Any change of filter is a different worklist, so page 1 is where it starts.
  useEffect(() => {
    setPage(1);
  }, [promotionId, onlyUnset, search]);

  const query = useBrochureImagesQuery({
    promotionId,
    onlyUnset,
    query: search,
    page,
    limit: BROCHURE_IMAGE_PAGE_SIZE,
  });

  const setImage = useSetBrochureImage();

  /**
   * What the user just clicked, held until the refetch confirms it.
   *
   * Without this the tile shows nothing chosen for as long as the round trip
   * takes, which reads as "the click did not register" and invites a second
   * click on a different candidate.
   */
  const [pendingChoice, setPendingChoice] = useState<Record<string, string>>({});

  const rows = useMemo(
    () =>
      (query.data?.items ?? []).map((row) => ({
        ...row,
        chosenAttachmentId: pendingChoice[row.productId] ?? row.chosenAttachmentId,
      })),
    [query.data, pendingChoice],
  );

  const total = query.data?.total ?? 0;
  const remaining = query.data?.remaining ?? 0;
  const withoutCandidates = rows.filter((row) => row.candidates.length === 0).length;
  // `shown`, not `total`: `total` counts everything matching the filter, while
  // the "only products still without an image" switch means only `shown` of them
  // can appear. Paging over `total` offers pages that hold nothing - a
  // 998-product promotion with 900 answered would advertise 40 pages for 4.
  const listable = query.data?.shown ?? 0;
  const pageCount = Math.max(1, Math.ceil(listable / BROCHURE_IMAGE_PAGE_SIZE));

  const choose = (productId: string, attachmentId: string, isChosen: boolean) => {
    // Idempotent, not a toggle: clicking the chosen one again leaves it chosen
    // rather than putting the product back to having no image at all.
    if (isChosen) return;
    setPendingChoice((current) => ({ ...current, [productId]: attachmentId }));
    setImage.mutate({ productId, attachmentId });
  };

  return (
    <div className="flex flex-col gap-5">
      <Card>
        <CardContent className="flex flex-col gap-4 py-5 lg:flex-row lg:items-end lg:justify-between">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor="dk-bi-promotion" className="text-xs text-muted-foreground">
                Promotion
              </Label>
              <SearchableSelect
                id="dk-bi-promotion"
                value={promotionId}
                onChange={setPromotionId}
                // Server-searched and paged: there are hundreds of promotions,
                // so a static option list would cap the filter at one page and
                // hide the rest without saying so.
                fetchOptions={promotionOptions.fetchOptions}
                paginated
                pageSize={PROMOTION_PAGE_SIZE}
                selectedOption={promotionOptions.optionFor(promotionId)}
                placeholder="Every product"
                clearable
                className="w-full sm:w-72"
              />
            </div>
            <div className="flex min-w-0 flex-col gap-1.5">
              <Label htmlFor="dk-bi-search" className="text-xs text-muted-foreground">
                Product
              </Label>
              <Input
                id="dk-bi-search"
                value={searchInput}
                onChange={(event) => setSearchInput(event.target.value)}
                placeholder="Code or name"
                className="w-full sm:w-56"
              />
            </div>
            <div className="flex items-center gap-2 pb-1.5">
              <Switch id="dk-bi-only-unset" checked={onlyUnset} onCheckedChange={setOnlyUnset} />
              <Label htmlFor="dk-bi-only-unset" className="text-sm">
                Only products still without an image
              </Label>
            </div>
          </div>

          <div className="text-sm text-muted-foreground" data-dk-bi-remaining>
            {remaining} of {total} still to choose
          </div>
        </CardContent>
      </Card>

      {withoutCandidates > 0 && (
        <Alert variant="warning" appearance="light">
          <AlertIcon>
            <TriangleAlert />
          </AlertIcon>
          {/* Scoped to the page in the wording, because that is all it counts.
              Unqualified, page 1 of the flyer reads "25 products have no photo"
              when the figure across the filter is 465. */}
          <AlertTitle>
            {withoutCandidates === 1
              ? '1 product on this page has'
              : `${withoutCandidates} products on this page have`}{' '}
            no photo to choose from. Attach a photo first.
          </AlertTitle>
        </Alert>
      )}

      {query.isPending && (
        <div className="flex flex-col gap-4" data-dk-bi-loading>
          {[0, 1, 2].map((index) => (
            <Card key={index}>
              <CardContent className="flex flex-col gap-3 py-5">
                <Skeleton className="h-4 w-48" />
                <div className="flex gap-3">
                  {[0, 1, 2, 3].map((tile) => (
                    <Skeleton key={tile} className="h-24 w-24 rounded-md" />
                  ))}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {query.isError && (
        <Alert variant="destructive" appearance="light" data-dk-bi-error>
          <AlertIcon>
            <TriangleAlert />
          </AlertIcon>
          <AlertTitle>
            {(query.error as Error)?.message || 'The product list could not be loaded.'}
            <Button
              variant="inverse"
              size="sm"
              className="ms-3"
              onClick={() => query.refetch()}
            >
              Try again
            </Button>
          </AlertTitle>
        </Alert>
      )}

      {query.isSuccess && rows.length === 0 && (
        <Card data-dk-bi-empty>
          <CardContent className="flex flex-col items-center gap-2 py-14 text-center">
            <Check className="size-8 text-muted-foreground" />
            <div className="text-base font-medium">Every product here has a brochure image</div>
            <p className="max-w-md text-sm text-muted-foreground">
              Turn off the filter above to review or change one.
            </p>
          </CardContent>
        </Card>
      )}

      {query.isSuccess &&
        rows.map((row) => (
          <Card key={row.productId} data-dk-bi-row={row.productCode}>
            <CardHeader className="flex-col items-start gap-1 py-4">
              <CardTitle className="text-sm">
                {row.productCode}
                {row.chosenAttachmentId && (
                  <Badge variant="success" appearance="light" size="sm" className="ms-2">
                    chosen
                  </Badge>
                )}
              </CardTitle>
              <div className="text-xs text-muted-foreground">
                {row.productName}
                {row.candidates.length > 0 && (
                  <>
                    {' '}
                    &middot; {row.candidates.length} candidate
                    {row.candidates.length === 1 ? '' : 's'}
                  </>
                )}
              </div>
            </CardHeader>
            <CardContent className="py-4">
              {row.candidates.length === 0 ? (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <ImageOff className="size-4" />
                  No photo is linked to this product yet.
                </div>
              ) : (
                <div className="grid grid-cols-[repeat(auto-fill,minmax(112px,1fr))] gap-3">
                  {row.candidates.map((candidate) => {
                    const isChosen = candidate.attachmentId === row.chosenAttachmentId;
                    return (
                      <button
                        key={candidate.attachmentId}
                        type="button"
                        onClick={() => choose(row.productId, candidate.attachmentId, isChosen)}
                        aria-pressed={isChosen}
                        data-dk-bi-candidate={candidate.filename}
                        className={`group flex flex-col gap-2 rounded-lg border p-2 text-start transition ${
                          isChosen
                            ? 'border-primary ring-2 ring-primary/25'
                            : 'border-border hover:border-primary/50'
                        }`}
                      >
                        <div className="relative aspect-square overflow-hidden rounded-md bg-muted">
                          {candidate.url ? (
                            // A plain img, not next/image: the src is a signed
                            // URL on a storage host that changes per request,
                            // which the optimiser cannot cache anyway.
                            <img
                              src={candidate.url}
                              alt={candidate.filename}
                              className="size-full object-cover"
                            />
                          ) : (
                            <div className="flex size-full items-center justify-center text-muted-foreground">
                              <ImageOff className="size-5" />
                            </div>
                          )}
                          {isChosen && (
                            <span className="absolute end-1 top-1 rounded-full bg-primary p-1 text-primary-foreground">
                              <Check className="size-3" />
                            </span>
                          )}
                        </div>
                        {/* The filename is the only thing distinguishing one
                            thumbnail from another when the photo is of a
                            different product entirely, so it is never hidden. */}
                        <span className="truncate text-[11px]" title={candidate.filename}>
                          {candidate.filename}
                        </span>
                        {candidate.accessLevels?.includes('dealer') && (
                          <span className="text-[10px] text-muted-foreground">dealer only</span>
                        )}
                      </button>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>
        ))}

      {query.isSuccess && pageCount > 1 && (
        <div className="flex items-center justify-between" data-dk-bi-pager>
          <span className="text-sm text-muted-foreground">
            Page {page} of {pageCount}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= pageCount}
              onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            >
              Next
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
