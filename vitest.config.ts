import { defineConfig } from "vitest/config";

// Bundle tests import the UI source directly rather than the built artefact:
// a failure should point at a line of TypeScript, not at a column in
// assets/index.js.
export default defineConfig({
  esbuild: { jsx: "automatic", jsxImportSource: "preact" },
  test: {
    include: ["tests/ui/**/*.spec.ts"],
    environment: "node",
    globals: false,
  },
});
