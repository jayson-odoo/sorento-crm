import { SharedArray } from 'k6/data';

// Pre-seeded resource IDs / tokens loaded from JSON fixtures.
// Each fixture is a JSON array of strings or objects.

export const orderIds = new SharedArray('orderIds', () => {
  try {
    return JSON.parse(open('../fixtures/order_ids.json'));
  } catch (_) {
    return [];
  }
});

export const contactIds = new SharedArray('contactIds', () => {
  try {
    return JSON.parse(open('../fixtures/contact_ids.json'));
  } catch (_) {
    return [];
  }
});

export const stockInquiryReviseTokens = new SharedArray('stockInquiryReviseTokens', () => {
  try {
    return JSON.parse(open('../fixtures/stock_inquiry_revise_tokens.json'));
  } catch (_) {
    return [];
  }
});

export function pick(arr) {
  if (!arr || arr.length === 0) return null;
  return arr[Math.floor(Math.random() * arr.length)];
}

export function unique(prefix = 'LOADTEST') {
  return `${prefix}-${__VU}-${__ITER}-${Date.now()}`;
}
