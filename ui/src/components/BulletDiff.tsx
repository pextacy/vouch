/**
 * One suggestion, next to the line it came from.
 *
 * The original is always visible. A rewrite the user cannot compare is a
 * rewrite they have to trust, and trust is the thing this product is trying
 * not to ask for.
 */

import { useState } from "preact/hooks";

import { SourceChip } from "./SourceChip";
import { t } from "../i18n";
import type { TailoredBullet } from "../lib/types";
import "./BulletDiff.css";

interface BulletDiffProps {
  bullet: TailoredBullet;
  accepted: string | undefined;
  onAccept: (text: string) => void;
  onSkip: () => void;
  readOnly?: boolean;
}

export function BulletDiff({ bullet, accepted, onAccept, onSkip, readOnly }: BulletDiffProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(accepted ?? bullet.suggestion ?? "");

  if (!bullet.suggestion) {
    return (
      <li class="bullet bullet--dropped">
        <p class="bullet__original">{bullet.original}</p>
        <p class="bullet__dropped">{t("tailor.dropped")}</p>
      </li>
    );
  }

  const current = accepted ?? bullet.suggestion;

  return (
    <li class={`bullet${accepted ? " bullet--accepted" : ""}`}>
      <div class="bullet__pane">
        <span class="bullet__label small muted">{t("tailor.original")}</span>
        <p class="bullet__original">{bullet.original}</p>
      </div>

      <div class="bullet__pane">
        <span class="bullet__label small muted">{t("tailor.suggestion")}</span>
        {editing ? (
          <textarea
            class="textarea bullet__editor"
            value={draft}
            maxLength={220}
            onInput={(event) => setDraft((event.target as HTMLTextAreaElement).value)}
          />
        ) : (
          <p class="bullet__suggestion">{current}</p>
        )}
      </div>

      <div class="row bullet__actions">
        {bullet.source_line_ids.map((line) => (
          <SourceChip key={line} line={line} />
        ))}

        {!readOnly && !editing && (
          <>
            <button
              type="button"
              class="button button--secondary"
              onClick={() => onAccept(current)}
              disabled={Boolean(accepted)}
            >
              {accepted ? t("tailor.accepted") : t("tailor.accept")}
            </button>
            <button type="button" class="button button--quiet" onClick={onSkip}>
              {t("tailor.skip")}
            </button>
            <button
              type="button"
              class="button button--quiet"
              onClick={() => {
                setDraft(current);
                setEditing(true);
              }}
            >
              {t("tailor.edit")}
            </button>
          </>
        )}

        {!readOnly && editing && (
          <>
            <button
              type="button"
              class="button"
              onClick={() => {
                onAccept(draft.trim() || current);
                setEditing(false);
              }}
            >
              {t("tailor.save")}
            </button>
            <button
              type="button"
              class="button button--quiet"
              onClick={() => {
                setDraft(current);
                setEditing(false);
              }}
            >
              {t("tailor.cancel")}
            </button>
          </>
        )}
      </div>
    </li>
  );
}
