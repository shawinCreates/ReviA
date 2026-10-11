import { toDocument, toMessage, toSession, toDisplayText } from "../lib/api.js";
import type { WireDocument, WireMessage, WireSession } from "../lib/api.js";

const API = (process.env.API ?? "http://127.0.0.1:8000").replace(/\/$/, "");
const COOKIE = process.env.COOKIE ?? "sb=anything";

let failed = 0;
function check(name: string, condition: boolean, detail = "") {
  if (condition) console.log(`  PASS  ${name}`);
  else {
    failed += 1;
    console.log(`  FAIL  ${name}`);
    if (detail) console.log(`        ${detail}`);
  }
}

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API}${path}`, { headers: { cookie: COOKIE } });
  if (!response.ok) {
    if (response.status === 401) {
      console.error(
        `\n${API} rejected the request as unauthenticated.\n` +
          "This check needs a signed-in session: point API at a local API whose auth\n" +
          "is bypassed, or forward a real Supabase session cookie:\n\n" +
          "  API=http://127.0.0.1:8010 npm run check:api\n",
      );
      process.exit(2);
    }
    throw new Error(`${path} -> ${response.status} ${await response.text()}`);
  }
  return (await response.json()) as T;
}

console.log(`\nlive API: ${API}\n`);

console.log("== /libraries ==");
const { libraries } = await get<{ libraries: { id: string; is_default: boolean; document_count: number }[] }>(
  "/api/v1/libraries",
);
check("libraries returned", libraries.length > 0, JSON.stringify(libraries));
const defaultLibrary = libraries.find((library) => library.is_default);
check("a default library exists (the page picks it)", Boolean(defaultLibrary), JSON.stringify(libraries));
console.log(`        default: ${defaultLibrary?.id} with ${defaultLibrary?.document_count} documents`);

console.log("\n== /documents -> what the library column and pipeline board render ==");
const { documents: wireDocuments } = await get<{ documents: WireDocument[] }>("/api/v1/documents");
check("documents returned", wireDocuments.length > 0, "none — nothing to map");
for (const wire of wireDocuments) {
  const mapped = toDocument(wire);
  console.log(
    `        ${mapped.status.padEnd(9)} ${mapped.filename}  (${mapped.stageDetail})`,
  );
  check(`${wire.filename}: filename is non-empty`, mapped.filename.length > 0);
  check(`${wire.filename}: sizeBytes is a finite number`, Number.isFinite(mapped.sizeBytes));
  check(
    `${wire.filename}: stage is one the UI knows`,
    ["queued", "parsing", "chunking", "embedding", "ready", "failed"].includes(mapped.status),
    mapped.status,
  );
  check(`${wire.filename}: stageDetail is non-empty`, mapped.stageDetail.length > 0);
  check(
    `${wire.filename}: pageCount is a number or null`,
    mapped.pageCount === null || Number.isFinite(mapped.pageCount),
    String(mapped.pageCount),
  );
  check(`${wire.filename}: createdAt parses as a date`, !Number.isNaN(Date.parse(mapped.createdAt)));
  if (mapped.status === "ready") {
    check(`${wire.filename}: a ready document has real counts`, /\d/.test(mapped.stageDetail), mapped.stageDetail);
  }
  if (mapped.status === "failed") {
    check(`${wire.filename}: a failed document explains why`, Boolean(mapped.error), "no error text");
  }
}

console.log("\n== /chat/sessions -> what the history column renders ==");
const { sessions: wireSessions } = await get<{ sessions: WireSession[] }>("/api/v1/chat/sessions");
check("sessions returned", wireSessions.length > 0, "none");
for (const wire of wireSessions) {
  const mapped = toSession(wire);
  console.log(`        ${String(mapped.messageCount).padStart(2)} messages  ${mapped.title}`);
  check(`session ${wire.id.slice(0, 8)}: title is non-empty`, mapped.title.length > 0, `"${mapped.title}"`);
  check(`session ${wire.id.slice(0, 8)}: messageCount is a number`, Number.isFinite(mapped.messageCount));
  check(`session ${wire.id.slice(0, 8)}: createdAt parses as a date`, !Number.isNaN(Date.parse(mapped.createdAt)));
}

console.log("\n== /chat/sessions/<id> -> what the transcript renders ==");
const newest = wireSessions[0];
const { messages } = await get<{ messages: WireMessage[] }>(`/api/v1/chat/sessions/${newest.id}`);
check("history returned turns", messages.length > 0, "none");
check("history alternates user then assistant", messages[0]?.role === "user", `first role: ${messages[0]?.role}`);

for (const wire of messages) {
  const mapped = toMessage(wire);
  if (wire.role === "user") {
    console.log(`\n        YOU: ${mapped.content.slice(0, 90)}`);
    check("user turn has no citations", mapped.citations.length === 0);
    continue;
  }
  console.log(`\n        REVIA: ${mapped.content.slice(0, 150).replace(/\n/g, " ")}`);
  for (const citation of mapped.citations) {
    console.log(
      `          [${citation.label}] ${citation.filename} p.${citation.page} — "${citation.snippet.slice(0, 60)}…"`,
    );
    check("citation label is S-prefixed", /^S\d+$/.test(citation.label), citation.label);
    check("citation has a real page number", citation.page > 0, `page=${citation.page}`);
    check("citation has a filename", citation.filename.length > 0);
    check("citation has a snippet", citation.snippet.length > 0);
  }
  check(
    "every inline marker in the text resolves to a rendered card",
    Array.from(mapped.content.matchAll(/\[(S?\d+(?:, ?S?\d+)*)\]/g)).every((match) =>
      match[1]
        .split(",")
        .map((part) => part.trim())
        .every((label) => mapped.citations.some((citation) => `S${label.replace(/^S/, "")}` === citation.label)),
    ),
    mapped.content,
  );
  if (mapped.refused) console.log("          (rendered as: refused, nothing to cite)");
  if (mapped.uncited) console.log("          (rendered as: uncited, treat as unverified)");
}

console.log(`\n${failed === 0 ? "all live-data checks passed" : `${failed} failed`}`);
process.exit(failed === 0 ? 0 : 1);
