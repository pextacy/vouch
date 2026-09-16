import { defineConfig } from "vite";
import preact from "@preact/preset-vite";

// The bundle is served under a sandboxed iframe CSP with `script-src 'self'
// <sdk-origin>`: no inline scripts, no external CDNs, relative asset paths.
export default defineConfig({
  plugins: [preact()],
  base: "./",
  build: {
    outDir: "../bundle",
    emptyOutDir: true,
    target: "es2022",
    assetsDir: "assets",
    cssCodeSplit: false,
    // Inlining would put the asset in a `<style>`/data URI; keeping files
    // separate keeps the CSP simple and the cache useful.
    assetsInlineLimit: 0,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name][extname]",
      },
    },
  },
  server: { port: 5173 },
});
