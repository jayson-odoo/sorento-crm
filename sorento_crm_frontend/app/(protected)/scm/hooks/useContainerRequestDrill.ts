/**
 * The drill behind one figure on one loading-plan row (R8, AC-B4).
 *
 * Fetched ON OPEN, per product and per kind, never for the whole grid: a page of rows would
 * otherwise carry three subscriptions each for dialogs nobody opened. Same reasoning as the
 * reorder plan's own `useLocationStock`.
 *
 * A short `staleTime`, because this is a LIVE book read (what is on the water right now), not
 * a frozen plan fact - re-opening the same figure a minute later should see the book move.
 */
import { useQuery } from '@tanstack/react-query';

import {
  getContainerRequestDrill,
  type ContainerRequestDrill,
  type ContainerRequestDrillKind,
} from '../services/containerRequestDrillService';

export function useContainerRequestDrill(
  supplierId: string | null,
  productId: string | null,
  kind: ContainerRequestDrillKind | null,
) {
  return useQuery<ContainerRequestDrill>({
    queryKey: ['scm', 'container-request', 'drill', supplierId, productId, kind],
    queryFn: () =>
      getContainerRequestDrill(
        supplierId as string,
        productId as string,
        kind as ContainerRequestDrillKind,
      ),
    enabled: Boolean(supplierId && productId && kind),
    staleTime: 15_000,
    retry: 1,
  });
}
