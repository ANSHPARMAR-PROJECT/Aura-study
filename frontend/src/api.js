let csrfToken = '';
export const setCsrfToken = (token) => { csrfToken = token || ''; };

export async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = { ...(options.headers || {}) };
  let body = options.body;
  if (body && !(body instanceof FormData) && typeof body !== 'string') {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(body);
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && csrfToken) {
    headers['X-CSRF-Token'] = csrfToken;
  }
  const response = await fetch(path, { ...options, method, headers, body, credentials: 'same-origin' });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    const error = new Error(payload?.error || `Request failed (${response.status})`);
    error.status = response.status;
    throw error;
  }
  return payload;
}
