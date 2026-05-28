import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
// eslint-plugin-jsx-a11y exposes a flat-config variant. Catches missing alt
// text, click handlers without keyboard handlers, role mis-use, etc. — see
// audit F-MAJ-12. The plugin declares peer ESLint up to ^9 but the flat
// API is unchanged in ESLint 10; install with --legacy-peer-deps.
import jsxA11y from 'eslint-plugin-jsx-a11y'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
      jsxA11y.flatConfigs.recommended,
    ],
    languageOptions: {
      globals: globals.browser,
      parserOptions: { ecmaFeatures: { jsx: true } },
    },
    rules: {
      // The OpenStreetMap iframe needs target="_blank" for the external link.
      // The frontend code already sets rel="noreferrer".
      'jsx-a11y/anchor-is-valid': ['warn'],
    },
  },
])
