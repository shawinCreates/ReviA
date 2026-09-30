import Link from "next/link";

import { APP_NAME, APP_TAGLINE } from "@/lib/config";
import { ArrowRight, Check, FileText, Search, Upload } from "@/components/icons";
import { Reveal } from "@/components/reveal";
import { PipelineBoard } from "@/components/pipeline/board";
import { SiteFooter, SiteHeader } from "@/components/chrome";
import { Badge, ButtonLink, Card, Kbd, SectionLabel } from "@/components/ui";

const FEATURES = [
  {
    title: "Every claim points at a page",
    body: "Sources are resolved against the chunks the model was actually shown. A label it invents is dropped rather than rendered, so a citation can never link to a page that does not support the claim.",
    span: "lg:col-span-2",
  },
  {
    title: "Two retrieval passes",
    body: "Dense vectors find paraphrase. Postgres full-text finds the acronym that appears once on page 40. Rank-fused, so neither leg can drown the other out.",
    span: "",
  },
  {
    title: "Says it does not know",
    body: "When nothing in your library answers the question, that is the answer. No answering from general knowledge and hoping.",
    span: "",
  },
  {
    title: "Your files stay private",
    body: "Objects are stored privately and reached through short-lived signed URLs. No one else can reach your library, and a citation link expires.",
    span: "",
  },
  {
    title: "You can watch it work",
    body: "Every upload moves through queued, parsing, chunking, embedding and ready, on a board you can open. No progress bar that lies by sitting at 90%.",
    span: "lg:col-span-2",
  },
] as const;

const STEPS = [
  {
    icon: Upload,
    label: "Upload",
    body: "Drop in lecture slides, papers, notes. PDF, DOCX and PPTX.",
  },
  {
    icon: FileText,
    label: "Parse and chunk",
    body: "Page by page, sliced so no chunk ever crosses a page boundary.",
  },
  {
    icon: Search,
    label: "Search both ways",
    body: "Vector similarity and full-text, fused into one ranked list.",
  },
  {
    icon: Check,
    label: "Answer with sources",
    body: "A cited answer, streamed as it is written.",
  },
] as const;

const FAQ = [
  {
    q: "Does it use my course material to train anything?",
    a: "No. Your files are used to answer your questions and for nothing else. Retrieval runs against your library only, so an answer can never be drawn from someone else's upload.",
  },
  {
    q: "What happens when it cannot find an answer?",
    a: "It tells you, and stops. The refusal is a real outcome rather than a fallback: a model that always answers is answering from its training data, not from your notes.",
  },
  {
    q: "Can I keep several libraries?",
    a: "Yes. Chat is scoped to exactly one library at a time, so a question about one module cannot be answered from another.",
  },
  {
    q: "Why is ingestion shown as a pipeline rather than a spinner?",
    a: "Because a five-page batch is visible work. You can see which stage a document is in, how far along it is, and what went wrong when it fails.",
  },
  {
    q: "Is there a file size limit?",
    a: "25MB per file, and up to 20 documents per library. The limit is on the file, not on how long an answer may be.",
  },
] as const;

const PLANS = [
  {
    name: "Student",
    price: "Free",
    cadence: "while the project is in beta",
    body: "Everything you need to ask questions of a semester's reading.",
    features: ["20 documents per library", "Unlimited questions", "Cited answers", "Pipeline visibility"],
    cta: "Try it",
    highlight: false,
  },
  {
    name: "Reading group",
    price: "£4",
    cadence: "per person, per month, when it launches",
    body: "Shared libraries for a seminar group, with separate accounts per person.",
    features: ["Everything in Student", "Shared libraries", "Group folders", "Export with citations"],
    cta: "Join the waitlist",
    highlight: true,
  },
] as const;

