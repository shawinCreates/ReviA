import Image from "next/image";
import Link from "next/link";

import { APP_NAME, APP_TAGLINE } from "@/lib/config";
import {
  ArrowRight,
  Check,
  FileText,
  ReviaMark,
  Search,
  Upload,
} from "@/components/icons";
import { Reveal } from "@/components/reveal";
import { PipelineBoard } from "@/components/pipeline/board";
import { SiteFooter, SiteHeader } from "@/components/chrome";
import { Badge, ButtonLink, Card, Kbd, SectionLabel } from "@/components/ui";

const HERO_IMAGE = "https://picsum.photos/seed/revia-hero/1200/675";
const NOTES_IMAGE = "https://picsum.photos/seed/revia-notes/1024/1280";

// `surface` decides how a bento cell is filled, so the grid is never a run of
// identical white cards: a hairline page texture, a real image, an accent tint.
const FEATURES = [
  {
    title: "Every claim points at a page",
    body: "Sources are resolved against the chunks the model was actually shown. A label it invents is dropped rather than rendered, so a citation can never link to a page that does not support the claim.",
    span: "lg:col-span-2",
    surface: "pattern",
  },
  {
    title: "Two retrieval passes",
    body: "Dense vectors find paraphrase. Postgres full-text finds the acronym that appears once on page 40. Rank-fused, so neither leg can drown the other out.",
    span: "",
    surface: "plain",
  },
  {
    title: "Says it does not know",
    body: "When nothing in your library answers the question, that is the answer. No answering from general knowledge and hoping.",
    span: "",
    surface: "image",
  },
  {
    title: "Your files stay private",
    body: "Objects are stored privately and reached through short-lived signed URLs. No one else can reach your library, and a citation link expires.",
    span: "lg:col-span-2",
    surface: "accent",
  },
  {
    title: "You can watch it work",
    body: "Every upload moves through queued, parsing, chunking, embedding and ready, on a board you can open. Each stage names what it is doing.",
    span: "lg:col-span-3",
    surface: "plain",
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

// Four items, because the grid below is two up: a fifth sat alone in the last
// row. The per-library document count it used to carry is on the pricing card;
// the per-file size limit is on /login and in the chat drop zone.
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
          <div className="relative mx-auto max-w-6xl px-6 pt-12 pb-16 md:pt-20 md:pb-24">
            <Reveal>
              <p className="font-mono text-[11px] tracking-[0.16em] text-accent uppercase">
                2026 &middot; beta
              </p>
            </Reveal>
            <Reveal index={1}>
              {/* Two lines at every width ≥ md: the steps are sized so the
                  tagline measures 1.6 lines of the available measure at md and
                  1.4 at lg, i.e. ~23% and ~42% of headroom before a third line. */}
              <h1 className="mt-5 font-[family-name:var(--font-display)] text-[2rem] leading-[1.06] tracking-[-0.02em] md:text-[2.25rem] lg:text-[3rem]">
                {APP_TAGLINE}
              </h1>
            </Reveal>
            <div className="mt-9 grid gap-10 md:grid-cols-2 md:items-center md:gap-14">
              <Reveal index={2}>
                <p className="max-w-[46ch] text-lede text-ink-soft">
                  Upload slides, papers and notes. Answers come only from what you
                  uploaded, with a page number on every claim.
                </p>
                <div className="mt-8 flex flex-wrap items-center gap-3">
                  <ButtonLink href="/chat" size="lg">
                    Try {APP_NAME}
                    <ArrowRight />
                  </ButtonLink>
                  <ButtonLink href="/login" variant="outline" size="lg">
                    Create an account
                  </ButtonLink>
                </div>
              </Reveal>
              <Reveal index={3}>
                <div className="border border-line bg-sunk">
                  <Image
                    src={HERO_IMAGE}
                    alt="Printed lecture notes spread open on a desk beside a laptop"
                    width={1200}
                    height={675}
                    priority
                    className="w-full"
                  />
                </div>
              </Reveal>
            </div>
          </div>
        </section>

        <section className="border-b border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
            <Reveal>
              <div className="border border-line bg-paper">
                <div className="flex items-center gap-2.5 border-b border-line px-5 py-3.5 md:px-7">
                  <ReviaMark size={15} className="text-accent" />
                  <span className="font-mono text-[11px] tracking-[0.14em] text-faint uppercase">
                    case file &middot; judicial-review
                  </span>
                </div>
                <div className="grid gap-8 px-5 py-7 md:grid-cols-[minmax(0,1fr)_minmax(0,260px)] md:gap-12 md:px-7 md:py-9">
                  <div>
                    <p className="font-mono text-[10px] tracking-[0.14em] text-faint uppercase">
                      question
                    </p>
                    <p className="mt-3 max-w-[40ch] text-[19px] leading-snug text-ink md:text-[21px]">
                      Does a minister exercising a statutory duty get the same review?
                    </p>
                    <p className="mt-6 max-w-[62ch] text-[14px] leading-relaxed text-ink-soft">
                      Yes. A minister exercising a statutory duty is a public body for
                      this purpose{" "}
                      <span className="font-mono text-accent">[S1]</span>. What changes
                      is the intensity of the review: a decision taken under a wide
                      discretion is examined for rationality only, not correctness{" "}
                      <span className="font-mono text-accent">[S2]</span>.
                    </p>
                  </div>
                  <div className="space-y-3 md:border-l md:border-line md:pl-8">
                    <div className="border border-line bg-surface p-4">
                      <p className="font-mono text-[10px] tracking-[0.12em] text-accent uppercase">
                        S1 &middot; p. 7
                      </p>
                      <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                        Public bodies include ministers exercising statutory duties.
                      </p>
                    </div>
                    <div className="border border-line bg-surface p-4">
                      <p className="font-mono text-[10px] tracking-[0.12em] text-accent uppercase">
                        S2 &middot; p. 9
                      </p>
                      <p className="mt-1.5 text-[12px] leading-relaxed text-muted">
                        Wider discretion narrows the court to a rationality review.
                      </p>
                    </div>
                  </div>
                </div>
                <div className="grid gap-6 border-t border-line px-5 py-6 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)] md:px-7 md:py-7">
                  <div>
                    <SectionLabel>Why it holds up</SectionLabel>
                  </div>
                  <div>
                    <p className="max-w-[60ch] text-[14px] leading-relaxed text-ink-soft">
                      A citation is a database lookup, not a string the model wrote.
                      If a label does not resolve, the sentence renders uncited rather
                      than linked.
                    </p>
                    <Card className="mt-5 inline-flex items-center gap-3 px-4 py-3">
                      <span className="text-[12px] text-muted">Ask with</span>
                      <Kbd>/</Kbd>
                      <span className="text-[12px] text-faint">
                        to focus the composer
                      </span>
                    </Card>
                  </div>
                </div>
              </div>
            </Reveal>
          </div>
        </section>

        <section id="how" className="scroll-mt-20 border-b border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
            <Reveal>
              <h2 className="max-w-[22ch] text-title">
                Four steps, then it is just answering questions.
              </h2>
            </Reveal>
            <ol className="mt-12 border-t border-line md:mt-14">
              {STEPS.map((step, index) => (
                <Reveal
                  as="li"
                  key={step.label}
                  index={index}
                  className={`border-b border-line ${index % 2 === 1 ? "md:pl-16" : ""}`}
                >
                  <div className="grid items-baseline gap-x-6 gap-y-3 py-8 md:grid-cols-[minmax(0,150px)_minmax(0,1fr)] md:py-9">
                    <p className="font-[family-name:var(--font-display)] text-[34px] leading-none text-accent">
                      0{index + 1}
                    </p>
                    <div className="md:max-w-[54ch]">
                      <div className="flex items-center gap-2.5">
                        <step.icon size={17} className="text-ink" />
                        <p className="text-[16px] text-ink">{step.label}</p>
                      </div>
                      <p className="mt-2.5 text-[14px] leading-relaxed text-muted">
                        {step.body}
                      </p>
                    </div>
                  </div>
                </Reveal>
              ))}
            </ol>
          </div>
        </section>

        <section id="features" className="scroll-mt-20 border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
            <Reveal>
              <h2 className="max-w-[26ch] text-title">
                Built around the failure modes of a chat tool that quotes itself.
              </h2>
            </Reveal>
            <div className="mt-12 grid gap-4 md:mt-14 md:grid-cols-2 lg:grid-cols-3">
              {FEATURES.map((feature, index) => (
                <Reveal key={feature.title} index={index} className={feature.span}>
                  <div
                    className={[
                      "flex h-full flex-col border border-line p-7 md:p-8",
                      feature.surface === "accent" ? "bg-accent-soft justify-center" : "bg-surface",
                      feature.surface === "pattern" ? "hairline-grid justify-center" : "",
                    ].join(" ")}
                  >
                    {feature.surface === "image" ? (
                      <Image
                        src={NOTES_IMAGE}
                        alt="A stack of open notebooks and reading glasses left on a table"
                        width={1024}
                        height={1280}
                        className="mb-7 w-full max-h-[440px] border border-line object-cover"
                      />
                    ) : null}
                    <h3 className="text-[17px] leading-snug text-ink">
                      {feature.title}
                    </h3>
                    <p className="mt-3 text-[14px] leading-relaxed text-muted">
                      {feature.body}
                    </p>
                  </div>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
            <Reveal>
              <SectionLabel>Ingestion</SectionLabel>
              <div className="mt-4 flex flex-wrap items-end justify-between gap-6">
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
            <div className="mt-12 border-t border-line pt-10 md:mt-14">
              <PipelineBoard />
            </div>
          </div>
        </section>

        <section id="pricing" className="scroll-mt-20 border-b border-line bg-surface">
          <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
            <div className="grid gap-10 md:grid-cols-[minmax(0,260px)_minmax(0,1fr)] md:gap-14">
              <Reveal>
                <h2 className="max-w-[14ch] text-title">Free while it is in beta.</h2>
              </Reveal>
              <div className="grid border-t border-line md:grid-cols-2">
                {PLANS.map((plan, index) => (
                  <Reveal
                    key={plan.name}
                    index={index}
                    className={`py-9 md:px-8 ${index === 0 ? "md:pl-0" : "md:border-l md:pr-0"}`}
                  >
                    <div className="flex items-center justify-between gap-4">
                      <p className={`text-[15px] ${plan.highlight ? "text-accent" : "text-ink"}`}>
                        {plan.name}
                      </p>
                      {plan.highlight ? (
                        <Badge tone="accent">Planned</Badge>
                      ) : (
                        <Badge>Beta</Badge>
                      )}
                    </div>
                    <p className="mt-8 text-[44px] leading-none font-medium tracking-[-0.03em] text-ink">
                      {plan.price}
                    </p>
                    <p className="mt-3 max-w-[30ch] text-[13px] text-muted">
                      {plan.cadence}
                    </p>
                    <p className="mt-6 text-[14px] leading-relaxed text-ink-soft">
                      {plan.body}
                    </p>
                    <ul className="mt-6 space-y-2.5">
                      {plan.features.map((feature) => (
                        <li
                          key={feature}
                          className="flex items-start gap-2.5 text-[13px] text-muted"
                        >
                          <Check size={15} className="mt-0.5 shrink-0 text-accent" />
                          {feature}
                        </li>
                      ))}
                    </ul>
                    <ButtonLink
                      href={plan.highlight ? "/login" : "/chat"}
                      variant={plan.highlight ? "outline" : "solid"}
                      className="mt-8"
                    >
                      {plan.cta}
                    </ButtonLink>
                  </Reveal>
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="border-b border-line">
          <div className="mx-auto max-w-6xl px-6 py-16 md:py-24">
            <Reveal>
              <h2 className="max-w-[24ch] text-title">Before you upload anything.</h2>
            </Reveal>
            <ul className="mt-12 grid gap-x-12 gap-y-10 md:mt-14 md:grid-cols-2">
              {FAQ.map((item, index) => (
                <Reveal as="li" key={item.q} index={index} className="border-t border-line pt-5">
                  <p className="text-[15px] leading-snug text-ink">{item.q}</p>
                  <p className="mt-3 max-w-[54ch] text-[13px] leading-relaxed text-muted">
                    {item.a}
                  </p>
                </Reveal>
              ))}
            </ul>
          </div>
        </section>

        <section className="border-t-2 border-accent bg-accent-soft">
          <div className="mx-auto max-w-3xl px-6 py-20 text-center md:py-28">
            <Reveal>
              <h2 className="text-[1.75rem] leading-[1.1] tracking-[-0.02em] font-[family-name:var(--font-display)] md:text-[2.25rem]">
                Bring one document you already know.
              </h2>
              <p className="mx-auto mt-6 max-w-[46ch] text-lede text-ink-soft">
                The fastest way to know whether the citations are real is to ask
                something you already know the answer to.
              </p>
              <ButtonLink href="/chat" size="lg" className="mt-9">
                Try {APP_NAME}
                <ArrowRight />
              </ButtonLink>
              <p className="mt-6 text-[13px] text-muted">
                Already have an account?{" "}
                <Link href="/login" className="text-accent underline underline-offset-4">
                  Sign in
                </Link>
              </p>
            </Reveal>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}
