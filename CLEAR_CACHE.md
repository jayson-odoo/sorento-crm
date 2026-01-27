# Clear Next.js Cache

If changes aren't showing up, try these steps:

1. **Stop the dev server** (Ctrl+C)

2. **Clear Next.js cache:**
   ```bash
   cd sorento_crm_frontend
   rm -rf .next
   ```

3. **Clear node_modules cache (optional but recommended):**
   ```bash
   rm -rf node_modules/.cache
   ```

4. **Restart dev server:**
   ```bash
   npm run dev
   ```

5. **Hard refresh browser:**
   - Chrome/Edge: Ctrl+Shift+R (Windows) or Cmd+Shift+R (Mac)
   - Firefox: Ctrl+F5 (Windows) or Cmd+Shift+R (Mac)
   - Safari: Cmd+Option+R

6. **Check browser console** for any errors
