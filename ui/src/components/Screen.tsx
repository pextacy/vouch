/**
 * The page frame every screen sits in: one column, one measure, safe areas
 * respected. Keeping the padding here is what stops ten screens from each
 * inventing their own margins.
 */

import type { ComponentChildren } from "preact";

import "./Screen.css";

interface ScreenProps {
  heading?: string;
  lede?: string;
  children: ComponentChildren;
  wide?: boolean;
}

export function Screen({ heading, lede, children, wide }: ScreenProps) {
  return (
    <main class={`screen${wide ? " screen--wide" : ""}`}>
      {heading && (
        <div class="stack stack--tight screen__head">
          <h1>{heading}</h1>
          {lede && <p class="lede">{lede}</p>}
        </div>
      )}
      {children}
    </main>
  );
}
