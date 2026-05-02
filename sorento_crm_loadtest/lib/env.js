const TARGET = (__ENV.TARGET || 'local').toLowerCase();

const targets = {
  local: {
    be: __ENV.BE_LOCAL_URL || 'http://localhost:8000',
    fe: __ENV.FE_LOCAL_URL || 'http://localhost:3000',
  },
  staging: {
    be: __ENV.BE_STAGING_URL || '',
    fe: __ENV.FE_STAGING_URL || '',
  },
  prod: {
    be: __ENV.BE_PROD_URL || '',
    fe: __ENV.FE_PROD_URL || 'https://fe-sorento.foundryx.my',
  },
};

const t = targets[TARGET];
if (!t) {
  throw new Error(`unknown TARGET=${TARGET}; expected local|staging|prod`);
}

export const target = TARGET;
export const beUrl = t.be;
export const feUrl = t.fe;

export const externalApiKey = __ENV.EXTERNAL_API_KEY || '';

export const n8n = {
  stockInquiryReviseUrl: __ENV.N8N_LOADTEST_STOCK_INQUIRY_REVISE_URL || '',
  attachmentUrl: __ENV.N8N_LOADTEST_ATTACHMENT_URL || '',
  crmChatOutboundUrl: __ENV.N8N_LOADTEST_CRM_CHAT_OUTBOUND_URL || '',
};

export function requireBeUrl() {
  if (!beUrl) {
    throw new Error(`BE URL missing for TARGET=${TARGET}; set BE_${TARGET.toUpperCase()}_URL in .env`);
  }
  return beUrl;
}

export function requireFeUrl() {
  if (!feUrl) {
    throw new Error(`FE URL missing for TARGET=${TARGET}; set FE_${TARGET.toUpperCase()}_URL in .env`);
  }
  return feUrl;
}

export function requireN8nUrl(key) {
  const url = n8n[key];
  if (!url) {
    throw new Error(`n8n URL missing: set N8N_LOADTEST_${key.replace(/[A-Z]/g, c => '_' + c).toUpperCase()}_URL in .env`);
  }
  if (url.includes('automate-sorento.foundryx.my')) {
    const isClone = (__ENV.N8N_ALLOW_PROD_URL || '').toLowerCase() === 'true';
    if (!isClone) {
      throw new Error(`refusing to hit production n8n host. Use a [LOADTEST] cloned workflow URL, or set N8N_ALLOW_PROD_URL=true to override.`);
    }
  }
  return url;
}
