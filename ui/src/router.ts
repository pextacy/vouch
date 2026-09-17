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
  | { name: "new-match" }
  | { name: "progress" }
  | { name: "match"; id: string }
  | { name: "tailor" }
  | { name: "letter" }
  | { name: "tracker" }
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
      return parts[1] === "preview" ? { name: "cv-preview" } : { name: "cv-add" };
    case "new":
      return { name: "new-match" };
    case "progress":
      return { name: "progress" };
    case "match":
      return parts[1] ? { name: "match", id: parts[1] } : { name: "tracker" };
    case "tailor":
      return { name: "tailor" };
    case "letter":
      return { name: "letter" };
    case "matches":
      return { name: "tracker" };
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

