/**
 * More than one CV, and the promise that nobody's first one moves.
 *
 * Two failures would be expensive here and both are tested below. A CV that
 * did not survive the upgrade is the one thing this app cannot lose — so the
 * first document stays under the key v1.0 wrote it to, and a match saved
 * before there were profiles still belongs to it. And a workspace that leaked
 * would be worse than no workspaces at all: an application checked against the
 * backend CV appearing under the data CV would put line citations against a
 * document that never contained those lines.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  DEFAULT_CV_ID,
  MAX_CV_NAME,
  MAX_CV_PROFILES,
  cleanName,
  cvKey,
  forProfile,
  mintCvId,
  nameFromFilename,
  nameOf,
  normalize,
} from "../../ui/src/lib/profiles";
import type { CvProfile, TrackerEntry } from "../../ui/src/lib/types";

const profile = (id: string, name = id): CvProfile => ({
  id,
  name,
  created_at: "2026-09-20T10:00:00+00:00",
});

const entry = (id: string, cv?: string): TrackerEntry => ({
  id,
  company: "Northwind",
  role: "Backend Engineer",
  created_at: "2026-09-20T10:00:00+00:00",
  strong: 6,
  total: 8,
  status: "drafted",
  ...(cv ? { cv } : {}),
});

describe("where a CV lives", () => {
  it("leaves the first one exactly where v1.0 put it", () => {
    // The whole migration story: an existing user's CV is not moved, copied or
    // rewritten by the upgrade, so a bug in this feature cannot lose it.
    expect(cvKey(DEFAULT_CV_ID)).toBe("cv:v1");
  });

  it("gives every later one its own key", () => {
    expect(cvKey("cv-2f9a")).toBe("cv:v1:cv-2f9a");
  });
});

describe("mintCvId", () => {
  it("never returns an id already in use", () => {
    const ids = new Set<string>();
    let taken: CvProfile[] = [profile(DEFAULT_CV_ID)];
    for (let index = 0; index < 20; index += 1) {
      const id = mintCvId(taken);
      expect(ids.has(id)).toBe(false);
      ids.add(id);
      taken = [...taken, profile(id)];
    }
  });
});

describe("naming", () => {
  it("reads a name off the file the user uploaded", () => {
    expect(nameFromFilename("dilek-aydin-backend.pdf")).toBe("dilek aydin backend");
  });

  it("has nothing to say about a pasted CV", () => {
    expect(nameFromFilename(null)).toBeNull();
  });

  it("refuses a name that is only whitespace", () => {
    expect(cleanName("   ")).toBeNull();
  });

  it("keeps a name short enough to render in a tab", () => {
    expect(cleanName("x".repeat(200))).toHaveLength(MAX_CV_NAME);
  });
});

describe("normalize", () => {
  it("turns a missing record into the one CV the account already had", () => {
    const { active, list } = normalize(null, "CV 1");

    expect(active).toBe(DEFAULT_CV_ID);
    expect(list).toHaveLength(1);
    expect(list[0]?.name).toBe("CV 1");
  });

  it("keeps the first CV even when a stored record forgot it", () => {
    const { list } = normalize({ active: "cv-2", list: [profile("cv-2")] }, "CV 1");

    expect(list.map((item) => item.id)).toEqual([DEFAULT_CV_ID, "cv-2"]);
  });

  it("falls back to the first CV when the active one is gone", () => {
    const { active } = normalize({ active: "deleted", list: [profile(DEFAULT_CV_ID)] }, "CV 1");

    expect(active).toBe(DEFAULT_CV_ID);
  });

  it("drops duplicates and refuses to grow past the cap", () => {
    const many = Array.from({ length: MAX_CV_PROFILES + 3 }, (_, index) =>
      profile(`cv-${index}`),
    );
    const { list } = normalize({ active: DEFAULT_CV_ID, list: [...many, ...many] }, "CV 1");

    expect(list).toHaveLength(MAX_CV_PROFILES);
  });
});

describe("forProfile", () => {
  it("counts an untagged application as the first CV's", () => {
    // Every match saved before v1.2 is untagged, and there was only one CV to
    // make it against.
    const entries = [entry("m1"), entry("m2", "cv-2"), entry("m3", DEFAULT_CV_ID)];

    expect(forProfile(entries, DEFAULT_CV_ID).map((row) => row.id)).toEqual(["m1", "m3"]);
    expect(forProfile(entries, "cv-2").map((row) => row.id)).toEqual(["m2"]);
  });
});

describe("nameOf", () => {
  it("falls back rather than rendering an empty heading", () => {
    expect(nameOf([profile("cv-2", "Data")], "gone", "CV")).toBe("CV");
  });
});

// ─── The workspace, end to end ────────────────────────────────────────

const storage = new Map<string, unknown>();

vi.mock("../../ui/src/lib/store", async () => {
  const { DEFAULT_CV_ID: FIRST, cvKey: keyOf } = await import("../../ui/src/lib/profiles");
  const read = <T,>(key: string): T | null => (storage.get(key) as T) ?? null;
  const index = (): TrackerEntry[] => read<TrackerEntry[]>("matches:index:v1") ?? [];
  const belongsTo = (row: { cv?: string }) => row.cv ?? FIRST;

  return {
    loadProfile: async () => null,
    saveProfile: async () => undefined,
    loadCv: async (id: string = FIRST) => read(keyOf(id)),
    saveCv: async (value: unknown, id: string = FIRST) => void storage.set(keyOf(id), value),
    deleteCv: async (id: string = FIRST) => void storage.delete(keyOf(id)),
    loadCvProfiles: async () => read("cvs:v1"),
    saveCvProfiles: async (value: unknown) => void storage.set("cvs:v1", value),
    loadIndex: async () => index(),
    loadMatch: async (id: string) => read(`match:v1:${id}`),
    loadRecentMatches: async (limit: number, cvId: string = FIRST) =>
      index()
        .filter((row) => belongsTo(row) === cvId)
        .slice(0, limit)
        .map((row) => read(`match:v1:${row.id}`))
        .filter(Boolean),
    saveMatch: async () => index(),
    attachTailor: async () => undefined,
    attachLetter: async () => undefined,
    attachAccepted: async () => undefined,
    setMatchStatus: async () => index(),
    deleteMatch: async (id: string) => {
      storage.delete(`match:v1:${id}`);
      const kept = index().filter((row) => row.id !== id);
      storage.set("matches:index:v1", kept);
      return kept;
    },
    deleteCvProfile: async (id: string) => {
      for (const row of index().filter((row) => belongsTo(row) === id)) {
        storage.delete(`match:v1:${row.id}`);
      }
      const kept = index().filter((row) => belongsTo(row) !== id);
      storage.set("matches:index:v1", kept);
      storage.delete(keyOf(id));
      return kept;
    },
    deleteEverything: async (ids: string[]) => {
      for (const row of index()) storage.delete(`match:v1:${row.id}`);
      storage.delete("matches:index:v1");
      for (const id of ids) storage.delete(keyOf(id));
      storage.delete("cvs:v1");
    },
  };
});

const { EXAMPLE_CV } = await import("../../ui/src/lib/example");
const state = await import("../../ui/src/state");

function seed(): void {
  storage.clear();
  storage.set("cv:v1", { doc: EXAMPLE_CV, filename: "backend.pdf", updated_at: "2026-09-19" });
  storage.set("cv:v1:cv-data", {
    doc: { ...EXAMPLE_CV, hash: "data-cv-hash" },
    filename: "data.pdf",
    updated_at: "2026-09-19",
  });
  storage.set("cvs:v1", {
    version: 1,
    active: DEFAULT_CV_ID,
    list: [profile(DEFAULT_CV_ID, "Backend"), profile("cv-data", "Data")],
  });
  storage.set("matches:index:v1", [
    entry("m-old"),
    entry("m-backend", DEFAULT_CV_ID),
    entry("m-data", "cv-data"),
  ]);
}

describe("the CV as a workspace", () => {
  beforeEach(async () => {
    seed();
    await state.boot();
  });

  it("opens the CV the account was left on, with only its applications", () => {
    expect(state.activeCvId.value).toBe(DEFAULT_CV_ID);
    expect(state.cv.value?.filename).toBe("backend.pdf");
    // The untagged match belongs to the first CV — that is what "saved before
    // there were profiles" means.
    expect(state.tracker.value.map((row) => row.id)).toEqual(["m-old", "m-backend"]);
  });

  it("switches the document and the applications together", async () => {
    await state.useCv("cv-data");

    expect(state.cv.value?.doc.hash).toBe("data-cv-hash");
    expect(state.tracker.value.map((row) => row.id)).toEqual(["m-data"]);
    expect(state.activeCvName.value).toBe("Data");
  });

  it("drops work that was about the other CV rather than showing it here", async () => {
    state.currentMatch.value = { ...EXAMPLE_CV, id: "m-backend" } as never;

    await state.useCv("cv-data");

    expect(state.currentMatch.value).toBeNull();
  });

  it("takes a deleted CV's applications with it, and leaves the others", async () => {
    await state.removeCvProfile("cv-data");

    expect(state.cvProfiles.value.map((item) => item.id)).toEqual([DEFAULT_CV_ID]);
    expect(storage.get("cv:v1:cv-data")).toBeUndefined();
    expect(storage.get("match:v1:m-data")).toBeUndefined();
    expect(state.tracker.value.map((row) => row.id)).toEqual(["m-old", "m-backend"]);
  });

  it("refuses to delete the last CV, because that is the other button", async () => {
    await state.removeCvProfile("cv-data");
    await state.removeCvProfile(DEFAULT_CV_ID);

    expect(state.cvProfiles.value).toHaveLength(1);
    expect(storage.get("cv:v1")).toBeDefined();
  });

  it("keeps a rename", async () => {
    await state.renameCv("cv-data", "  Data  Science ");

    expect(state.cvProfiles.value.find((item) => item.id === "cv-data")?.name).toBe(
      "Data Science",
    );
    expect(storage.get("cvs:v1")).toMatchObject({ active: DEFAULT_CV_ID });
  });
});
