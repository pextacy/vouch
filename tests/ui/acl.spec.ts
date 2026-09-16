/**
 * The manifest and the code have to agree.
 *
 * `anna-app validate --strict` greps the bundle for `anna.<ns>.<method>`;
 * these tests check the other direction — that the ACL the manifest derives
 * actually permits what the app does, and refuses what it does not. A grant
 * that quietly disappears from the manifest fails here rather than in review.
 */

import { describe, expect, it } from "vitest";
import { HostApiError, deriveAcl, mountBundle } from "@anna-ai/cli/test";

import rawManifest from "../../manifest.json";

/**
 * The manifest on disk references the engine by its `bundled:` handle.
 * `anna-app dev` and `anna-app apps publish` substitute the resolved tool id
 * before the dispatcher ever sees it, so the ACL these tests exercise has to
 * be the substituted one — otherwise they would be checking a manifest that
 * never reaches production.
 */
const ENGINE_TOOL_ID = "tool-dev-receipts-engine";

const manifest = JSON.parse(
  JSON.stringify(rawManifest).replaceAll("bundled:receipts-engine", ENGINE_TOOL_ID),
) as typeof rawManifest;

describe("derived ACL", () => {
  const acl = deriveAcl(manifest as never);

  it("permits the calls the app makes", () => {
    for (const call of ["storage.get", "storage.set", "storage.delete", "storage.list"]) {
      expect(acl.allowed.has(call), call).toBe(true);
    }
  });

  it("does not permit a namespace the app never declared", () => {
    expect(acl.allowed.has("llm.complete")).toBe(false);
    expect(acl.allowed.has("chat.write_message")).toBe(false);
    expect(acl.allowed.has("fs.read")).toBe(false);
  });

  it("allows only the bundled engine as a tool", () => {
    expect(acl.toolsWildcard).toBe(false);
    expect([...acl.allowedTools]).toContain(ENGINE_TOOL_ID);
  });
});

describe("mounted bundle", () => {
  it("invokes the engine through the granted tool id", async () => {
    const harness = await mountBundle({
      manifest: manifest as never,
      mocks: {
        "tools.invoke": () => ({ ok: true, version: "1.0.0" }),
      },
    });

    await harness.runtime.tools.invoke({
      tool_id: ENGINE_TOOL_ID,
      method: "engine",
      args: { action: "health" },
    });

    const call = harness.calls.lastOf("tools.invoke");
    expect(call?.outcome).toBe("ok");
    expect(call?.args).toMatchObject({ method: "engine" });
  });

  it("denies a tool the manifest does not bundle", async () => {
    const harness = await mountBundle({ manifest: manifest as never });
    await expect(
      harness.runtime.tools.invoke({
        tool_id: "tool-someone-else-abcd1234",
        method: "engine",
        args: {},
      }),
    ).rejects.toBeInstanceOf(HostApiError);
    expect(harness.calls.last()?.outcome).toBe("denied");
  });

  it("denies an ungranted namespace", async () => {
    const harness = await mountBundle({ manifest: manifest as never });
    await expect(harness.runtime.llm.complete({ prompt: "hi" })).rejects.toBeInstanceOf(
      HostApiError,
    );
    expect(harness.calls.last()?.outcome).toBe("denied");
  });

  it("round-trips storage", async () => {
    const harness = await mountBundle({ manifest: manifest as never });
    await harness.runtime.storage.set("cv:v1", { hash: "abc" });
    await expect(harness.runtime.storage.get("cv:v1")).resolves.toMatchObject({ hash: "abc" });
  });
});

describe("manifest shape", () => {
  it("declares mobile support with a phone-sized minimum", () => {
    expect(manifest.ui.form_factors).toContain("mobile");
    expect(manifest.ui.views[0]?.min_size?.w).toBeLessThanOrEqual(360);
  });

  it("keeps the sampling capability the engine needs", () => {
    expect(manifest.host_capabilities).toContain("llm.sample");
  });

  it("declares no permission outside the platform allow-list", () => {
    const allowed = new Set([
      "artifact.create",
      "artifact.delete",
      "artifact.update",
      "chat.append_artifact",
      "chat.read",
      "chat.write_message",
      "fs.read",
      "fs.write",
      "llm.complete",
      "prefs.read",
      "storage.read",
      "storage.write",
      "tools.invoke",
      "ui.svg",
    ]);
    for (const permission of manifest.permissions) {
      expect(allowed.has(permission), permission).toBe(true);
    }
  });

  it("adds no CSP directive that would allow inline script", () => {
    expect(manifest.ui.csp_overrides["script-src"]).toEqual(["'self'"]);
    expect(manifest.ui.csp_overrides["style-src"]).toEqual(["'self'"]);
  });
});
