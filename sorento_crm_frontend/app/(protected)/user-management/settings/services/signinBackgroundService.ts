import { apiFetch } from '@/lib/api';
import { extractApiError } from '@/lib/api-client';

/**
 * The sign-in background image.
 *
 * Contract, matching `POST /api/v1/user-management/settings/signin-background`:
 *
 *   multipart form: backgroundAction = "save" | "remove", backgroundFile = the image
 *   -> { signin_background_url: string | null }
 *
 * It is its own endpoint rather than a field on the general settings save because the column
 * holds a URL the sign-in page loads for anonymous visitors: the bytes come through us or they
 * do not go in, so there is no string field a client could set. The response is the signed URL
 * to preview, or null once removed.
 */

const PATH = '/api/user-management/settings/signin-background';

/** Matches the ceiling and the allow-list the route enforces; the UI is the courtesy copy. */
export const SIGNIN_BACKGROUND_MAX_MB = 5;
/** Extensions, because that is what `FileDropzone` matches on. */
export const SIGNIN_BACKGROUND_ACCEPT = '.jpg,.jpeg,.png,.webp';

async function post(form: FormData): Promise<string | null> {
  const response = await apiFetch(PATH, { method: 'POST', body: form });
  if (!response.ok) {
    throw new Error(
      await extractApiError(
        response,
        'Could not update the sign-in background',
      ),
    );
  }
  const data = (await response.json()) as {
    signin_background_url?: string | null;
  };
  return data?.signin_background_url ?? null;
}

export async function uploadSigninBackground(
  file: File,
): Promise<string | null> {
  const form = new FormData();
  form.append('backgroundAction', 'save');
  form.append('backgroundFile', file);
  return post(form);
}

export async function removeSigninBackground(): Promise<string | null> {
  const form = new FormData();
  form.append('backgroundAction', 'remove');
  return post(form);
}
