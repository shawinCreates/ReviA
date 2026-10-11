import { STAGES, type Stage } from "@/lib/config";
import type { ChatSession, LibraryDocument, Message } from "@/lib/types";

const HOUR = 3_600_000;

function ago(hours: number): string {
  return new Date(Date.now() - hours * HOUR).toISOString();
}

export const DEMO_LIBRARY_ID = "demo-library";

export const DEMO_DOCUMENTS: LibraryDocument[] = [
  {
    id: "doc-natlaw",
    filename: "Constitutional Law - Week 4 Notes.pdf",
    sizeBytes: 2_411_724,
    pageCount: 24,
    status: "ready",
    stageDetail: "24 pages, 61 chunks",
    error: null,
    createdAt: ago(52),
    owned: false,
  },
  {
    id: "doc-thermo",
    filename: "Thermodynamics Lecture 07.pptx",
    sizeBytes: 8_930_112,
    pageCount: 31,
    status: "ready",
    stageDetail: "31 pages, 48 chunks",
    error: null,
    createdAt: ago(50),
    owned: false,
  },
  {
    id: "doc-fieldwork",
    filename: "Field Methods Handbook.pdf",
    sizeBytes: 5_242_880,
    pageCount: 112,
    status: "ready",
    stageDetail: "112 pages, 310 chunks",
    error: null,
    createdAt: ago(49),
    owned: false,
  },
  {
    id: "doc-genetics",
    filename: "Genetics Problem Set 3.docx",
    sizeBytes: 184_320,
    pageCount: 6,
    status: "ready",
    stageDetail: "6 pages, 19 chunks",
    error: null,
    createdAt: ago(48),
    owned: false,
  },
];

export const DEMO_PIPELINE_DOCUMENTS: LibraryDocument[] = [
  ...DEMO_DOCUMENTS.slice(0, 2),
  {
    id: "doc-sicilian",
    filename: "Sicilian Gardens, 1780-1900.pdf",
    sizeBytes: 18_874_368,
    pageCount: null,
    status: "queued",
    stageDetail: "Waiting for a worker",
    error: null,
    createdAt: ago(0.02),
    owned: true,
  },
  {
    id: "doc-micro",
    filename: "Microbiology Lab Report - Draft.docx",
    sizeBytes: 96_256,
    pageCount: null,
    status: "parsing",
    stageDetail: "Page 4 of 9",
    error: null,
    createdAt: ago(0.05),
    owned: true,
  },
  {
    id: "doc-optics",
    filename: "Optics Slideshow.pptx",
    sizeBytes: 12_582_912,
    pageCount: null,
    status: "chunking",
    stageDetail: "Chunk 84 of 96",
    error: null,
    createdAt: ago(0.08),
    owned: true,
  },
  {
    id: "doc-tectonics",
    filename: "Plate Tectonics Review.pdf",
    sizeBytes: 4_194_304,
    pageCount: 44,
    status: "embedding",
    stageDetail: "Embedding 191 of 240",
    error: null,
    createdAt: ago(0.12),
    owned: true,
  },
  {
    id: "doc-scan",
    filename: "Handwritten Lecture Notes (scan).pdf",
    sizeBytes: 6_291_456,
    pageCount: null,
    status: "failed",
    stageDetail: "Failed after 2 attempts",
    error: "No readable text found. Scanned PDFs need OCR, which is not supported yet.",
    createdAt: ago(0.3),
    owned: true,
  },
];

export const DEMO_SESSIONS: ChatSession[] = [
  { id: "sess-1", title: "What counts as judicial review?", createdAt: ago(3), messageCount: 6 },
  { id: "sess-2", title: "Second law at constant volume", createdAt: ago(26), messageCount: 4 },
  { id: "sess-3", title: "Transect method for quadrats", createdAt: ago(50), messageCount: 8 },
  { id: "sess-4", title: "Punnett square for a dihybrid", createdAt: ago(74), messageCount: 2 },
];

const CITE = {
  "doc-natlaw": "Constitutional Law - Week 4 Notes.pdf",
  "doc-thermo": "Thermodynamics Lecture 07.pptx",
  "doc-fieldwork": "Field Methods Handbook.pdf",
  "doc-genetics": "Genetics Problem Set 3.docx",
};

export const DEMO_MESSAGES: Message[] = [
  {
    id: "m1",
    role: "user",
    content: "What counts as judicial review in the UK, and why was it established?",
    citations: [],
    refused: false,
    uncited: false,
    createdAt: ago(3.1),
  },
  {
    id: "m2",
    role: "assistant",
    content:
      "Judicial review is the courts' power to examine whether a public body has acted lawfully, rationally, and fairly, and to remedy the failure. It is not an appeal against the decision itself: the court does not re-run the decision, it checks the process that produced it [S1].\n\nIt was established in the late 19th century, most often traced to Regina v. Burah (1876), which held that a public body was subject to the courts even when the Crown was involved [S1].",
    citations: [
      {
        label: "S1",
        page: 7,
        documentId: "doc-natlaw",
        filename: CITE["doc-natlaw"],
        snippet:
          "Judicial review is the courts' supervisory jurisdiction over public bodies... it is not an appeal on the merits.",
      },
    ],
    refused: false,
    uncited: false,
    createdAt: ago(3),
  },
  {
    id: "m3",
    role: "user",
    content: "Does that change if the body is a minister exercising a statutory duty?",
    citations: [],
    refused: false,
    uncited: false,
    createdAt: ago(2.9),
  },
  {
    id: "m4",
    role: "assistant",
    content:
      "No. A minister exercising a statutory duty is a public body for this purpose, and the availability of judicial review does not depend on whether the decision is ministerial or administrative [S1]. What changes is the intensity of review: a decision taken under a wide statutory discretion is reviewed for rationality only, not for correctness [S2].",
    citations: [
      {
        label: "S1",
        page: 7,
        documentId: "doc-natlaw",
        filename: CITE["doc-natlaw"],
        snippet: "Public bodies include ministers exercising statutory duties.",
      },
      {
        label: "S2",
        page: 9,
        documentId: "doc-natlaw",
        filename: CITE["doc-natlaw"],
        snippet: "Wider discretion narrows the court to a rationality review.",
      },
    ],
    refused: false,
    uncited: false,
    createdAt: ago(2.8),
  },
];

export const SUGGESTED_QUESTIONS = [
  "What is judicial review?",
  "How do I set up a quadrat transect?",
  "What does the second law say at constant volume?",
];

export function documentsByStage(
  documents: LibraryDocument[],
): Record<Stage, LibraryDocument[]> {
  const grouped = Object.fromEntries(
    STAGES.map((stage) => [stage, []]),
  ) as unknown as Record<Stage, LibraryDocument[]>;

  for (const document of documents) {
    grouped[document.status].push(document);
  }

  return grouped;
}
