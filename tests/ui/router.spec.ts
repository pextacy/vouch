/** Route parsing — every path the app can be deep-linked to. */

import { describe, expect, it } from "vitest";

import { parse } from "../../ui/src/router";

describe("parse", () => {
  it.each([
    ["/", "onboarding"],
    ["", "onboarding"],
    ["/cv/add", "cv-add"],
    ["/cv", "cv-add"],
    ["/cv/preview", "cv-preview"],
    ["/new", "new-match"],
    ["/progress", "progress"],
    ["/matches", "tracker"],
    ["/data", "settings"],
    ["/tailor", "tailor"],
    ["/letter", "letter"],
    ["/nonsense", "onboarding"],
  ])("maps %s to %s", (path, name) => {
    expect(parse(path).name).toBe(name);
  });

  it("carries the match id", () => {
    const route = parse("/match/abc123");
    expect(route).toEqual({ name: "match", id: "abc123" });
  });

  it("falls back to the tracker when a match id is missing", () => {
    expect(parse("/match").name).toBe("tracker");
  });

  it("ignores a query string", () => {
    expect(parse("/matches?ref=reddit").name).toBe("tracker");
  });
});
