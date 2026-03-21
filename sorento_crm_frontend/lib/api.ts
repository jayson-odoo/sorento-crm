import { NextRequest } from 'next/server';

/**
 * apiFetch - universal fetch for dev/prod that prefixes API calls with the correct base URL
 * Routes business logic APIs to FastAPI backend, keeps auth routes in Next.js
 *
 * Usage:
 *   apiFetch('/api/v1/master-data/products', { method: 'GET' })
 *   apiFetch('/api/auth/login', { method: 'POST' }) // stays in Next.js
 */
export async function apiFetch(
  input: string | Request,
  init?: RequestInit,
): Promise<Response> {
  let url = input;
  // Use empty string for relative paths (nginx will proxy), or explicit URL for direct backend access
  let apiUrl = process.env.NEXT_PUBLIC_API_URL || '';
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

  // Always check and sanitize apiUrl to prevent HTTP URLs in production
  // If apiUrl is HTTP and we're not in localhost development, clear it
  if (apiUrl && apiUrl.startsWith('http://')) {
    // Only allow HTTP URLs on localhost for development
    // In production (any HTTPS or non-localhost), force relative paths
    if (typeof window !== 'undefined') {
      const isLocalhost = 
        window.location.hostname === 'localhost' || 
        window.location.hostname === '127.0.0.1' ||
        window.location.hostname.startsWith('192.168.') ||
        window.location.hostname.startsWith('10.') ||
        window.location.hostname.startsWith('172.');
      
      const isProduction = 
        window.location.protocol === 'https:' || 
        (!isLocalhost && window.location.hostname.includes('.'));
      
      // If HTTP URL but we're in production, clear it to force relative paths
      if (isProduction || !isLocalhost) {
        apiUrl = '';
      }
    } else {
      // Server-side: if it's an HTTP URL, clear it (will use relative paths)
      // Server-side should use relative paths and let nginx proxy handle it
      apiUrl = '';
    }
  }

  // In browser (client-side), always use relative paths to avoid mixed content issues
  // The nginx reverse proxy will handle routing to the backend
  // Only use explicit API URL for local development when explicitly set
  if (typeof window !== 'undefined') {
    // Check if we're accessing via localhost (development)
    const isLocalhost = 
      window.location.hostname === 'localhost' || 
      window.location.hostname === '127.0.0.1' ||
      window.location.hostname.startsWith('192.168.') ||
      window.location.hostname.startsWith('10.') ||
      window.location.hostname.startsWith('172.');
    
    // Check if we're in production (HTTPS or non-localhost domain)
    const isProduction = 
      window.location.protocol === 'https:' || 
      (!isLocalhost && window.location.hostname.includes('.'));
    
    // Check if we're in development mode (HTTP on localhost)
    const isDevelopment = isLocalhost && window.location.protocol === 'http:';
    
    // In production, ALWAYS use relative paths regardless of NEXT_PUBLIC_API_URL
    // This ensures HTTPS pages always use HTTPS requests (no mixed content)
    // Nginx reverse proxy will handle routing to the backend
    if (isProduction) {
      apiUrl = '';
    } else if (isDevelopment && !apiUrl) {
      // Development without explicit API URL: use relative paths (Next.js rewrites will handle it)
      apiUrl = '';
    }
    // If apiUrl is explicitly set in development and we're on localhost HTTP, use it (e.g., http://localhost:8000)
  }

  // If input is a string and is a relative API path
  if (typeof input === 'string') {
      if (input.startsWith('/api/')) {
        // Routes that should stay in Next.js (not routed to FastAPI backend).
        // Keep this list explicit to avoid catching similarly named FastAPI routes.
        const nextJsOnlyPrefixes = [
          '/api/user-management/contact-access-agents',
        ];
        const isNextJsRoute =
          nextJsOnlyPrefixes.some((prefix) => input.startsWith(prefix)) ||
          /^\/api\/user-management\/access-agents\/[^/]+\/contact-access(?:\/|$)/.test(input);

        // Route business logic APIs to FastAPI backend
        const businessApiRoutes = [
          '/api/v1/',
          '/api/master-data/',
          '/api/order-management/',
          '/api/inventory/',
          '/api/procurement/',
          '/api/marketing/',
          '/api/forms-management/',
          '/api/complaint-management/',
          '/api/sla-management/',
          '/api/resource-management/',
          '/api/user-management/',
        ];

        const isBusinessApi = !isNextJsRoute && businessApiRoutes.some(route => input.startsWith(route));

      if (isBusinessApi) {
        // Route to FastAPI backend using relative paths
        // All URLs will be relative to avoid mixed content issues
        if (input.startsWith('/api/master-data/')) {
          url = `/api/v1/master-data${input.replace('/api/master-data', '')}`;
        } else if (input.startsWith('/api/order-management/')) {
          url = `/api/v1/order-management${input.replace('/api/order-management', '')}`;
        } else if (input.startsWith('/api/inventory/')) {
          url = `/api/v1/inventory${input.replace('/api/inventory', '')}`;
        } else if (input.startsWith('/api/procurement/')) {
          url = `/api/v1/procurement${input.replace('/api/procurement', '')}`;
        } else if (input.startsWith('/api/marketing/')) {
          url = `/api/v1/marketing${input.replace('/api/marketing', '')}`;
        } else if (input.startsWith('/api/forms-management/')) {
          url = `/api/v1/forms-management${input.replace('/api/forms-management', '')}`;
        } else if (input.startsWith('/api/complaint-management/')) {
          url = `/api/v1/complaint-management${input.replace('/api/complaint-management', '')}`;
        } else if (input.startsWith('/api/sla-management/')) {
          // Route all SLA management (including tiers) to FastAPI backend
          url = `/api/v1/sla-management${input.replace('/api/sla-management', '')}`;
        } else if (input.startsWith('/api/resource-management/')) {
          url = `/api/v1/resource-management${input.replace('/api/resource-management', '')}`;
        } else if (input.startsWith('/api/user-management/')) {
          url = `/api/v1/user-management${input.replace('/api/user-management', '')}`;
        } else if (input.startsWith('/api/v1/')) {
          // Already using v1 path - use as-is (relative)
          url = input;
        }

        // Prepend apiUrl to business API routes if set (for local development ONLY)
        // NEVER prepend HTTP URLs in production - always use relative paths
        // Prepend apiUrl ONLY in local development
        // In production with HTTPS, ALWAYS use relative paths (nginx handles proxying)
        if (apiUrl && typeof url === 'string' && url.startsWith('/api/v1/')) {
          const isHttpUrl = apiUrl.startsWith('http://');
          const isHttpsUrl = apiUrl.startsWith('https://');
          const isLocalhost = typeof window !== 'undefined' && (
            window.location.hostname === 'localhost' || 
            window.location.hostname === '127.0.0.1'
          );
          const isProductionHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
          
          // NEVER prepend URLs in production HTTPS - always use relative paths
          if (isProductionHttps) {
            // Force relative path in production to avoid mixed content
            url = url; // Keep as-is (relative path like /api/v1/...)
          } else if (isHttpUrl && !isLocalhost) {
            // HTTP URL but not localhost = production HTTP, use relative path
            url = url;
          } else if (apiUrl && (isLocalhost || isHttpsUrl)) {
            // Safe to prepend: either localhost or HTTPS URL
            const baseUrl = apiUrl.replace(/\/$/, '');
            url = `${baseUrl}${url}`;
          }
          // else: leave url as relative path
        }

        // Extract JWT token from NextAuth and send in Authorization header
        // NextAuth stores JWT encrypted in cookies, so we need to get the raw token
        if (typeof window !== 'undefined') {
          try {
            // For client-side: fetch the raw JWT token from Next.js API
            const tokenResponse = await fetch(`${basePath}/api/auth/token`, {
              credentials: 'include',
            });
            
            if (tokenResponse.ok) {
              const data = await tokenResponse.json();
              const token = data?.token;
              
              if (token) {
                console.debug('JWT token extracted successfully');
                // Don't set Content-Type for FormData - browser needs to set it with boundary
                const isFormData = init?.body instanceof FormData;
                
                if (isFormData) {
                  // For FormData, we MUST NOT set Content-Type header
                  // Browser will automatically set it with boundary when it sees FormData body
                  // However, we can still add other headers like Authorization
                  console.debug('FormData detected - preserving browser Content-Type handling');
                  
                  const currentInit = init || {};
                  
                  // Create a new Headers object (don't copy Content-Type if it exists)
                  const headers = new Headers();
                  
                  // Only copy non-Content-Type headers from existing init
                  if (currentInit.headers) {
                    if (currentInit.headers instanceof Headers) {
                      currentInit.headers.forEach((value, key) => {
                        // Explicitly skip Content-Type - browser must set it
                        if (key.toLowerCase() !== 'content-type') {
                          headers.set(key, value);
                        }
                      });
                    } else if (Array.isArray(currentInit.headers)) {
                      currentInit.headers.forEach(([key, value]) => {
                        if (key.toLowerCase() !== 'content-type') {
                          headers.set(key, value);
                        }
                      });
                    } else {
                      // Plain object
                      Object.entries(currentInit.headers as Record<string, string>).forEach(([key, value]) => {
                        if (key.toLowerCase() !== 'content-type') {
                          headers.set(key, value);
                        }
                      });
                    }
                  }
                  
                  // Add Authorization header
                  headers.set('Authorization', `Bearer ${token}`);
                  
                  // Important: Don't set Content-Type - let browser handle it
                  // When fetch sees FormData body, it will automatically set:
                  // Content-Type: multipart/form-data; boundary=...
                  
                  init = {
                    ...currentInit,
                    credentials: 'include' as RequestCredentials,
                    headers: headers, // Headers object without Content-Type
                  };
                  
                  console.debug('FormData request prepared - Content-Type will be set by browser');
                } else {
                  // For non-FormData, convert headers to plain object
                  const existingHeaders: Record<string, string> = {};
                  if (init?.headers) {
                    if (init.headers instanceof Headers) {
                      init.headers.forEach((value, key) => {
                        existingHeaders[key] = value;
                      });
                    } else if (Array.isArray(init.headers)) {
                      init.headers.forEach(([key, value]) => {
                        existingHeaders[key] = value;
                      });
                    } else {
                      Object.assign(existingHeaders, init.headers);
                    }
                  }
                  
                  const headers: Record<string, string> = {
                    ...existingHeaders,
                    'Authorization': `Bearer ${token}`,
                  };
                  if (!headers['Content-Type'] && !headers['content-type']) {
                    headers['Content-Type'] = 'application/json';
                  }
                  init = {
                    ...init,
                    credentials: 'include' as RequestCredentials,
                    headers,
                  };
                }
              } else {
                console.warn('Token endpoint returned no token', data);
                // Fallback: send cookies if token extraction fails
                const isFormData = init?.body instanceof FormData;
                const headers: Record<string, string> = {
                  ...(init?.headers as Record<string, string>),
                };
                if (!isFormData && !headers['Content-Type']) {
                  headers['Content-Type'] = 'application/json';
                }
                init = {
                  ...init,
                  credentials: 'include' as RequestCredentials,
                  headers,
                };
              }
            } else {
              const errorData = await tokenResponse.json().catch(() => ({}));
              console.warn('Token endpoint failed', tokenResponse.status, errorData);
              // Fallback: send cookies if token endpoint fails
              const isFormData = init?.body instanceof FormData;
              const headers: Record<string, string> = {
                ...(init?.headers as Record<string, string>),
              };
              if (!isFormData && !headers['Content-Type']) {
                headers['Content-Type'] = 'application/json';
              }
              init = {
                ...init,
                credentials: 'include' as RequestCredentials,
                headers,
              };
            }
          } catch (e) {
            console.error('Failed to get token for API call', e);
            // Fallback: send cookies
            const isFormData = init?.body instanceof FormData;
            const headers: Record<string, string> = {
              ...(init?.headers as Record<string, string>),
            };
            if (!isFormData && !headers['Content-Type']) {
              headers['Content-Type'] = 'application/json';
            }
            init = {
              ...init,
              credentials: 'include' as RequestCredentials,
              headers,
            };
          }
        } else {
          // Server-side: cookies will be forwarded automatically
          const isFormData = init?.body instanceof FormData;
          const headers: Record<string, string> = {
            ...(init?.headers as Record<string, string>),
          };
          if (!isFormData && !headers['Content-Type']) {
            headers['Content-Type'] = 'application/json';
          }
          init = {
            ...init,
            credentials: 'include' as RequestCredentials,
            headers,
          };
        }
      } else {
        // Keep auth and account routes in Next.js
        url = basePath + (input.startsWith('/') ? input : '/' + input);
      }
    }
  }

  return fetch(url as RequestInfo, init);
}

export function getClientIP(request: NextRequest): string {
  return (
    request.headers.get('x-forwarded-for') ||
    request.headers.get('x-real-ip') ||
    //|| request.socket.remoteAddress
    'unknown'
  );
}
