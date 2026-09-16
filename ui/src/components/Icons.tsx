/**
 * The icon set, drawn for this app.
 *
 * Six shapes, 16px, 1.5px stroke, all inheriting `currentColor`. An
 * off-the-shelf icon library would bring a house style that is not this one —
 * and the highlighter tip and the bracket are the two shapes that carry the
 * product's meaning, so they had to be drawn anyway.
 */

interface IconProps {
  /** Icons are decorative by default; pass a title to make one announced. */
  title?: string;
  size?: number;
}

function frame({ title, size = 16 }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 16 16",
    fill: "none",
    stroke: "currentColor",
    "stroke-width": 1.5,
    "stroke-linecap": "round" as const,
    "stroke-linejoin": "round" as const,
    role: (title ? "img" : undefined) as "img" | undefined,
    "aria-hidden": title ? undefined : true,
  };
}

/** Evidenced: a highlighter tip laying down a stroke. */
export function MarkerIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M9.6 2.4 13 5.8l-5.2 5.2-3.4-3.4L9.6 2.4Z" />
      <path d="M4.4 7.6 2.6 11l1.5 1.5 3.4-1.5" />
      <path d="M2 14h12" stroke-width="2" />
    </svg>
  );
}

/** Related: the 3px underline the partial mark uses, as a glyph. */
export function UnderlineIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M4 2.5v5a4 4 0 0 0 8 0v-5" />
      <path d="M3 13.5h10" stroke-width="2" />
    </svg>
  );
}

/** No evidence yet: empty brackets, the shape used in the map. */
export function BracketIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M6 2.5H3.5v11H6" />
      <path d="M10 2.5h2.5v11H10" />
    </svg>
  );
}

/** Folder tab — the tracker. */
export function TabIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M1.5 12.5v-8a1 1 0 0 1 1-1H6l1.5 2h6a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-11a1 1 0 0 1-1-1Z" />
    </svg>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M8 10.5V2.5" />
      <path d="m4.75 5.75 3.25-3.25 3.25 3.25" />
      <path d="M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" />
    </svg>
  );
}

export function DownloadIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M8 2.5v8" />
      <path d="m4.75 7.25 3.25 3.25 3.25-3.25" />
      <path d="M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2" />
    </svg>
  );
}

export function TrashIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M2.5 4h11" />
      <path d="M6 4V2.5h4V4" />
      <path d="M4 4v9a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4" />
      <path d="M6.5 6.5v5M9.5 6.5v5" />
    </svg>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="m3 8.5 3.5 3.5L13 5" />
    </svg>
  );
}

export function PencilIcon(props: IconProps) {
  return (
    <svg {...frame(props)}>
      {props.title && <title>{props.title}</title>}
      <path d="M11.2 2.3 13.7 4.8 5.5 13H3v-2.5L11.2 2.3Z" />
    </svg>
  );
}
