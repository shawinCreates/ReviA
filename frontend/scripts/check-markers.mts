import { splitMarkers } from "../lib/markers.js";

let failed = 0;

function check(name: string, condition: boolean, detail = "") {
  if (condition) {
    console.log(`  PASS  ${name}`);
  } else {
    failed += 1;
    console.log(`  FAIL  ${name}`);
    if (detail) console.log(`        ${detail}`);
  }
}

function equalSegments(actual: unknown, expected: unknown) {
  return JSON.stringify(actual) === JSON.stringify(expected);
}

console.log("\n== splitMarkers: text and citation markers ==");
check(
  "no markers is one text segment",
  equalSegments(splitMarkers("No markers here."), [{ kind: "text", value: "No markers here." }]),
  JSON.stringify(splitMarkers("No markers here.")),
);
check(
  "a marker splits the text around it",
  equalSegments(splitMarkers("Checked [S1]."), [
    { kind: "text", value: "Checked " },
    { kind: "marker", label: "S1" },
    { kind: "text", value: "." },
  ]),
  JSON.stringify(splitMarkers("Checked [S1].")),
);
check(
  "a grouped marker yields one segment per label",
  equalSegments(splitMarkers("Both [S1, S2] agree."), [
    { kind: "text", value: "Both " },
    { kind: "marker", label: "S1" },
    { kind: "text", value: ", " },
    { kind: "marker", label: "S2" },
    { kind: "text", value: " agree." },
  ]),
  JSON.stringify(splitMarkers("Both [S1, S2] agree.")),
);
check(
  "a bracketed year stays text",
  equalSegments(splitMarkers("Published in [2024] here."), [
    { kind: "text", value: "Published in [2024] here." },
  ]),
  JSON.stringify(splitMarkers("Published in [2024] here.")),
);
check(
  "a bare bracketed number stays text",
  equalSegments(splitMarkers("See [7] for detail."), [{ kind: "text", value: "See [7] for detail." }]),
  JSON.stringify(splitMarkers("See [7] for detail.")),
);
check(
  "a marker at the very start",
  equalSegments(splitMarkers("[S1] leads."), [
    { kind: "marker", label: "S1" },
    { kind: "text", value: " leads." },
  ]),
  JSON.stringify(splitMarkers("[S1] leads.")),
);
check("empty input yields no segments", equalSegments(splitMarkers(""), []), JSON.stringify(splitMarkers("")));
check(
  "adjacent markers produce no empty text segment between them",
  equalSegments(splitMarkers("[S1][S2]"), [
    { kind: "marker", label: "S1" },
    { kind: "marker", label: "S2" },
  ]),
  JSON.stringify(splitMarkers("[S1][S2]")),
);
check(
  "a malformed marker is literal text, not partially consumed",
  equalSegments(splitMarkers("Broken [S1 here."), [{ kind: "text", value: "Broken [S1 here." }]),
  JSON.stringify(splitMarkers("Broken [S1 here.")),
);
check(
  "a marker at the very end leaves no empty text segment",
  equalSegments(splitMarkers("Cited [S1]"), [
    { kind: "text", value: "Cited " },
    { kind: "marker", label: "S1" },
  ]),
  JSON.stringify(splitMarkers("Cited [S1]")),
);

console.log(failed === 0 ? "\nall marker checks passed" : `\n${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
