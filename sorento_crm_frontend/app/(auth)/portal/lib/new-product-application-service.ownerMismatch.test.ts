/**
 * NPA-FROM-SI crew pass: opening another contact's application answers the SI portal's 403
 * OWNER_MISMATCH, and the service surfaces it as the SI's typed error, so the form shows the
 * owner's verify card (shared `portalSessionRedirectPath`), not "Application not found".
 */
import { describe, expect, it } from 'vitest';
import { makeNewProductApplicationService } from './new-product-application-service';
import { PortalOwnerMismatchError } from './portal-client';

const json = (b: unknown, status: number) =>
  new Response(JSON.stringify(b), { status, headers: { 'content-type': 'application/json' } });

describe('getNewProductApplication', () => {
  it("a 403 OWNER_MISMATCH is the SI portal's PortalOwnerMismatchError", async () => {
    const svc = makeNewProductApplicationService((async () =>
      json(
        { message: 'This new product application belongs to another contact.', code: 'OWNER_MISMATCH' },
        403,
      )) as never);
    await expect(svc.getNewProductApplication('npa-1')).rejects.toBeInstanceOf(PortalOwnerMismatchError);
  });

  it('a 404 stays an ordinary error (the not-found state)', async () => {
    const svc = makeNewProductApplicationService((async () =>
      json({ message: 'New product application not found.', code: 'NOT_FOUND' }, 404)) as never);
    const err = await svc.getNewProductApplication('npa-1').catch((e: unknown) => e);
    expect(err).not.toBeInstanceOf(PortalOwnerMismatchError);
    expect(err).toBeInstanceOf(Error);
  });
});