export default function Home() {
  return (
    <div className="min-h-dvh">
      <SiteHeader />

      <main>
        <section className="relative overflow-hidden border-b border-line">
          <div className="warm-wash absolute inset-0" />
          <div className="hairline-grid absolute inset-0 opacity-[0.55]" />
          <div className="relative mx-auto max-w-6xl px-6 pb-28 pt-24 sm:pt-32">
            <Reveal>
              <Badge tone="blue">Now in beta</Badge>
            </Reveal>
            <Reveal index={1}>
              <h1 className="mt-7 max-w-[16ch] text-display">{APP_TAGLINE}</h1>
            </Reveal>
            <Reveal index={2}>
              <p className="mt-7 max-w-[52ch] text-lede text-ink-soft">
                Upload your slides, papers and notes. Ask a question. Get an answer
                built only from what you uploaded, with the page number attached to
                every claim it makes.
              </p>
            </Reveal>
            <Reveal index={3}>
              <div className="mt-10 flex flex-wrap items-center gap-3">
                <ButtonLink href="/chat" size="lg">
                  Try {APP_NAME}
                  <ArrowRight />
                </ButtonLink>
                <ButtonLink href="/login" variant="outline" size="lg">
                  Create an account
                </ButtonLink>
              </div>
              <p className="mt-4 text-[13px] text-muted">
                No card. Try it against a sample library before you sign up.
              </p>
            </Reveal>
          </div>
        </section>

        <section className="border-b border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-20">
            <Reveal>
              <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
                <div className="rounded-[10px] border border-line bg-canvas p-7">
                  <div className="flex items-center gap-2.5 border-b border-line pb-4">
                    <span className="h-2 w-2 rounded-full bg-line-strong" />
                    <span className="h-2 w-2 rounded-full bg-line-strong" />
                    <span className="h-2 w-2 rounded-full bg-line-strong" />
                    <span className="ml-2 font-mono text-[11px] text-faint">
                      judicial-review
                    </span>
                  </div>
                  <div className="mt-6 space-y-6 text-[14px] leading-relaxed">
                    <p className="text-muted">
                      Does a minister exercising a statutory duty get the same review?
                    </p>
                    <p className="text-ink-soft">
                      Yes. A minister exercising a statutory duty is a public body for
                      this purpose [S1]. What changes is the intensity of the review: a
                      decision taken under a wide discretion is examined for rationality
                      only, not correctness [S2].
                    </p>
                    <div className="grid gap-2.5 sm:grid-cols-2">
                      <div className="rounded-[8px] border border-line bg-surface p-3.5">
                        <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-pale-blue-ink">
                          S1 &middot; p. 7
                        </p>
                        <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                          Public bodies include ministers exercising statutory duties.
                        </p>
                      </div>
                      <div className="rounded-[8px] border border-line bg-surface p-3.5">
                        <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-pale-blue-ink">
                          S2 &middot; p. 9
                        </p>
                        <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                          Wider discretion narrows the court to a rationality review.
                        </p>
                      </div>
                    </div>
                  </div>
                </div>
                <div className="space-y-5">
                  <div>
                    <SectionLabel>Why it holds up</SectionLabel>
                    <p className="mt-3 text-[14px] leading-relaxed text-ink-soft">
                      A citation is a database lookup, not a string the model wrote. If
                      a label does not resolve, the sentence renders uncited rather
                      than linked.
                    </p>
                  </div>
                  <div className="rounded-[10px] border border-line bg-canvas p-5">
                    <p className="text-[12px] text-muted">Ask with</p>
                    <p className="mt-2 flex gap-1.5">
                      <Kbd>/</Kbd>
                      <span className="text-[12px] text-faint">to focus the composer</span>
                    </p>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        <section id="how" className="border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <SectionLabel>How it works</SectionLabel>
              <h2 className="mt-4 max-w-[20ch] text-title">
                Four steps, then it is just answering questions.
              </h2>
            </Reveal>
            <ol className="mt-14 grid gap-px overflow-hidden rounded-[10px] border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
              {STEPS.map((step, index) => (
                <Reveal key={step.label} as="li" index={index} className="bg-canvas p-7">
                  <step.icon size={20} className="text-ink" />
                  <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.1em] text-faint">
                    0{index + 1}
                  </p>
                  <p className="mt-2 text-[15px] text-ink">{step.label}</p>
                  <p className="mt-2 text-[13px] leading-relaxed text-muted">{step.body}</p>
                </Reveal>
              ))}
            </ol>
          </div>
        </section>

        <section id="features" className="border-b border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <SectionLabel>What it does</SectionLabel>
              <h2 className="mt-4 max-w-[24ch] text-title">
                Built around the failure modes of a chat tool that quotes itself.
              </h2>
            </Reveal>
            <div className="mt-14 grid gap-4 lg:grid-cols-3">
              {FEATURES.map((feature, index) => (
                <Reveal
                  key={feature.title}
                  index={index}
                  className={feature.span}
                >
                  <Card className="h-full p-8">
                    <h3 className="text-[17px] leading-snug text-ink">{feature.title}</h3>
                    <p className="mt-3 text-[14px] leading-relaxed text-muted">{feature.body}</p>
                  </Card>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <SectionLabel>Ingestion</SectionLabel>
              <div className="mt-4 flex flex-wrap items-end justify-between gap-8">
                <h2 className="max-w-[20ch] text-title">
                  Watch a document move through the pipeline.
                </h2>
                <ButtonLink href="/pipeline" variant="outline">
                  See the full board
                  <ArrowRight />
                </ButtonLink>
              </div>
              <p className="mt-5 max-w-[64ch] text-lede text-ink-soft">
                Uploading six files at once is normal, not an edge case. Each one
                reports its own stage and progress, and a failure tells you what
                failed instead of retrying silently forever.
              </p>
            </Reveal>
            <Reveal index={1}>
              <PipelineBoard />
            </Reveal>
          </div>
        </section>

        <section id="pricing" className="border-b border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-24">
            <Reveal>
              <SectionLabel>Pricing</SectionLabel>
              <h2 className="mt-4 max-w-[22ch] text-title">
                Free while it is in beta.
              </h2>
            </Reveal>
            <div className="mt-14 grid gap-4 lg:grid-cols-2">
              {PLANS.map((plan, index) => (
                <Reveal key={plan.name} index={index}>
                  <Card
                    className={`flex h-full flex-col p-8 ${plan.highlight ? "border-ink" : ""}`}
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-[15px] text-ink">{plan.name}</p>
                      {plan.highlight ? <Badge tone="blue">Planned</Badge> : <Badge>Beta</Badge>}
                    </div>
                    <p className="mt-7 text-[42px] font-medium leading-none tracking-[-0.03em] text-ink">
                      {plan.price}
                    </p>
                    <p className="mt-2 text-[13px] text-muted">{plan.cadence}</p>
                    <p className="mt-5 text-[14px] leading-relaxed text-ink-soft">{plan.body}</p>
                    <ul className="mt-7 space-y-2.5">
                      {plan.features.map((feature) => (
                        <li key={feature} className="flex items-start gap-2.5 text-[13px] text-muted">
                          <Check size={15} className="mt-0.5 shrink-0 text-ink" />
                          {feature}
                        </li>
                      ))}
                    </ul>
                    <ButtonLink
                      href={plan.highlight ? "/login" : "/chat"}
                      variant={plan.highlight ? "outline" : "solid"}
                      className="mt-8 w-full"
                    >
                      {plan.cta}
                    </ButtonLink>
                  </Card>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-3xl px-6 py-24">
            <Reveal>
              <SectionLabel>Questions</SectionLabel>
              <h2 className="mt-4 text-title">Before you upload anything.</h2>
            </Reveal>
            <div className="mt-12">
              {FAQ.map((item, index) => (
                <Reveal key={item.q} as="li" index={index} className="border-b border-line">
                  <details className="group py-6">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-6 text-[15px] text-ink marker:content-none">
                      {item.q}
                      <span className="relative h-4 w-4 shrink-0">
                        <span className="absolute top-1/2 left-0 h-px w-4 bg-ink" />
                        <span className="absolute top-0 left-1/2 h-4 w-px bg-ink transition-opacity duration-200 group-open:opacity-0" />
                      </span>
                    </summary>
                    <p className="mt-4 max-w-[62ch] text-[14px] leading-relaxed text-muted">
                      {item.a}
                    </p>
                  </details>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-canvas">
          <div className="mx-auto max-w-6xl px-6 py-28">
            <Reveal>
              <div className="rounded-[10px] border border-line bg-surface px-8 py-14 text-center">
                <h2 className="mx-auto max-w-[18ch] text-title">
                  Bring one document you already know.
                </h2>
                <p className="mx-auto mt-5 max-w-[48ch] text-lede text-ink-soft">
                  The fastest way to know whether the citations are real is to ask
                  something you already know the answer to.
                </p>
                <ButtonLink href="/chat" size="lg" className="mt-9">
                  Try {APP_NAME}
                  <ArrowRight />
                </ButtonLink>
                <p className="mt-5 text-[13px] text-muted">
                  Already have an account?{" "}
                  <Link href="/login" className="text-ink underline underline-offset-4">
                    Sign in
                  </Link>
                </p>
              </div>
            </Reveal>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
