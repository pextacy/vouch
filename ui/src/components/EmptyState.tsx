/**
 * What a screen shows before it has anything to show.
 *
 * Every empty state names the one action that fills it — an empty screen with
 * no way forward is a dead end the user has to back out of.
 */

import type { ComponentChildren } from "preact";

import "./EmptyState.css";

interface EmptyStateProps {
  text: string;
  action?: ComponentChildren;
}

export function EmptyState({ text, action }: EmptyStateProps) {
  return (
    <div class="empty">
      <p class="muted">{text}</p>
      {action}
    </div>
  );
}
