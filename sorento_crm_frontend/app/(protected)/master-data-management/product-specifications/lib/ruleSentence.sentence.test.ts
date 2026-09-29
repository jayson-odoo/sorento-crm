/**
 * Fix round 4, F3 (owner, 27 Sep: "how is this rule explained"): one plain sentence
 * per rule, built from the same parts the rules grid shows. Every kind, the Only
 * when clause, and the end-of-name and skip-after options. Never a snake_case key.
 */
import { describe, it, expect } from 'vitest';
import { ruleSentence } from './ruleSentence';
import type { SpecRegistryKey, SpecRuleBuilder } from '../types/productSpec.types';

const spec = (over: Partial<SpecRegistryKey>) =>
  ({ spec_key: 'finish', label: 'Finish or colour', data_type: 'enum', value_labels: {}, ...over }) as SpecRegistryKey;

const FINISH = spec({});
const BOARD = spec({ spec_key: 'chopping_board', label: 'Chopping board', data_type: 'boolean' });
const LENGTH = spec({ spec_key: 'dim_length', label: 'Length', data_type: 'numeric', unit: 'mm' });
const registry = [FINISH, BOARD, LENGTH];
const lookup = (key: string) => registry.find((k) => k.spec_key === key);

const say = (builder: SpecRuleBuilder, on: SpecRegistryKey = FINISH) => ruleSentence(builder, on, lookup);

describe('ruleSentence - every kind', () => {
  it('Words: the owner example', () => {
    expect(say({ kind: 'words', words: ['BLACK'], value: 'black' })).toBe(
      'When the description or flyer contains the word BLACK, set Finish or colour to Black.',
    );
  });

  it('Words: several words, where to look, end of name and skip after', () => {
    expect(
      say({
        kind: 'words',
        look_in: 'name',
        words: ['BLACK', 'MATT BLACK'],
        at_end: true,
        skip_after: ['NOT'],
        value: 'matt_black',
      }),
    ).toBe(
      'When the product name contains any of the words BLACK or MATT BLACK at the end of the product name, but not right after NOT, set Finish or colour to Matt black.',
    );
  });

  it('Words: a yes-or-no specification is set to Yes', () => {
    expect(say({ kind: 'words', look_in: 'flyer', words: ['CHOPPING BOARD'], value: true }, BOARD)).toBe(
      'When the flyer contains the word CHOPPING BOARD, set Chopping board to Yes.',
    );
  });

  it('Words: with Only when', () => {
    expect(
      say({
        kind: 'words',
        words: ['BLACK'],
        value: 'black',
        only_when: { spec: 'chopping_board', is: true, values: ['true'] },
      }),
    ).toBe(
      'When the description or flyer contains the word BLACK and Chopping board is Yes, set Finish or colour to Black.',
    );
  });

  it('Words: Only when is not, several values, a spec the registry lost', () => {
    expect(
      say({
        kind: 'words',
        words: ['BLACK'],
        value: 'black',
        only_when: { spec: 'basin_shape', is: false, values: ['round', 'square'] },
      }),
    ).toBe(
      'When the description or flyer contains the word BLACK and Basin shape is not Round or Square, set Finish or colour to Black.',
    );
  });

  it('Number: between, written in, ignore below, skip after', () => {
    expect(
      say(
        {
          kind: 'number',
          look_in: 'description',
          after: ['('],
          before: ['MM'],
          written_in: 'centimetres',
          ignore_below: 100,
          skip_after: ['PACK OF'],
        },
        LENGTH,
      ),
    ).toBe(
      'When the description has a number after ( and before MM, but not right after PACK OF, set Length to that number, written in centimetres, ignoring numbers below 100.',
    );
  });

  it('Number: before only', () => {
    expect(say({ kind: 'number', before: ['MM'] }, LENGTH)).toBe(
      'When the description or flyer has a number before MM, set Length to that number.',
    );
  });

  it('Size: a position and a label', () => {
    expect(say({ kind: 'size', pick: 2 }, LENGTH)).toBe(
      'Set Length to the 2nd number of the size in the description or flyer.',
    );
    expect(say({ kind: 'size', pick: 'W' }, LENGTH)).toBe(
      'Set Length to the number labelled W in the size in the description or flyer.',
    );
  });

  it('Code', () => {
    expect(say({ kind: 'code', code_match: 'ends_with', texts: ['-BK', '-MB'], value: 'black' })).toBe(
      'When the product code ends with -BK or -MB, set Finish or colour to Black.',
    );
  });

  it('Product, with Only when', () => {
    expect(
      say(
        {
          kind: 'product',
          fact: 'length',
          only_when: { spec: 'chopping_board', is: true, values: ['false'] },
        },
        LENGTH,
      ),
    ).toBe("When Chopping board is No, set Length to the product's length.");
  });

  it('never prints a snake_case key', () => {
    const text = say({
      kind: 'words',
      words: ['BLACK'],
      value: 'matt_black',
      only_when: { spec: 'basin_shape', is: true, values: ['semi_round'] },
    });
    expect(text).not.toMatch(/[a-z]+_[a-z]+/);
  });
});
