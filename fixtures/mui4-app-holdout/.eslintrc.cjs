module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  plugins: ['@typescript-eslint', 'react-hooks'],
  extends: ['eslint:recommended', 'plugin:@typescript-eslint/recommended', 'plugin:react-hooks/recommended'],
  env: { browser: true, es2019: true, jest: true },
  parserOptions: { ecmaVersion: 2019, sourceType: 'module', ecmaFeatures: { jsx: true } },
  rules: { 'no-undef': 'off' },
};
