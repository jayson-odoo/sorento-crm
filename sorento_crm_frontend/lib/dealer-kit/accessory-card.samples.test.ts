/** B review: the designer's sample accessories fill the spec sheet card fields too. */
import { describe, expect, it } from 'vitest';

import { accessoryDesignSamples, cardElementsFor, defaultSpecSheetCard } from './accessory-card';

describe('accessoryDesignSamples', () => {
  it('carry a brand, a description, a spec sheet description and dimensions', () => {
    for (const sample of accessoryDesignSamples()) {
      expect(sample.brand).toBeTruthy();
      expect(sample.description).toBeTruthy();
      expect(sample.spec_sheet_description).toBeTruthy();
      expect(sample.dimensions).toBeTruthy();
    }
  });

  it('preview the default spec sheet card fully: brand and code, then the description', () => {
    const texts = cardElementsFor(accessoryDesignSamples()[0], defaultSpecSheetCard())
      .filter((e) => e.kind === 'text')
      .map((e) => e.text);
    expect(texts[0]).toMatch(/\S+ CODE/);
    expect(texts[1]).toBeTruthy();
  });
});
