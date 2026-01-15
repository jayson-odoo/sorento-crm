import { NextRequest } from 'next/server';
import { getSession } from 'next-auth/react';

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
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
  const basePath = process.env.NEXT_PUBLIC_BASE_PATH || '';

  // If input is a string and is a relative API path
  if (typeof input === 'string') {
    if (input.startsWith('/api/')) {
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
        '/api/user-management/users',
        '/api/user-management/roles',
        '/api/user-management/permissions',
        '/api/user-management/access-agents',
      ];

      const isBusinessApi = businessApiRoutes.some(route => input.startsWith(route));

      if (isBusinessApi) {
        // Route to FastAPI backend
        // Convert /api/master-data/products to /api/v1/master-data/products
        if (input.startsWith('/api/master-data/')) {
          url = `${apiUrl}/api/v1/master-data${input.replace('/api/master-data', '')}`;
        } else if (input.startsWith('/api/order-management/')) {
          url = `${apiUrl}/api/v1/order-management${input.replace('/api/order-management', '')}`;
        } else if (input.startsWith('/api/inventory/')) {
          url = `${apiUrl}/api/v1/inventory${input.replace('/api/inventory', '')}`;
        } else if (input.startsWith('/api/procurement/')) {
          url = `${apiUrl}/api/v1/procurement${input.replace('/api/procurement', '')}`;
        } else if (input.startsWith('/api/marketing/')) {
          url = `${apiUrl}/api/v1/marketing${input.replace('/api/marketing', '')}`;
        } else if (input.startsWith('/api/forms-management/')) {
          url = `${apiUrl}/api/v1/forms-management${input.replace('/api/forms-management', '')}`;
        } else if (input.startsWith('/api/complaint-management/')) {
          url = `${apiUrl}/api/v1/complaint-management${input.replace('/api/complaint-management', '')}`;
        } else if (input.startsWith('/api/sla-management/')) {
          url = `${apiUrl}/api/v1/sla-management${input.replace('/api/sla-management', '')}`;
        } else if (input.startsWith('/api/resource-management/')) {
          url = `${apiUrl}/api/v1/resource-management${input.replace('/api/resource-management', '')}`;
        } else if (input.startsWith('/api/user-management/')) {
          url = `${apiUrl}/api/v1/user-management${input.replace('/api/user-management', '')}`;
        } else if (input.startsWith('/api/v1/')) {
          // Already using v1 path - route directly to FastAPI
          url = `${apiUrl}${input}`;
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
