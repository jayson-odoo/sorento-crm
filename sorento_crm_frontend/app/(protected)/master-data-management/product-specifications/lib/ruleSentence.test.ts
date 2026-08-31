import { describe, expect, it } from 'vitest';
import { plainPattern, ruleSentence } from './ruleSentence';

describe('reading a regular expression as words', () => {
  it('undoes the constructs the shipped rules use', () => {
    expect(plainPattern('\\bSINGLE\\s+BOWLS?\\b')).toBe('SINGLE BOWL(S)');
    expect(plainPattern('\\bRIMLESS\\b')).toBe('RIMLESS');
  });

  it('gives up rather than mistranslating', () => {
    // Alternation and lookaround are genuinely for someone who writes regexes. A
    // confident-sounding wrong reading of a live rule is worse than showing the source.
    expect(plainPattern('(?<!\\d)(\\d)\\s*BOWLS?\\b')).toBeNull();
    expect(plainPattern('\\b(WALL|FLOOR) MOUNTED\\b')).toBeNull();
  });
});

describe('a rule as a sentence', () => {
  it('states the condition and the answer', () => {
    expect(
      ruleSentence(
        { match: 'contains', pattern: 'S/STEEL 304', value: '304' },
        'Steel grade',
      ),
    ).toBe(
      'If the description or flyer contains “S/STEEL 304”, Steel grade is 304.',
    );
  });

  it('names the flyer when the rule is scoped to it', () => {
    expect(
      ruleSentence(
        { match: 'contains', pattern: 'L680X', value: 680, source: 'flyer' },
        'Length',
      ),
    ).toContain('the flyer card');
  });

  it('reads a flag as yes', () => {
    expect(
      ruleSentence(
        { match: 'present', pattern: '\\bRIMLESS\\b', value: true },
        'Rimless',
      ),
    ).toBe(
      'If “RIMLESS” appears in the description or flyer at all, Rimless is yes.',
    );
  });

  it('explains a field read, which has no pattern to show', () => {
    expect(
      ruleSentence({ match: 'from_field', pattern: 'brand' }, 'Brand'),
    ).toBe("From the product's brand field.");
    expect(
      ruleSentence(
        { match: 'from_field', pattern: 'column:dimensions_length' },
        'Length',
      ),
    ).toBe("From the product's `dimensions_length` column.");
  });

  it('explains a name-head read', () => {
    expect(
      ruleSentence({ match: 'name_head', pattern: 'class_tail' }, 'Class'),
    ).toBe('Class comes from the product name head.');
  });
});

describe('a pattern rule does two different jobs', () => {
  it('reads a number out of the text when it captures one', () => {
    expect(
      ruleSentence(
        { match: 'regex', pattern: '(\\d+)MM S-TRAP', capture: 1 },
        'Trap outlet length',
      ),
    ).toContain('Read Trap outlet length out of');
  });

  it('states the answer when the rule carries one', () => {
    // bowl_count's word forms are regex rules with a value, not captures. Describing
    // them as "read the number out of SINGLE BOWL(S)" names something that never happens.
    expect(
      ruleSentence(
        { match: 'regex', pattern: '\\bSINGLE\\s+BOWLS?\\b', value: 1 },
        'Number of bowls',
      ),
    ).toBe(
      'If the description or flyer matches “SINGLE BOWL(S)”, Number of bowls is 1.',
    );
  });
});
