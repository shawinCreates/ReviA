import { toDisplayText, toDocument, toMessage, type WireDocument, type WireMessage } from "../lib/api.js";

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

console.log("\n== toDisplayText: inline markers match the S-labels on the cards ==");
const one = new Set([1]);
const two = new Set([1, 2]);

check("single marker", toDisplayText("Judicial review [1].", one) === "Judicial review [S1].");
check("two markers", toDisplayText("First [1] then [2].", two) === "First [S1] then [S2].");
check("grouped marker", toDisplayText("Both [1, 2] agree.", two) === "Both [S1, S2] agree.");
check("spaced group", toDisplayText("Both [1,2] agree.", two) === "Both [S1, S2] agree.");
check(
  "no markers is untouched",
  toDisplayText("No citations here.", two) === "No citations here.",
);

console.log("\n== markers that do not resolve stay as written ==");
check(
  "a bracketed year is not turned into a citation",
  toDisplayText("Published in [2024] here.", one) === "Published in [2024] here.",
  toDisplayText("Published in [2024] here.", one),
);
check(
  "an invented reference is left alone rather than relabelled",
  toDisplayText("See [7] for detail.", one) === "See [7] for detail.",
  toDisplayText("See [7] for detail.", one),
);
check(
  "a real marker beside a year still resolves",
  toDisplayText("See note [2024] and [1].", one) === "See note [2024] and [S1].",
  toDisplayText("See note [2024] and [1].", one),
);
check(
  "a group with one real and one invented reference keeps only the real one",
  toDisplayText("Both [1, 7] matter.", one) === "Both [S1] matter.",
  toDisplayText("Both [1, 7] matter.", one),
);
check(
  "a group with nothing resolvable is untouched",
  toDisplayText("Both [5, 6] matter.", one) === "Both [5, 6] matter.",
  toDisplayText("Both [5, 6] matter.", one),
);
check(
  "a multi-digit real marker resolves whole",
  toDisplayText("Item [12] here.", new Set([12])) === "Item [S12] here.",
  toDisplayText("Item [12] here.", new Set([12])),
);
check(
  "with no citation set the text is never touched",
  toDisplayText("Anything [1] at all.") === "Anything [1] at all.",
);

console.log("\n== toDocument: a real document payload ==");
const wireDocument: WireDocument = {
  id: "6c1f0a4e-2b7a-4f0e-9a1c-2f3b4c5d6e7f",
  filename: "Thermodynamics Lecture 07.pptx",
  extension: ".pptx",
  stage: "ready",
  stage_label: "Ready",
  size_bytes: 8_930_112,
  page_count: 31,
  error_message: null,
  chunk_count: 48,
  created_at: "2026-09-30T11:05:10.123456Z",
  updated_at: "2026-09-30T11:05:59.654321Z",
};
const document = toDocument(wireDocument);
check("filename passes through", document.filename === wireDocument.filename);
check("sizeBytes is a number", document.sizeBytes === 8_930_112);
check("pageCount survives", document.pageCount === 31);
check("status is the stage", document.status === "ready");
check("stageDetail reports real counts", document.stageDetail === "31 pages, 48 chunks", document.stageDetail);
check("no error for a healthy document", document.error === null);
check("a fetched document is owned", document.owned === true);

console.log("\n== toDocument: the stages the pipeline board renders ==");
const staged: WireDocument[] = [
  { ...wireDocument, stage: "queued", page_count: null, chunk_count: 0, error_message: null },
  { ...wireDocument, stage: "parsing", page_count: null, chunk_count: 0, error_message: null },
  { ...wireDocument, stage: "chunking", page_count: 44, chunk_count: 0, error_message: null },
  { ...wireDocument, stage: "embedding", page_count: 44, chunk_count: 0, error_message: null },
  { ...wireDocument, stage: "failed", page_count: null, chunk_count: 0, error_message: "No readable text found." },
  { ...wireDocument, stage: "ready", page_count: null, chunk_count: null, error_message: null },
];
for (const entry of staged) {
  const mapped = toDocument(entry);
  check(
    `${entry.stage} has a stageDetail`,
    mapped.stageDetail.length > 0,
    `got "${mapped.stageDetail}"`,
  );
  check(
    `${entry.stage} error passes through`,
    mapped.error === entry.error_message,
  );
}
check(
  "a ready document with no chunk count does not claim zero chunks",
  toDocument(staged[5]).stageDetail === "Searchable",
  toDocument(staged[5]).stageDetail,
);

console.log("\n== toMessage: citations, refusals and uncited answers ==");
const wireCitation = {
  reference: 1,
  chunk_id: "9a2b3c4d-5e6f-4a1b-8c9d-0e1f2a3b4c5d",
  document_id: "6c1f0a4e-2b7a-4f0e-9a1c-2f3b4c5d6e7f",
  filename: "Thermodynamics Lecture 07.pptx",
  page_number: 7,
  ordinal: 12,
  snippet: "Judicial review is the courts' supervisory jurisdiction.",
};

const cited: WireMessage = {
  id: "m2",
  role: "assistant",
  content: "A minister is a public body [1]. It is reviewed for rationality [2].",
  citations: [wireCitation, { ...wireCitation, reference: 2, page_number: 9 }],
  created_at: "2026-09-30T11:05:12Z",
};
const citedMessage = toMessage(cited, 5);
check("both citations are kept", citedMessage.citations.length === 2);
check("label is S-prefixed", citedMessage.citations[0].label === "S1", citedMessage.citations[0].label);
check("page comes from page_number", citedMessage.citations[0].page === 7);
check("documentId comes from document_id", citedMessage.citations[0].documentId === wireCitation.document_id);
check("snippet is carried", citedMessage.citations[0].snippet === wireCitation.snippet);
check("inline markers are relabelled", citedMessage.content.includes("[S1]") && citedMessage.content.includes("[S2]"), citedMessage.content);
check("a cited answer is not refused", citedMessage.refused === false);
check("a cited answer is not uncited", citedMessage.uncited === false);

const refused = toMessage({ ...cited, content: "I could not find that.", citations: [] }, 0);
check("no context means refused", refused.refused === true);
check("no context is not uncited", refused.uncited === false);

const uncited = toMessage({ ...cited, content: "Probably fine.", citations: [] }, 5);
check("context but no citation means uncited", uncited.uncited === true);
check("context but no citation is not refused", uncited.refused === false);

const userTurn = toMessage(
  { id: "m1", role: "user", content: "What is it?", citations: [], created_at: "2026-09-30T11:05:10Z" },
  5,
);
check("a user turn is never refused", userTurn.refused === false);
check("a user turn is never uncited", userTurn.uncited === false);

console.log("\n== a citation with no page ==");
const noPage = toMessage({ ...cited, citations: [{ ...wireCitation, page_number: null }] }, 1);
check("a missing page does not crash", noPage.citations[0].page === 0);
check(
  "a missing page renders as 'no page', not 'p. 0'",
  `${noPage.citations[0].page}` === "0",
);

console.log(failed === 0 ? "\nall mapping checks passed" : `\n${failed} failed`);
process.exit(failed === 0 ? 0 : 1);
