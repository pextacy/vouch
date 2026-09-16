/**
 * A paper surface: the CV and the cover letter.
 *
 * The only element in the app that casts a shadow, and the only one set in the
 * serif. That pairing is the whole signal — grotesque means "app chrome",
 * serif on a lifted sheet means "this is your document".
 */

import type { ComponentChildren } from "preact";

import "./DocumentSheet.css";

interface DocumentSheetProps {
  title?: string;
  actions?: ComponentChildren;
  children: ComponentChildren;
  scrollRef?: (element: HTMLDivElement | null) => void;
}

export function DocumentSheet({ title, actions, children, scrollRef }: DocumentSheetProps) {
  return (
    <section class="sheet">
      {(title || actions) && (
        <header class="sheet__head">
          {title && <h2 class="sheet__title">{title}</h2>}
          {actions && <div class="row">{actions}</div>}
        </header>
      )}
      <div class="sheet__body" ref={scrollRef}>
        {children}
      </div>
    </section>
  );
}
