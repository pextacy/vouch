/**
 * Tone and length for the letter.
 *
 * Radios, not a dropdown: three options each, and seeing all six choices at
 * once is the difference between picking one and hunting for one.
 */

import { t } from "../i18n";
import type { Length, Tone } from "../lib/types";
import "./ToneSwitch.css";

interface ToneSwitchProps {
  tone: Tone;
  length: Length;
  onTone: (tone: Tone) => void;
  onLength: (length: Length) => void;
  disabled?: boolean;
}

const TONES: Tone[] = ["plain", "warm", "formal"];
const LENGTHS: Length[] = ["short", "standard"];

export function ToneSwitch({ tone, length, onTone, onLength, disabled }: ToneSwitchProps) {
  return (
    <div class="row toneswitch">
      <fieldset class="toneswitch__group">
        <legend class="toneswitch__legend">{t("letter.tone")}</legend>
        {TONES.map((value) => (
          <label key={value} class={`toneswitch__option${tone === value ? " toneswitch__option--on" : ""}`}>
            <input
              class="visually-hidden"
              type="radio"
              name="tone"
              value={value}
              checked={tone === value}
              disabled={disabled}
              onChange={() => onTone(value)}
            />
            {t(`letter.tone.${value}`)}
          </label>
        ))}
      </fieldset>

      <fieldset class="toneswitch__group">
        <legend class="toneswitch__legend">{t("letter.length")}</legend>
        {LENGTHS.map((value) => (
          <label key={value} class={`toneswitch__option${length === value ? " toneswitch__option--on" : ""}`}>
            <input
              class="visually-hidden"
              type="radio"
              name="length"
              value={value}
              checked={length === value}
              disabled={disabled}
              onChange={() => onLength(value)}
            />
            {t(`letter.length.${value}`)}
          </label>
        ))}
      </fieldset>
    </div>
  );
}
