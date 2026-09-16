/**
 * Executa ids.
 *
 * `anna-app apps publish` (and `anna-app dev`) resolve the `bundled:` handles
 * in manifest.json to minted ids and write `bundle/anna-tool-ids.js`, which
 * sets `window.__ANNA_TOOL_IDS__`. Reading it here means a minted id never has
 * to be pasted into source — see docs/api-notes.md §1.
 */

declare global {
  interface Window {
    __ANNA_TOOL_IDS__?: Record<string, string>;
  }
}

/** Local-dev id; must equal `tool_id` in executas/receipts-engine/executa.json. */
export const DEV_TOOL_ID = "tool-dev-receipts-engine";

/** The handle used in app.json `bundled_executas` and manifest.json. */
export const ENGINE_HANDLE = "receipts-engine";

/** Plugin-side method name; mint-only ids carry no separator, so it is required. */
export const ENGINE_METHOD = "engine";

export function engineToolId(): string {
  const injected = typeof window !== "undefined" ? window.__ANNA_TOOL_IDS__ : undefined;
  return injected?.[ENGINE_HANDLE] ?? DEV_TOOL_ID;
}
