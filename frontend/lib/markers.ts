/**
 * Splits an assistant answer into text and citation-marker segments.
 *
 * Markers are already validated against real citations by `toDisplayText` in
 * `lib/api.ts`, which relabels a bracketed number into `[S1]` only when that
 * number resolved to a citation. Anything this function does not match —
 * `[2024]`, `[7]`, a malformed `[S1` — is a model-authored bracket and must
 * render as text.
 */

export type Segment = { kind: "text"; value: string } | { kind: "marker"; label: string };

const GROUP = /\[(S\d+(?:,\s*S\d+)*)\]/g;

const LABEL = /S\d+/g;

export function splitMarkers(text: string): Segment[] {
  const segments: Segment[] = [];
  let cursor = 0;
  for (const match of text.matchAll(GROUP)) {
    const before = text.slice(cursor, match.index);
    if (before.length > 0) segments.push({ kind: "text", value: before });
    let inner = 0;
    const group = match[1];
    for (const label of group.matchAll(LABEL)) {
      const gap = group.slice(inner, label.index);
      if (gap.length > 0) segments.push({ kind: "text", value: gap });
      segments.push({ kind: "marker", label: label[0] });
      inner = label.index + label[0].length;
    }
    cursor = match.index + match[0].length;
  }
  const tail = text.slice(cursor);
  if (tail.length > 0) segments.push({ kind: "text", value: tail });
  return segments;
}
