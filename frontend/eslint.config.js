// ESLint flat config.
//
// The rules here enforce SPEC §9.0's constraints mechanically, so a future
// contributor (or a future agent) cannot quietly reintroduce the TypeScript
// constructs the maintainer has to be able to read.

import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { ignores: ['dist', 'src/types/api.gen.ts'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
      'react-refresh': reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],

      // SPEC §9.0 Rule 2: `any` is a permitted escape hatch, so this must not
      // be an error — but each use should carry a comment saying why.
      '@typescript-eslint/no-explicit-any': 'off',

      // SPEC §9.0 Rule 1: these constructs are banned outright. Restricting the
      // syntax means the reviewer does not have to remember to catch them.
      'no-restricted-syntax': [
        'error',
        {
          selector: 'TSEnumDeclaration',
          message: 'SPEC §9.0 Rule 1: use a union of string literals instead of an enum.',
        },
        {
          selector: 'TSModuleDeclaration[kind="namespace"]',
          message: 'SPEC §9.0 Rule 1: namespaces are banned. Use modules.',
        },
        {
          selector: 'TSConditionalType',
          message: 'SPEC §9.0 Rule 1: conditional types are banned. Restructure the code.',
        },
        {
          selector: 'TSMappedType',
          message: 'SPEC §9.0 Rule 1: mapped types are banned. Restructure the code.',
        },
        {
          selector: 'TSInferType',
          message: 'SPEC §9.0 Rule 1: `infer` is banned. Restructure the code.',
        },
        {
          selector: 'ClassDeclaration[abstract=true]',
          message: 'SPEC §9.0 Rule 1: abstract classes are banned.',
        },
        {
          selector: 'Decorator',
          message: 'SPEC §9.0 Rule 1: decorators are banned.',
        },
      ],

      // Unused args are fine when they exist to satisfy a library signature,
      // provided they are underscore-prefixed to say so.
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
    },
  },
  // Config files run in Node, not the browser.
  {
    files: ['*.config.js', 'vite.config.ts'],
    languageOptions: { globals: globals.node },
  },
)
