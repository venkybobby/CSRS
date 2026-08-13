// ESLint 9 flat config. `npm run lint` failed outright before this existed
// -- ESLint 9 dropped .eslintrc support and the repo never had a config in
// either format, so the script errored rather than reporting zero problems.
// That is also why nothing caught it: cloudbuild/pr-checks.yaml's lint step
// is `ruff check` over the Python tree only, and never invokes npm.
import js from "@eslint/js";
import tsParser from "@typescript-eslint/parser";
import tsPlugin from "@typescript-eslint/eslint-plugin";
import globals from "globals";

export default [
  { ignores: ["dist/**", "node_modules/**", "*.config.js"] },
  js.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: "latest",
        sourceType: "module",
        ecmaFeatures: { jsx: true },
      },
      globals: { ...globals.browser },
    },
    plugins: { "@typescript-eslint": tsPlugin },
    rules: {
      ...tsPlugin.configs.recommended.rules,
      // tsc -b --noEmit already reports undefined identifiers with real type
      // information; the base rule additionally can't see JSX or type-only
      // references and would flag them as undefined.
      "no-undef": "off",
      // Prefixing with _ is the documented escape hatch for a deliberately
      // unused binding (destructuring rest, unused catch param).
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];
