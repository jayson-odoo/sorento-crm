import { describe, expect, it } from 'vitest';
import type {
  QuotationDocument,
  QuotationIssue,
} from '../services/quotationDocumentService';
import {
  pickMobile,
  quotationNumberLabel,
  toWaDigits,
  whatsAppMessage,
} from './quotationWhatsApp';

describe('toWaDigits', () => {
  it('turns a MY local mobile into 60...', () => {
    expect(toWaDigits('012-000 0001')).toBe('60120000001');
  });
  it('keeps a +60 number as 60...', () => {
    expect(toWaDigits('+60 12-000 0001')).toBe('60120000001');
    expect(toWaDigits('60 12-000 0001')).toBe('60120000001');
  });
  it('drops spaces, dashes, brackets and plus', () => {
    expect(toWaDigits('(+60) 12-000 0001')).toBe('60120000001');
  });
  it('keeps another country code, dropping the 00 prefix', () => {
    expect(toWaDigits('0065 0000 0001')).toBe('6500000001');
    expect(toWaDigits('+65 0000 0001')).toBe('6500000001');
  });
});

describe('toWaDigits typed numbers (AC-C5)', () => {
  it('reads +60 with a leading 0 as 60...', () => {
    expect(toWaDigits('+60 012-000 0001')).toBe('60120000001');
  });
  it('reads a mobile typed without the trunk 0 as Malaysian', () => {
    expect(toWaDigits('12-000 0001')).toBe('60120000001');
    expect(toWaDigits('11-0000 0001')).toBe('601100000001');
  });
});

describe('pickMobile', () => {
  it('returns wa digits for a mobile, local or international', () => {
    expect(pickMobile('012-000 0001')).toBe('60120000001');
    expect(pickMobile('+60 12-000 0001')).toBe('60120000001');
  });
  it('keeps a foreign number written with + or 00', () => {
    expect(pickMobile('+65 0000 0001')).toBe('6500000001');
    expect(pickMobile('0065 0000 0001')).toBe('6500000001');
  });
  it('leaves a MY landline empty', () => {
    expect(pickMobile('03-0000 0001')).toBe('');
    expect(pickMobile('+603-0000 0001')).toBe('');
  });
  it('picks the mobile from a multi-line field', () => {
    expect(pickMobile('03-0000 0001\n012-000 0001')).toBe('60120000001');
  });
  it('picks the first mobile of a slash list', () => {
    expect(pickMobile('012-000 0001 / 013-000 0002')).toBe('60120000001');
  });
  it('splits on comma and semicolon', () => {
    expect(pickMobile('03-0000 0001, 013-000 0002')).toBe('60130000002');
    expect(pickMobile('03-0000 0001; 013-000 0002')).toBe('60130000002');
  });
  it('gives empty for a field with no mobile', () => {
    expect(pickMobile('91-00-00000001/2/3/4')).toBe('');
  });
  it('gives empty for empty, null, undefined and whitespace', () => {
    expect(pickMobile('')).toBe('');
    expect(pickMobile(null)).toBe('');
    expect(pickMobile(undefined)).toBe('');
    expect(pickMobile('   ')).toBe('');
  });
});

describe('quotationNumberLabel', () => {
  const doc = { document_no: 'PRJQ-2026-0003' } as QuotationDocument;
  it('uses the printed ref when set', () => {
    const issue = { issue_no: 1, our_ref_text: 'PRJQ-2026-0003 (R1)' } as QuotationIssue;
    expect(quotationNumberLabel(doc, issue)).toBe('PRJQ-2026-0003 (R1)');
  });
  it('falls back to document_no and revision', () => {
    const issue = { issue_no: 2, our_ref_text: null } as QuotationIssue;
    expect(quotationNumberLabel(doc, issue)).toBe('PRJQ-2026-0003 (R2)');
  });
});

describe('whatsAppMessage', () => {
  const base = {
    attn: 'ATTN A',
    numberLabel: 'PRJQ-2026-0003 (R1)',
    subject: 'SUBJECT A',
    link: 'https://crm.example.test/quotation-sign/tok',
    signatory: 'SALES REP A',
  };

  it('is byte-exact for the full message', () => {
    expect(whatsAppMessage(base)).toBe(
      [
        'Hi ATTN A,',
        '',
        'Here is our quotation PRJQ-2026-0003 (R1) for SUBJECT A.',
        'You can view and accept it here:',
        'https://crm.example.test/quotation-sign/tok',
        '',
        'Thank you,',
        'SALES REP A',
      ].join('\n'),
    );
  });

  it('says "Hi," with no attn, blank counted as missing', () => {
    expect(whatsAppMessage({ ...base, attn: null }).split('\n')[0]).toBe('Hi,');
    expect(whatsAppMessage({ ...base, attn: '   ' }).split('\n')[0]).toBe('Hi,');
  });

  it('leaves out " for <subject>" with no subject', () => {
    const lines = whatsAppMessage({ ...base, subject: '  ' }).split('\n');
    expect(lines[2]).toBe('Here is our quotation PRJQ-2026-0003 (R1).');
  });

  it('ends at "Thank you," with no signatory', () => {
    const text = whatsAppMessage({ ...base, signatory: null });
    expect(text.endsWith('Thank you,')).toBe(true);
    expect(whatsAppMessage({ ...base, signatory: ' ' }).endsWith('Thank you,')).toBe(true);
  });
});
