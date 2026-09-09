import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "scripts/news_collector/.venv/**",
    "scripts/news_collector/output/**",
  ]),
  {
    files: ["src/components/edition/news-edition.tsx"],
    rules: {
      // This component is shared with a plain HTML build, not just Next navigation.
      "@next/next/no-html-link-for-pages": "off",
      // Browser storage and URL state are hydrated after server rendering.
      "react-hooks/set-state-in-effect": "off",
    },
  },
]);

export default eslintConfig;
