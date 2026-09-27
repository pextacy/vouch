/**
 * A hash router, because the History API is unreliable inside the app iframe.
 *
 * Routes are flat and few; anything more would be machinery for its own sake.
 */

import { signal } from "@preact/signals";

export type Route =
  | { name: "onboarding" }
  | { name: "cv-add" }
  | { name: "cv-preview" }
  | { name: "cv-audit" }
  | { name: "cv-ledger" }
  | { name: "cv-profile" }
  | { name: "check" }
  | { name: "new-match" }
  | { name: "progress" }
  | { name: "match"; id: string }
  | { name: "tailor" }
  | { name: "gaps" }
  | { name: "letter" }
  | { name: "answers" }
  | { name: "share" }
  | { name: "brief" }
  | { name: "since" }
  | { name: "followup" }
  | { name: "changed" }
  | { name: "worth" }
  | { name: "tracker" }
  | { name: "recurring" }
  | { name: "compare" }
  | { name: "settings" };

export const route = signal<Route>(parse(currentHash()));

function currentHash(): string {
  if (typeof window === "undefined") return "/";
  return window.location.hash.replace(/^#/, "") || "/";
}

export function parse(path: string): Route {
  const clean = path.split("?")[0] ?? "/";
  const parts = clean.split("/").filter(Boolean);

  switch (parts[0]) {
    case undefined:
      return { name: "onboarding" };
    case "cv":
      if (parts[1] === "preview") return { name: "cv-preview" };
      if (parts[1] === "audit") return { name: "cv-audit" };
      if (parts[1] === "ledger") return { name: "cv-ledger" };
      if (parts[1] === "profile") return { name: "cv-profile" };
      return { name: "cv-add" };
    case "check":
      return { name: "check" };
    case "new":
      return { name: "new-match" };
    case "progress":
      return { name: "progress" };
    case "match":
      return parts[1] ? { name: "match", id: parts[1] } : { name: "tracker" };
    case "tailor":
      return { name: "tailor" };
    case "gaps":
      return { name: "gaps" };
    case "letter":
      return { name: "letter" };
    case "answers":
      return { name: "answers" };
    case "share":
      return { name: "share" };
    case "brief":
      return { name: "brief" };
    case "since":
      return { name: "since" };
    case "followup":
      return { name: "followup" };
    case "changed":
      return { name: "changed" };
    case "worth":
      return { name: "worth" };
    case "matches":
      return { name: "tracker" };
    case "recurring":
      return { name: "recurring" };
    case "compare":
      return { name: "compare" };
    case "data":
      return { name: "settings" };
    default:
      return { name: "onboarding" };
  }
}

export function navigate(path: string): void {
  if (typeof window === "undefined") return;
  const next = path.startsWith("#") ? path.slice(1) : path;
  if (currentHash() === next) {
    route.value = parse(next);
    return;
  }
  window.location.hash = next;
}

export function startRouter(): () => void {
  const handler = () => {
    route.value = parse(currentHash());
  };
  window.addEventListener("hashchange", handler);
  handler();
  return () => window.removeEventListener("hashchange", handler);
}

