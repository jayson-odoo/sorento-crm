// eslint.config.mjs
import { FlatCompat } from '@eslint/eslintrc';

// Create a FlatCompat instance to support legacy "extends" syntax.
const compat = new FlatCompat({
  baseDirectory: import.meta.dirname,
});

const eslintConfig = [
  ...compat.config({
    extends: ['next/core-web-vitals', 'next/typescript', 'prettier'],
    // Plugins in legacy format must be an array of plugin names.
    plugins: ['react-hooks'],
    rules: {
      // Disable react-in-jsx-scope (not needed in React 17+)
      'react/react-in-jsx-scope': 'off',
      'react/no-unescaped-entities': 'off',
      // React Hooks rules
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@next/next/no-img-element': 'off',
      // Searchable Dropdown Standard (PLAN-searchable-dropdown-standard). Doctrine:
      // every dropdown-select must be searchable and use the standard component
      // (@/components/common/SearchableSelect | SearchableMultiSelect). 'error' so any
      // violation fails CI. The migration is COMPLETE — the whole codebase is on the
      // standard, the burn-down allowlist has been deleted, and ui/select.tsx is gone.
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@/components/ui/select',
              message:
                'Radix Select is not searchable. Use SearchableSelect / SearchableMultiSelect from @/components/common. See documentation/reference/ADR-PRODUCT-STANDARDS.md.',
            },
            {
              name: '@/components/ui/command',
              importNames: ['CommandInput'],
              message:
                'Do not hand-roll a searchable dropdown with CommandInput. Use SearchableSelect / SearchableMultiSelect from @/components/common. (Genuine Cmd+K command palettes are exempt in eslint.config.mjs.)',
            },
          ],
        },
      ],
      // Architecture guards (PLAN-fix-security-cluster Sub-plan E). 'warn' so the
      // ~283 pre-existing sites don't fail `eslint .` (no --max-warnings), while
      // any NEW violation is surfaced in editor/PR/CI. Fix opportunistically.
      'no-restricted-syntax': [
        'warn',
        {
          // Hand-rolled error parsing: response.json().catch(() => ({}))
          selector:
            "CallExpression[callee.property.name='catch'][callee.object.callee.property.name='json']",
          message:
            'Use extractApiError(response, fallback) from @/lib/api-client instead of hand-rolling response.json().catch().',
        },
        {
          // Native confirm() — not allowed per ADR (use a dialog).
          selector: "CallExpression[callee.name='confirm']",
          message:
            'Do not use native confirm(). Use ConfirmDeleteDialog / AlertDialog from @/components/ui.',
        },
        {
          selector:
            "CallExpression[callee.object.name='window'][callee.property.name='confirm']",
          message:
            'Do not use native window.confirm(). Use ConfirmDeleteDialog / AlertDialog from @/components/ui.',
        },
        {
          // Raw native <select> — not searchable. (warn: only advisory; the real gate
          // is the no-restricted-imports ban on @/components/ui/select above.)
          selector: "JSXOpeningElement[name.name='select']",
          message:
            'Native <select> is not searchable. Use SearchableSelect from @/components/common.',
        },
        // NOTE: no rule for `new URLSearchParams` — it has legit non-DataGrid uses
        // (simple query strings) that a blanket AST selector can't distinguish from
        // the buildDataGridParams cases, so it stays a manual/review cleanup (E).
      ],
    },
  }),
  {
    // Permanent exemptions from the dropdown ban:
    // - the standard components themselves (they legitimately wrap Command/CommandInput)
    // - genuine Cmd+K command palettes (a Command menu, NOT a dropdown-select)
    files: [
      'components/common/**',
      'components/ui/**',
      'app/components/partials/dialogs/search/search-dialog.tsx',
    ],
    rules: { 'no-restricted-imports': 'off' },
  },
  {
    ignores: ['.next/**', 'node_modules/**', 'prisma/**'],
  },
];

export default eslintConfig;
