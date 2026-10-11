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
