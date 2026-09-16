/**
 * Entry point.
 *
 * Styles are imported here so Vite emits one stylesheet; the CSP forbids
 * inline `<style>`, and one file is one request.
 */

import { render } from "preact";

import { App } from "./app";
import { boot } from "./state";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/marks.css";
import "./styles/app.css";

const root = document.getElementById("root");

if (root) {
  render(<App />, root);
  void boot().catch((error: unknown) => {
    // Booting is the one failure with no UI to show it in: surface it to the
    // host error log and leave a readable message behind.
    root.textContent = "Receipts could not start. Reload the window.";
    void import("./lib/anna").then(({ runtime }) => {
      try {
        const anna = runtime() as { window?: { report_error?: (args: unknown) => void } };
        anna.window?.report_error?.({
          message: error instanceof Error ? error.message : String(error),
        });
      } catch {
        // No host to report to; the message on screen is all there is.
      }
    });
  });
}
