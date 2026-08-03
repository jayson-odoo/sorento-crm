/**
 * Mapping one AI-extract response onto the lodge form.
 *
 * This map is where an extraction that read the paper perfectly can still end up wrong on
 * screen, so every line of it is asserted.
 *
 * Three of these are the same rule wearing different clothes: **extraction reads, it does
 * not decide.** It reads a shop NAME, and `POST /lodge/resolve` decides whether that name
 * is a dealer. It reads a model CODE, and the server decides which Kind and whether any
 * single variant matches. Letting the map decide instead would put a guess in the field a
 * consumer reads as fact - and the S3-pre spike found three receipts whose nearest dealer
 * was real and WRONG, and base codes that match three variants apiece.
 */
import { describe, expect, it } from 'vitest';

import { mapExtractToLodge } from './lodgeBackend';
import type { AIExtractResult } from '../../lib/portal-client';

function result(overrides: Partial<AIExtractResult> = {}): AIExtractResult {
  return {
    values: {},
    products: [],
    per_field: {},
    usage: { prompt_tokens: 0, completion_tokens: 0, total_tokens: 0 },
    ...overrides,
  } as AIExtractResult;
}

describe('mapExtractToLodge', () => {
  it('carries the shop name through verbatim, branch and all', () => {
    // The resolver strips branch qualifiers itself, on both sides, and that rule lifted
    // exact resolution from 23 to 26 of 38. Cleaning them up here would hide it.
    const mapped = mapExtractToLodge(
      result({ values: { shop_name: 'DiLOOMA SDN. BHD. (JLN IPOH BRANCH)' } }),
    );
    expect(mapped.shop_name_raw).toBe('DiLOOMA SDN. BHD. (JLN IPOH BRANCH)');
  });

  it('never states a dealer, whatever the shop name says', () => {
    // Extraction reads a name. `POST /lodge/resolve` decides if it is a dealer, and only
    // `resolved` is ever shown as one.
    const mapped = mapExtractToLodge(result({ values: { shop_name: 'TOTAL HOME DIY SDN BHD' } }));
    expect(mapped.dealer.state).toBe('unmatched');
    expect(mapped.dealer.customer_name).toBeNull();
  });

  it('keeps the dealer document number and never promotes it to an order number', () => {
    // AC-C12. Six dealer numbers, six no-matches against `orders`. They live in different
    // fields because they are different things.
    const mapped = mapExtractToLodge(
      result({ values: { dealer_document_number: 'KCS-2112-0054' } }),
    );
    expect(mapped.document_number).toBe('KCS-2112-0054');
    expect(mapped.sorento_order_number).toBeNull();
  });

  it('keeps a quoted Sorento order number separately', () => {
    // AC-C13. `202604-0348` matches exactly one order, which is the whole dealer track.
    const mapped = mapExtractToLodge(
      result({ values: { sorento_order_number: '202604-0348' } }),
    );
    expect(mapped.sorento_order_number).toBe('202604-0348');
  });

  it('leaves the product unresolved even when a code was read', () => {
    // AC-C17. `SRTWC8152` matches three real variants; picking one here would put another
    // part's warranty term on the line.
    const mapped = mapExtractToLodge(
      result({ products: [{ product_code: 'SRTWC8152', product_name: 'WATER CLOSET' }] as never }),
    );
    expect(mapped.lines[0].product_id).toBeNull();
    expect(mapped.lines[0].kind_code).toBeNull();
    expect(mapped.lines[0].model_code_raw).toBe('SRTWC8152');
  });

  it('builds the claimed text from what was actually printed', () => {
    // The only thing a CS agent can act on when the code resolves to nothing, which is
    // the ordinary outcome.
    const mapped = mapExtractToLodge(
      result({ products: [{ product_code: 'SRTWC8152', product_name: 'WATER CLOSET' }] as never }),
    );
    expect(mapped.lines[0].claimed_text).toBe('SRTWC8152 WATER CLOSET');
  });

  it('survives a line with a name and no code', () => {
    // A till receipt often prints a description and no model number at all.
    const mapped = mapExtractToLodge(
      result({ products: [{ product_name: 'TAP SET' }] as never }),
    );
    expect(mapped.lines[0].claimed_text).toBe('TAP SET');
    expect(mapped.lines[0].model_code_raw).toBeNull();
  });

  it('defaults a missing or nonsense quantity to one', () => {
    // A zero would tell the ledger the consumer bought nothing, and a blank breaks the
    // line. One is the honest reading of a receipt that did not say.
    for (const quantity of [undefined, 0, -3]) {
      const mapped = mapExtractToLodge(
        result({ products: [{ product_code: 'X1', quantity }] as never }),
      );
      expect(mapped.lines[0].quantity).toBe(1);
    }
  });

  it('turns blank strings into null rather than empty fields', () => {
    // An empty string reaching the form makes "we could not read much from that photo"
    // impossible to detect, and the confirm step then asks a consumer to agree with a
    // sentence that has nothing in it.
    const mapped = mapExtractToLodge(
      result({ values: { shop_name: '   ', purchase_date: '' } }),
    );
    expect(mapped.shop_name_raw).toBeNull();
    expect(mapped.purchase_date).toBeNull();
  });

  it('maps an empty extraction to an empty-but-valid form', () => {
    // 24% of receipts. Not an error path - the ordinary imperfect case.
    const mapped = mapExtractToLodge(result());
    expect(mapped.lines).toEqual([]);
    expect(mapped.shop_name_raw).toBeNull();
    expect(mapped.dealer.state).toBe('unmatched');
  });
});
