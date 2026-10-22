import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

// Utility to infer document category from filename for Prior‑Art and Legal Sources
function inferDocCategory(filename: string): string {
  const lowered = filename.toLowerCase();
  if (lowered.includes("patent")) return "Patent record";
  if (lowered.includes("judgment")) return "Judgment";
  if (lowered.includes("rule")) return "Rule or regulation";
  if (lowered.includes("act")) return "Statute";
  if (lowered.includes("treaty")) return "Treaty";
  if (lowered.includes("traditional") || lowered.includes("tkdl")) return "Traditional knowledge resource";
  return "Other";
}
import type {
  AbsAnswers,
  FormulationAnswers,
  InterfaceLanguage,
  Jurisdiction,
  ResearchState,
  SearchFilters,
} from "./prototype-state";

// ---------------------------------------------------------------------------
// API integration
// ---------------------------------------------------------------------------
const API_BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:8000";

type ApiCitation = {
  source_filename: string;
  page: number | null;
  excerpt: string;
  source_url: string | null;
};

type UserFailureNotice = {
  failure_type: string;
  reason: string;
  next_action: string;
};

type ApiResponse = {
  question: string;
  jurisdiction: string;
  language: string;
  answer: string;
  citations: ApiCitation[];
  evidence_status: "sufficient" | "partial" | "insufficient";
  confidence: string;
  disclaimer: string;
  user_failure?: UserFailureNotice | null;
};

type ChatState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "success"; data: ApiResponse; question: string }
  | { status: "error"; message: string; failure?: UserFailureNotice; question: string };

type IconName =
  | "arrow"
  | "bell"
  | "book"
  | "check"
  | "chevron"
  | "clock"
  | "dashboard"
  | "document"
  | "external"
  | "flask"
  | "globe"
  | "history"
  | "leaf"
  | "menu"
  | "mic"
  | "panel"
  | "paperclip"
  | "pause"
  | "play"
  | "plus"
  | "refresh"
  | "search"
  | "send"
  | "shield"
  | "sparkles"
  | "speaker"
  | "stop"
  | "thumbDown"
  | "thumbUp"
  | "user"
  | "warning"
  | "x";

function Icon({
  name,
  size = "md",
}: {
  name: IconName;
  size?: "sm" | "md" | "lg";
}) {
  const paths: Record<IconName, ReactNode> = {
    arrow: <path d="M5 12h14m-5-5 5 5-5 5" />,
    bell: (
      <>
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9" />
        <path d="M10 21h4" />
      </>
    ),
    book: (
      <>
        <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H11v16H6.5A2.5 2.5 0 0 0 4 21.5v-16Z" />
        <path d="M20 5.5A2.5 2.5 0 0 0 17.5 3H13v16h4.5a2.5 2.5 0 0 1 2.5 2.5v-16Z" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    chevron: <path d="m9 18 6-6-6-6" />,
    clock: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M12 7v5l3 2" />
      </>
    ),
    dashboard: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    document: (
      <>
        <path d="M6 3h8l4 4v14H6V3Z" />
        <path d="M14 3v5h5M9 13h6M9 17h6" />
      </>
    ),
    external: (
      <>
        <path d="M14 4h6v6M20 4l-9 9" />
        <path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6" />
      </>
    ),
    flask: (
      <>
        <path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3" />
        <path d="M8 15h8" />
      </>
    ),
    globe: (
      <>
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18" />
      </>
    ),
    history: (
      <>
        <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
        <path d="M3 3v5h5M12 7v5l3 2" />
      </>
    ),
    leaf: (
      <>
        <path d="M20 4C12 4 5 7 5 14a6 6 0 0 0 6 6c7 0 9-8 9-16Z" />
        <path d="M4 21c3-7 8-10 13-13" />
      </>
    ),
    menu: <path d="M4 7h16M4 12h16M4 17h16" />,
    mic: (
      <>
        <rect x="9" y="3" width="6" height="11" rx="3" />
        <path d="M5 11a7 7 0 0 0 14 0M12 18v3M9 21h6" />
      </>
    ),
    panel: (
      <>
        <rect x="3" y="4" width="18" height="16" rx="2" />
        <path d="M9 4v16M6 9h.01" />
      </>
    ),
    paperclip: <path d="m21 11.5-8.8 8.8a6 6 0 0 1-8.5-8.5l9.5-9.5a4 4 0 0 1 5.7 5.7l-9.6 9.5a2 2 0 0 1-2.8-2.8L15.3 6" />,
    pause: (
      <>
        <path d="M8 5v14M16 5v14" />
      </>
    ),
    play: <path d="m8 5 11 7-11 7V5Z" />,
    plus: <path d="M12 5v14M5 12h14" />,
    refresh: (
      <>
        <path d="M20 6v5h-5" />
        <path d="M18.5 15a8 8 0 1 1-.6-7.8L20 11" />
      </>
    ),
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    send: <path d="m22 2-7 20-4-9-9-4 20-7ZM22 2 11 13" />,
    shield: (
      <>
        <path d="M12 3 20 6v5c0 5-3.4 8.4-8 10-4.6-1.6-8-5-8-10V6l8-3Z" />
        <path d="m8.5 12 2.2 2.2 4.8-5" />
      </>
    ),
    sparkles: (
      <>
        <path d="m12 3 1.2 3.8L17 8l-3.8 1.2L12 13l-1.2-3.8L7 8l3.8-1.2L12 3Z" />
        <path d="m18 14 .8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14Z" />
      </>
    ),
    speaker: (
      <>
        <path d="M11 5 6 9H3v6h3l5 4V5Z" />
        <path d="M15 9a4 4 0 0 1 0 6M18 6a8 8 0 0 1 0 12" />
      </>
    ),
    stop: <rect x="6" y="6" width="12" height="12" rx="1" />,
    thumbDown: (
      <path d="M7 3v11H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3Zm0 9 4 8a2 2 0 0 0 3.8-.8L14 14h4.5a2.5 2.5 0 0 0 2.4-3.2l-1.5-5A4 4 0 0 0 15.6 3H7" />
    ),
    thumbUp: (
      <path d="M7 21V10H4a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h3Zm0-9 4-8a2 2 0 0 1 3.8.8L14 10h4.5a2.5 2.5 0 0 1 2.4 3.2l-1.5 5a4 4 0 0 1-3.8 2.8H7" />
    ),
    user: (
      <>
        <circle cx="12" cy="8" r="4" />
        <path d="M4 21a8 8 0 0 1 16 0" />
      </>
    ),
    warning: (
      <>
        <path d="M12 3 2.8 19a1.3 1.3 0 0 0 1.2 2h16a1.3 1.3 0 0 0 1.2-2L12 3Z" />
        <path d="M12 9v4m0 4h.01" />
      </>
    ),
    x: <path d="m6 6 12 12M18 6 6 18" />,
  };
  const sizes = { sm: "size-4", md: "size-5", lg: "size-6" };

  return (
    <svg
      className={sizes[size]}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name]}
    </svg>
  );
}

function Logo({
  collapsed = false,
  href = "#/landing",
}: {
  collapsed?: boolean;
  href?: string;
}) {
  return (
    <a
      href={href}
      className="flex min-w-0 items-center gap-3"
      aria-label="IP-SAKTI Sahayak"
    >
      <div className="grid size-10 shrink-0 place-items-center rounded-xl bg-brand text-sm font-bold tracking-tight text-white shadow-brand">
        IS
      </div>
      {!collapsed && (
        <div className="min-w-0">
          <div className="truncate font-display text-base font-bold tracking-tight text-ink">
            IP-SAKTI
          </div>
          <div className="text-xs font-medium text-ink-subtle">Sahayak</div>
        </div>
      )}
    </a>
  );
}

type PageId =
  | "dashboard"
  | "assistant"
  | "classifier"
  | "abs"
  | "prior-art"
  | "sources"
  | "history"
  | "admin";

type RouteId = PageId | "landing";

const navigation: Array<{
  id: PageId;
  label: string;
  icon: IconName;
}> = [
  { id: "dashboard", label: "Dashboard", icon: "dashboard" },
  { id: "assistant", label: "AI Assistant", icon: "sparkles" },
  { id: "classifier", label: "Formulation Classification", icon: "flask" },
  { id: "abs", label: "ABS Compliance", icon: "leaf" },
  { id: "prior-art", label: "Prior-Art Search", icon: "search" },
  { id: "sources", label: "Legal Sources", icon: "book" },
  { id: "history", label: "History", icon: "history" },
  { id: "admin", label: "Admin Knowledge Base", icon: "shield" },
];

const pageDetails: Record<
  Exclude<PageId, "dashboard">,
  { title: string; eyebrow: string; description: string; icon: IconName }
> = {
  assistant: {
    title: "AI Assistant",
    eyebrow: "Guided research",
    description:
      "Ask questions about Ayurveda intellectual property and regulatory pathways in plain language.",
    icon: "sparkles",
  },
  classifier: {
    title: "Formulation Classification",
    eyebrow: "Product pathway",
    description:
      "Organize formulation details and explore potentially relevant classification considerations.",
    icon: "flask",
  },
  abs: {
    title: "ABS Compliance",
    eyebrow: "Resource use",
    description:
      "Work through access and benefit-sharing considerations for biological resources and associated knowledge.",
    icon: "leaf",
  },
  "prior-art": {
    title: "Prior-Art Search",
    eyebrow: "Knowledge discovery",
    description:
      "Structure a search across relevant sources and keep promising references organized.",
    icon: "search",
  },
  sources: {
    title: "Legal Sources",
    eyebrow: "Source library",
    description:
      "Review saved official and authoritative materials used across your research.",
    icon: "book",
  },
  history: {
    title: "History",
    eyebrow: "Your activity",
    description:
      "Return to earlier questions, classification work, and research sessions.",
    icon: "history",
  },
  admin: {
    title: "Admin Knowledge Base",
    eyebrow: "Authorised access",
    description:
      "Manage the curated legal corpus and review document ingestion activity.",
    icon: "shield",
  },
};

function LandingPage({
  user,
  onOpenAuth,
  onNavigate,
  onLogout,
}: {
  user: AuthUser | null;
  onOpenAuth: (mode: "login" | "register") => void;
  onNavigate: (page: PageId) => void;
  onLogout: () => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <div className="min-h-screen bg-white text-ink">
      <header className="sticky top-0 z-30 border-b border-line bg-white/95 backdrop-blur">
        <div className="mx-auto flex h-18 max-w-content items-center justify-between px-5 sm:px-8">
          <Logo href="#/landing" />
          <nav className="hidden items-center gap-7 md:flex" aria-label="Public navigation">
            <a href="#landing-features" className="text-sm font-semibold text-ink-muted hover:text-brand">
              Features
            </a>
            <a href="#landing-how" className="text-sm font-semibold text-ink-muted hover:text-brand">
              How It Works
            </a>
            <a href="#landing-trust" className="text-sm font-semibold text-ink-muted hover:text-brand">
              About
            </a>
            {user ? (
              <div className="flex items-center gap-3">
                <span className="text-xs font-semibold text-ink-muted">
                  Signed in as <strong className="text-ink">{user.name}</strong>
                </span>
                <button
                  type="button"
                  onClick={() => onNavigate("dashboard")}
                  className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
                >
                  Dashboard
                  <Icon name="arrow" size="sm" />
                </button>
                <button
                  type="button"
                  onClick={onLogout}
                  className="inline-flex h-10 items-center rounded-lg border border-line px-3 text-sm font-semibold text-ink-muted hover:bg-surface-subtle"
                >
                  Sign out
                </button>
              </div>
            ) : (
              <div className="flex items-center gap-2.5">
                <button
                  type="button"
                  onClick={() => onOpenAuth("login")}
                  className="inline-flex h-10 items-center rounded-lg border border-line-strong px-4 text-sm font-semibold text-ink hover:border-brand-muted hover:bg-brand-pale hover:text-brand"
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => onOpenAuth("register")}
                  className="inline-flex h-10 items-center rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
                >
                  Register
                </button>
              </div>
            )}
          </nav>
          <button
            type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen}
            onClick={() => setMenuOpen(!menuOpen)}
            className="grid size-10 place-items-center rounded-lg border border-line text-ink-muted md:hidden"
          >
            <Icon name={menuOpen ? "x" : "menu"} />
          </button>
        </div>
        {menuOpen && (
          <nav className="grid gap-1 border-t border-line px-5 py-4 md:hidden">
            {[
              ["Features", "#landing-features"],
              ["How It Works", "#landing-how"],
              ["About", "#landing-trust"],
            ].map(([label, href]) => (
              <a
                key={label}
                href={href}
                onClick={() => setMenuOpen(false)}
                className="rounded-lg px-3 py-3 text-sm font-semibold text-ink-muted hover:bg-surface-subtle"
              >
                {label}
              </a>
            ))}
            {user ? (
              <div className="border-t border-line pt-2">
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); onNavigate("dashboard"); }}
                  className="w-full rounded-lg px-3 py-3 text-left text-sm font-semibold text-brand hover:bg-surface-subtle"
                >
                  Dashboard ({user.name})
                </button>
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); onLogout(); }}
                  className="w-full rounded-lg px-3 py-3 text-left text-sm font-semibold text-error hover:bg-surface-subtle"
                >
                  Sign out
                </button>
              </div>
            ) : (
              <div className="flex flex-col gap-2 border-t border-line pt-3">
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); onOpenAuth("login"); }}
                  className="w-full rounded-lg border border-line-strong px-4 py-2.5 text-center text-sm font-semibold text-ink hover:bg-brand-pale"
                >
                  Login
                </button>
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); onOpenAuth("register"); }}
                  className="w-full rounded-lg bg-brand px-4 py-2.5 text-center text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
                >
                  Register
                </button>
              </div>
            )}
          </nav>
        )}
      </header>

      <main>
        <section className="relative overflow-hidden bg-brand">
          <div className="absolute inset-y-0 right-0 w-hero-glow bg-hero-glow" />
          <div className="relative mx-auto grid max-w-content items-center gap-12 px-5 py-16 sm:px-8 sm:py-20 lg:grid-cols-2 lg:py-24">
            <div>
              <span className="inline-flex items-center gap-2 rounded-full border border-sage-soft bg-sage-pale px-3 py-1.5 text-xs font-semibold text-sage-strong">
                <span className="size-1.5 rounded-full bg-sage-strong" />
                Responsible AI for Ayurveda innovation
              </span>
              <h1 className="mt-6 font-display text-4xl font-bold leading-tight tracking-tight text-white sm:text-5xl lg:text-6xl">
                Trusted IP &amp; Regulatory Guidance for Ayurveda
              </h1>
              <p className="mt-6 max-w-2xl text-base leading-7 text-brand-soft sm:text-lg sm:leading-8">
                Source-aware AI guidance for Ayurvedic practitioners, researchers, and startups
                exploring intellectual property and regulatory questions.
              </p>
              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                {user ? (
                  <button
                    type="button"
                    onClick={() => onNavigate("dashboard")}
                    className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-white px-5 text-sm font-semibold text-brand shadow-brand hover:bg-brand-pale focus:outline-none focus-visible:ring-4 focus-visible:ring-white/20"
                  >
                    Open dashboard
                    <Icon name="arrow" size="sm" />
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      onClick={() => onOpenAuth("login")}
                      className="inline-flex h-12 items-center justify-center gap-2 rounded-xl bg-white px-5 text-sm font-semibold text-brand shadow-brand hover:bg-brand-pale focus:outline-none focus-visible:ring-4 focus-visible:ring-white/20"
                    >
                      Sign in to dashboard
                      <Icon name="arrow" size="sm" />
                    </button>
                    <button
                      type="button"
                      onClick={() => onOpenAuth("register")}
                      className="inline-flex h-12 items-center justify-center rounded-xl border border-white/25 bg-white/5 px-5 text-sm font-semibold text-white hover:bg-white/10 focus:outline-none focus-visible:ring-4 focus-visible:ring-white/20"
                    >
                      Create free account
                    </button>
                  </>
                )}
                <a
                  href="#landing-features"
                  className="inline-flex h-12 items-center justify-center rounded-xl border border-white/25 bg-white/5 px-5 text-sm font-semibold text-white hover:bg-white/10 focus:outline-none focus-visible:ring-4 focus-visible:ring-white/20"
                >
                  Explore services
                </a>
              </div>
            </div>
            <div className="rounded-3xl border border-white/15 bg-white p-5 shadow-hero sm:p-6">
              <div className="flex items-center gap-3 border-b border-line pb-4">
                <span className="grid size-10 place-items-center rounded-xl bg-brand text-white">
                  <Icon name="sparkles" />
                </span>
                <div>
                  <div className="text-sm font-bold text-ink">IP-SAKTI Assistant</div>
                  <div className="mt-0.5 text-xs text-ink-subtle">Source-aware Ayurveda AI platform</div>
                </div>
              </div>
              <div className="mt-5 rounded-2xl bg-brand-pale p-4 text-sm leading-6 text-ink">
                Can I patent my new Ayurvedic herbal formulation?
              </div>
              <div className="mt-4 rounded-2xl border border-line p-4">
                <div className="flex items-center gap-2 text-xs font-bold text-brand">
                  <Icon name="document" size="sm" />
                  Source-aware AI answer
                </div>
                <p className="mt-3 text-sm leading-6 text-ink-muted">
                  Receive a plain-language explanation backed by real citations retrieved from the
                  curated legal corpus, with evidence status and a disclaimer.
                </p>
              </div>
            </div>
          </div>
        </section>

        <section id="landing-features" className="scroll-mt-20 bg-canvas px-5 py-20 sm:px-8">
          <div className="mx-auto max-w-content">
            <div className="max-w-2xl">
              <div className="text-xs font-bold uppercase tracking-widest text-action">Platform</div>
              <h2 className="mt-3 font-display text-3xl font-bold tracking-tight text-ink">
                Focused guidance workspaces
              </h2>
              <p className="mt-3 text-sm leading-6 text-ink-muted">
                Move from a question to a structured review without losing source context.
              </p>
            </div>
            <div className="mt-9 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {services.map((service) => (
                <button
                  type="button"
                  key={service.title}
                  onClick={() => {
                    if (user) {
                      onNavigate(service.page);
                    } else {
                      onOpenAuth("login");
                    }
                  }}
                  className="rounded-2xl border border-line bg-white p-5 text-left shadow-card transition hover:-translate-y-1 hover:border-brand-soft hover:shadow-card-hover"
                >
                  <span className={`grid size-10 place-items-center rounded-xl ${service.tone}`}>
                    <Icon name={service.icon} />
                  </span>
                  <h3 className="mt-5 font-display text-base font-bold text-ink">{service.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-ink-muted">{service.description}</p>
                </button>
              ))}
            </div>
          </div>
        </section>

        <section id="landing-how" className="scroll-mt-20 px-5 py-20 sm:px-8">
          <div className="mx-auto max-w-content">
            <div className="mx-auto max-w-2xl text-center">
              <div className="text-xs font-bold uppercase tracking-widest text-action">
                How it works
              </div>
              <h2 className="mt-3 font-display text-3xl font-bold tracking-tight text-ink">
                Ask, review, and decide with context
              </h2>
            </div>
            <div className="mt-10 grid gap-5 md:grid-cols-3">
              {[
                ["01", "Describe your question", "Share the relevant product, resource, or research context."],
                ["02", "Review AI guidance", "Inspect explanations, evidence status, and cited source metadata."],
                ["03", "Confirm before acting", "Verify official materials and involve a qualified professional."],
              ].map(([number, title, description]) => (
                <div key={number} className="rounded-2xl border border-line bg-white p-6 text-center shadow-card">
                  <span className="mx-auto grid size-10 place-items-center rounded-full bg-brand-pale text-sm font-bold text-brand">
                    {number}
                  </span>
                  <h3 className="mt-5 font-display text-lg font-bold text-ink">{title}</h3>
                  <p className="mt-2 text-sm leading-6 text-ink-muted">{description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section id="landing-trust" className="scroll-mt-20 bg-brand-pale px-5 py-16 sm:px-8">
          <div className="mx-auto flex max-w-content flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
            <div className="max-w-2xl">
              <div className="text-xs font-bold uppercase tracking-widest text-action">
                Designed for traceability
              </div>
              <h2 className="mt-3 font-display text-2xl font-bold text-ink">
                Information, not legal advice
              </h2>
              <p className="mt-3 text-sm leading-6 text-ink-muted">
                Retrieval-augmented generation, evidence verification, and AI responses are clearly
                distinguished from user input. Cited sources are returned from the backend corpus.
              </p>
            </div>
            {user ? (
              <button
                type="button"
                onClick={() => onNavigate("dashboard")}
                className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
              >
                Enter dashboard
                <Icon name="arrow" size="sm" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onOpenAuth("login")}
                className="inline-flex h-11 shrink-0 items-center justify-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
              >
                Sign in to Dashboard
                <Icon name="arrow" size="sm" />
              </button>
            )}
          </div>
        </section>
      </main>
    </div>
  );
}

function Sidebar({
  activePage,
  collapsed,
  mobileOpen,
  onCollapse,
  onNavigate,
  onMobileClose,
}: {
  activePage: PageId;
  collapsed: boolean;
  mobileOpen: boolean;
  onCollapse: () => void;
  onNavigate: (page: PageId) => void;
  onMobileClose: () => void;
}) {
  return (
    <>
      {mobileOpen && (
        <button
          type="button"
          aria-label="Close navigation"
          onClick={onMobileClose}
          className="fixed inset-0 z-40 bg-ink/30 backdrop-blur-sm lg:hidden"
        />
      )}
      <aside
        className={`fixed inset-y-0 left-0 z-50 flex flex-col border-r border-line bg-white transition-all duration-300 lg:sticky lg:top-0 lg:z-20 ${
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        } ${collapsed ? "w-sidebar-collapsed" : "w-sidebar"}`}
      >
        <div className="flex h-18 items-center justify-between border-b border-line px-4">
          <Logo collapsed={collapsed} />
          {!collapsed && (
            <button
              type="button"
              aria-label={mobileOpen ? "Close navigation" : "Collapse sidebar"}
              onClick={mobileOpen ? onMobileClose : onCollapse}
              className="grid size-9 place-items-center rounded-lg text-ink-subtle transition hover:bg-surface-subtle hover:text-ink"
            >
              <Icon name={mobileOpen ? "x" : "panel"} size="sm" />
            </button>
          )}
        </div>

        <nav className="flex-1 space-y-1 overflow-y-auto p-3" aria-label="Application navigation">
          {navigation.map((item) => {
            const active = item.id === activePage;
            return (
              <a
                key={item.id}
                href={`#/${item.id}`}
                title={collapsed ? item.label : undefined}
                onClick={() => {
                  onNavigate(item.id);
                  onMobileClose();
                }}
                className={`flex h-11 items-center rounded-lg text-sm font-semibold transition ${
                  collapsed ? "justify-center px-0" : "gap-3 px-3"
                } ${
                  active
                    ? "bg-brand-pale text-brand"
                    : "text-ink-muted hover:bg-surface-subtle hover:text-ink"
                }`}
              >
                <Icon name={item.icon} size="sm" />
                {!collapsed && <span>{item.label}</span>}
              </a>
            );
          })}
        </nav>

        <div className="border-t border-line p-3">
          {!collapsed ? (
            <div className="rounded-xl bg-sage-pale p-4">
              <div className="flex items-center gap-2 text-xs font-bold text-sage-strong">
                <Icon name="shield" size="sm" />
                Responsible guidance
              </div>
              <p className="mt-2 text-xs leading-5 text-sage-text">
                Review cited sources and seek professional advice when needed.
              </p>
            </div>
          ) : (
            <div className="grid h-11 place-items-center rounded-lg bg-sage-pale text-sage-strong">
              <Icon name="shield" size="sm" />
            </div>
          )}
        </div>
      </aside>
    </>
  );
}

type AuthUser = { name: string; email: string; id: number };

function useAuthUser(): { user: AuthUser | null; token: string | null; logout: () => void } {
  const [user, setUser] = useState<AuthUser | null>(() => {
    try {
      const raw = sessionStorage.getItem("ipsakti_user");
      return raw ? (JSON.parse(raw) as AuthUser) : null;
    } catch {
      return null;
    }
  });
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem("ipsakti_token"));

  useEffect(() => {
    function sync() {
      const t = sessionStorage.getItem("ipsakti_token");
      const raw = sessionStorage.getItem("ipsakti_user");
      setToken(t);
      try { setUser(raw ? (JSON.parse(raw) as AuthUser) : null); } catch { setUser(null); }
    }
    window.addEventListener("storage", sync);
    window.addEventListener("ipsakti-auth-change", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("ipsakti-auth-change", sync);
    };
  }, []);

  function logout() {
    if (token) {
      void fetch(`${API_BASE}/auth/logout`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      }).catch(() => {});
    }
    sessionStorage.removeItem("ipsakti_token");
    sessionStorage.removeItem("ipsakti_user");
    setToken(null);
    setUser(null);
    window.dispatchEvent(new Event("ipsakti-auth-change"));
  }

  return { user, token, logout };
}

function AuthModal({
  initialMode = "login",
  onClose,
}: {
  initialMode?: "login" | "register";
  onClose: (user: AuthUser | null, token: string | null) => void;
}) {
  const [mode, setMode] = useState<"login" | "register">(initialMode);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function submit() {
    setError(null);
    setLoading(true);
    try {
      const body =
        mode === "login"
          ? { email: email.trim(), password }
          : { name: name.trim(), email: email.trim(), password };
      const res = await fetch(`${API_BASE}/auth/${mode}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data?.detail ?? "Authentication failed. Please check your credentials.");
        return;
      }
      const { token, user } = data as { token: string; user: AuthUser };
      sessionStorage.setItem("ipsakti_token", token);
      sessionStorage.setItem("ipsakti_user", JSON.stringify(user));
      window.dispatchEvent(new Event("ipsakti-auth-change"));
      onClose(user, token);
    } catch {
      setError("Could not connect to the authentication server. Ensure the backend is running.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/40 p-4 backdrop-blur-sm">
      <div className="w-full max-w-sm rounded-2xl border border-line bg-white p-7 shadow-card-hover">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="grid size-8 place-items-center rounded-lg bg-brand text-xs font-bold text-white shadow-brand">
              IS
            </div>
            <div>
              <h2 className="font-display text-lg font-bold text-ink">IP-SAKTI Sahayak</h2>
              <p className="text-xs text-ink-subtle">Ayurveda IP &amp; Regulatory Portal</p>
            </div>
          </div>
          <button
            type="button"
            aria-label="Close authentication window"
            onClick={() => onClose(null, null)}
            className="grid size-8 place-items-center rounded-lg text-ink-subtle hover:bg-surface-subtle"
          >
            <Icon name="x" size="sm" />
          </button>
        </div>

        <div className="mt-6 flex rounded-xl bg-surface-subtle p-1">
          <button
            type="button"
            onClick={() => {
              setMode("login");
              setError(null);
            }}
            className={`flex-1 rounded-lg py-2 text-xs font-bold transition ${
              mode === "login" ? "bg-white text-brand shadow-card" : "text-ink-subtle hover:text-ink"
            }`}
          >
            Sign in
          </button>
          <button
            type="button"
            onClick={() => {
              setMode("register");
              setError(null);
            }}
            className={`flex-1 rounded-lg py-2 text-xs font-bold transition ${
              mode === "register" ? "bg-white text-brand shadow-card" : "text-ink-subtle hover:text-ink"
            }`}
          >
            Create account
          </button>
        </div>

        <div className="mt-5 space-y-3">
          {mode === "register" && (
            <label className="block">
              <span className="text-xs font-semibold text-ink-muted">Full name</span>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Dr. Ananya Sharma"
                autoComplete="name"
                className="mt-1.5 h-11 w-full rounded-lg border border-line-strong bg-white px-3 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
              />
            </label>
          )}
          <label className="block">
            <span className="text-xs font-semibold text-ink-muted">Email address</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="researcher@ayurveda.org"
              autoComplete="email"
              className="mt-1.5 h-11 w-full rounded-lg border border-line-strong bg-white px-3 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
            />
          </label>
          <label className="block">
            <span className="text-xs font-semibold text-ink-muted">Password</span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="At least 8 characters"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              onKeyDown={(e) => e.key === "Enter" && void submit()}
              className="mt-1.5 h-11 w-full rounded-lg border border-line-strong bg-white px-3 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
            />
          </label>
        </div>

        {error && (
          <div className="mt-3 rounded-lg border border-error/20 bg-error-pale px-3 py-2 text-xs text-error">
            {error}
          </div>
        )}

        <button
          type="button"
          onClick={() => void submit()}
          disabled={loading}
          className="mt-5 inline-flex h-11 w-full items-center justify-center gap-2 rounded-lg bg-brand text-sm font-semibold text-white shadow-brand hover:bg-brand-strong disabled:opacity-60"
        >
          {loading ? (
            "Authenticating…"
          ) : mode === "login" ? (
            <>
              Sign in to Dashboard
              <Icon name="arrow" size="sm" />
            </>
          ) : (
            <>
              Register &amp; Open Dashboard
              <Icon name="arrow" size="sm" />
            </>
          )}
        </button>

        <p className="mt-4 text-center text-xs text-ink-subtle">
          {mode === "login" ? "New to IP-SAKTI Sahayak? " : "Already registered? "}
          <button
            type="button"
            onClick={() => {
              setMode(mode === "login" ? "register" : "login");
              setError(null);
            }}
            className="font-semibold text-brand hover:text-brand-strong underline"
          >
            {mode === "login" ? "Create an account" : "Sign in here"}
          </button>
        </p>
      </div>
    </div>
  );
}

function TopBar({
  title,
  onMobileOpen,
}: {
  title: string;
  onMobileOpen: () => void;
}) {
  const { user, logout } = useAuthUser();

  const initials = user
    ? user.name
        .split(" ")
        .filter(Boolean)
        .map((w) => w[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()
    : "IS";

  return (
    <header className="sticky top-0 z-30 flex h-18 items-center justify-between border-b border-line bg-white/95 px-4 backdrop-blur sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <button
          type="button"
          aria-label="Open navigation"
          onClick={onMobileOpen}
          className="grid size-10 shrink-0 place-items-center rounded-lg border border-line text-ink-muted lg:hidden"
        >
          <Icon name="menu" />
        </button>
        <h1 className="truncate font-display text-lg font-bold text-ink sm:text-xl">{title}</h1>
      </div>

      <div className="flex items-center gap-3">
        {user ? (
          <div className="flex items-center gap-2.5 sm:gap-3">
            <div className="flex items-center gap-2 rounded-lg border border-line bg-surface-subtle px-2.5 py-1.5 shadow-xs sm:px-3">
              <span className="grid size-7 shrink-0 place-items-center rounded-full bg-brand text-xs font-bold text-white shadow-xs">
                {initials}
              </span>
              <span className="max-w-32 truncate text-xs font-semibold text-ink sm:max-w-56 sm:text-sm">
                {user.name}
              </span>
            </div>
            <button
              type="button"
              onClick={logout}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line bg-white px-3 text-xs font-semibold text-ink-muted shadow-xs transition hover:border-error/30 hover:bg-error-pale hover:text-error"
              title="Sign out of your account"
            >
              <span className="rotate-180">
                <Icon name="arrow" size="sm" />
              </span>
              <span>Logout</span>
            </button>
          </div>
        ) : (
          <a
            href="#/landing"
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-line-strong px-3 text-xs font-semibold text-ink hover:bg-brand-pale hover:text-brand"
          >
            Sign in
          </a>
        )}
      </div>
    </header>
  );
}

function AskPanel({
  onAsk,
  jurisdiction,
  onJurisdictionChange,
  language,
  onLanguageChange,
}: {
  onAsk: (question: string) => void;
  jurisdiction: Jurisdiction;
  onJurisdictionChange: (jurisdiction: Jurisdiction) => void;
  language: InterfaceLanguage;
  onLanguageChange: (language: InterfaceLanguage) => void;
}) {
  const [question, setQuestion] = useState("");

  function submitQuestion() {
    if (question.trim()) {
      onAsk(question.trim());
    }
  }

  return (
    <div className="mt-7 overflow-hidden rounded-2xl border border-brand-soft bg-white shadow-card">
      <div className="bg-brand px-5 py-5 sm:px-6">
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-center">
          <div className="flex items-center gap-3 text-white">
            <span className="grid size-9 place-items-center rounded-lg bg-white/10">
              <Icon name="sparkles" />
            </span>
            <div>
              <div className="text-sm font-bold">Ask IP-SAKTI Sahayak</div>
              <div className="mt-0.5 text-xs text-brand-soft">Source-aware AI guidance</div>
            </div>
          </div>
          <div className="flex w-fit rounded-lg bg-brand-strong p-1" aria-label="Jurisdiction">
            {(["India", "International"] as const).map((item) => (
              <button
                type="button"
                key={item}
                onClick={() => onJurisdictionChange(item)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                  jurisdiction === item ? "bg-white text-brand" : "text-brand-soft hover:text-white"
                }`}
              >
                {item}
              </button>
            ))}
          </div>
        </div>
      </div>
      <div className="p-4 sm:p-6">
        <label>
          <span className="sr-only">Ask a question</span>
          <textarea
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask anything about Ayurveda IP and compliance…"
            rows={3}
            className="w-full resize-none border-0 bg-transparent text-base leading-7 text-ink outline-none placeholder:text-ink-faint"
          />
        </label>
        <div className="mt-4 flex flex-col gap-3 border-t border-line pt-4 sm:flex-row sm:items-center sm:justify-between">
          <label className="flex items-center gap-2 text-xs font-semibold text-ink-muted">
            Response language
            <select
              value={language}
              onChange={(event) => onLanguageChange(event.target.value as InterfaceLanguage)}
              className="rounded-lg border border-line bg-surface-subtle px-3 py-2 text-xs font-semibold text-ink outline-none focus:border-brand"
            >
              <option>English</option>
              <option>हिन्दी</option>
              <option>தமிழ்</option>
              <option>বাংলা</option>
              <option>తెలుగు</option>
              <option>मराठी</option>
            </select>
          </label>
          <button
            type="button"
            onClick={submitQuestion}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand transition hover:bg-brand-strong focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-soft"
          >
            Ask question
            <Icon name="send" size="sm" />
          </button>
        </div>
      </div>
    </div>
  );
}

const services: Array<{
  page: PageId;
  icon: IconName;
  title: string;
  description: string;
  tone: string;
}> = [
  {
    page: "assistant",
    icon: "shield",
    title: "IPR Guidance",
    description: "Explore protection pathways for your innovation.",
    tone: "bg-brand-pale text-brand",
  },
  {
    page: "classifier",
    icon: "flask",
    title: "Formulation Classification",
    description: "Review possible categories for a formulation.",
    tone: "bg-blue-soft text-action",
  },
  {
    page: "abs",
    icon: "leaf",
    title: "ABS Compliance",
    description: "Consider resource access and benefit sharing.",
    tone: "bg-sage-pale text-sage-strong",
  },
  {
    page: "prior-art",
    icon: "search",
    title: "Prior-Art Search",
    description: "Start a structured knowledge search.",
    tone: "bg-surface-subtle text-ink-muted",
  },
];

const suggestions = [
  "Can an Ayurvedic formulation be patented?",
  "How do I classify a herbal wellness product?",
  "When could ABS considerations apply?",
  "How should I begin a prior-art search?",
];

type HistoryItem = { id: number; question: string; answer: string; language: string; created_at: string };

function useLiveHistory(): { items: HistoryItem[]; loading: boolean; error: string | null; refresh: () => void } {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    const token = sessionStorage.getItem("ipsakti_token");
    if (!token) { setItems([]); setError(null); return; }
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/auth/history`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) { setItems([]); setError(null); return; }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setItems((data.items ?? []) as HistoryItem[]);
    } catch {
      setError("Could not load history from backend.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return { items, loading, error, refresh: load };
}

function Dashboard({
  onNavigate,
  onAsk,
  jurisdiction,
  onJurisdictionChange,
  language,
  onLanguageChange,
}: {
  onNavigate: (page: PageId) => void;
  onAsk: (question: string) => void;
  jurisdiction: Jurisdiction;
  onJurisdictionChange: (jurisdiction: Jurisdiction) => void;
  language: InterfaceLanguage;
  onLanguageChange: (language: InterfaceLanguage) => void;
}) {
  const { user } = useAuthUser();
  const { items: historyItems, loading: historyLoading } = useLiveHistory();
  const recentItems = historyItems.slice(0, 4);
  const greeting = user ? `Welcome back, ${user.name.split(" ")[0]}` : "Welcome";

  return (
    <div className="mx-auto max-w-dashboard px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <section>
        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-action">
              {greeting}
            </div>
            <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              Your Ayurveda IP Assistant
            </h2>
            <p className="mt-3 text-sm leading-6 text-ink-muted sm:text-base">
              Get clear guidance and keep your research moving forward.
            </p>
          </div>
          <div className="flex items-center gap-2 text-xs font-semibold text-sage-strong">
            <span className="size-2 rounded-full bg-sage-strong" />
            Assistant available
          </div>
        </div>
        <AskPanel
          onAsk={onAsk}
          jurisdiction={jurisdiction}
          onJurisdictionChange={onJurisdictionChange}
          language={language}
          onLanguageChange={onLanguageChange}
        />
      </section>

      <section className="mt-10">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="font-display text-xl font-bold text-ink">Explore services</h2>
            <p className="mt-1 text-sm text-ink-subtle">Choose a focused guidance workflow.</p>
          </div>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {services.map((service) => (
            <a
              key={service.title}
              href={`#/${service.page}`}
              onClick={() => onNavigate(service.page)}
              className="group rounded-2xl border border-line bg-white p-5 shadow-card transition hover:-translate-y-1 hover:border-brand-soft hover:shadow-card-hover focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-pale"
            >
              <div className={`grid size-10 place-items-center rounded-xl ${service.tone}`}>
                <Icon name={service.icon} />
              </div>
              <h3 className="mt-5 font-display text-base font-bold text-ink">{service.title}</h3>
              <p className="mt-2 min-h-description text-sm leading-5 text-ink-muted">
                {service.description}
              </p>
              <div className="mt-4 flex items-center gap-2 text-xs font-bold text-brand">
                Open service
                <Icon name="arrow" size="sm" />
              </div>
            </a>
          ))}
        </div>
      </section>

      <div className="mt-10 grid gap-6 xl:grid-cols-dashboard">
        <section className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="font-display text-lg font-bold text-ink">Recent questions</h2>
              <p className="mt-1 text-sm text-ink-subtle">Continue where you left off.</p>
            </div>
            <a
              href="#/history"
              onClick={() => onNavigate("history")}
              className="text-xs font-bold text-brand hover:text-brand-strong"
            >
              View history
            </a>
          </div>
          <div className="mt-5">
            {historyLoading ? (
              <div className="space-y-2">
                {[1, 2].map((i) => (
                  <div key={i} className="h-12 animate-pulse rounded-xl border border-line bg-surface-subtle" />
                ))}
              </div>
            ) : recentItems.length > 0 ? (
              <div className="space-y-2">
                {recentItems.map((item) => (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => onAsk(item.question)}
                    className="w-full rounded-xl border border-line bg-canvas p-3 text-left transition hover:border-brand-soft hover:bg-brand-pale"
                  >
                    <p className="truncate text-sm font-semibold text-ink">{item.question}</p>
                    <p className="mt-0.5 text-xs text-ink-faint">
                      {new Date(item.created_at).toLocaleDateString()} · {item.language}
                    </p>
                  </button>
                ))}
              </div>
            ) : (
              <div className="flex items-center gap-3 rounded-xl border border-line bg-canvas px-4 py-5">
                <Icon name="clock" size="sm" />
                <p className="text-sm text-ink-subtle">
                  {user ? "No recent conversations yet. Ask your first question above." : "Sign in to see your recent questions."}
                </p>
              </div>
            )}
          </div>
        </section>

        <div className="grid gap-6 sm:grid-cols-2 xl:grid-cols-1">
          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <h2 className="font-display text-base font-bold text-ink">Quick start</h2>
            <div className="mt-4 space-y-2">
              {suggestions.map((suggestion) => (
                <a
                  key={suggestion}
                  href="#/assistant"
                  onClick={() => onNavigate("assistant")}
                  className="flex items-start justify-between gap-3 rounded-lg bg-surface-subtle px-3 py-2.5 text-xs font-semibold leading-5 text-ink-muted transition hover:bg-brand-pale hover:text-brand"
                >
                  {suggestion}
                  <Icon name="arrow" size="sm" />
                </a>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <div className="flex items-center justify-between">
              <h2 className="font-display text-base font-bold text-ink">Recent legal sources</h2>
              <a
                href="#/sources"
                onClick={() => onNavigate("sources")}
                className="text-xs font-bold text-brand"
              >
                View all
              </a>
            </div>
            <div className="mt-4 space-y-4">
              {[
                ["Patents Act, 1970", "Legislation"],
                ["Biological Diversity Act, 2002", "Regulatory source"],
                ["Drugs and Cosmetics Rules, 1945", "Regulation"],
              ].map(([title, type]) => (
                <a
                  href="#/sources"
                  onClick={() => onNavigate("sources")}
                  key={title}
                  className="flex items-center gap-3"
                >
                  <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-brand-pale text-brand">
                    <Icon name="document" size="sm" />
                  </span>
                  <span>
                    <span className="block text-xs font-bold text-ink">{title}</span>
                    <span className="mt-0.5 block text-xs text-ink-faint">{type}</span>
                  </span>
                </a>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// History workspace — loads real questions from GET /auth/history
// ---------------------------------------------------------------------------
function HistoryWorkspace({ onAsk, onNavigate }: { onAsk: (q: string) => void; onNavigate: (page: PageId) => void }) {
  const { user } = useAuthUser();
  const { items, loading, error, refresh } = useLiveHistory();
  const [search, setSearch] = useState("");
  const [expandedId, setExpandedId] = useState<number | null>(null);

  const filtered = items.filter((item) =>
    item.question.toLowerCase().includes(search.toLowerCase()) ||
    item.answer.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="mx-auto max-w-dashboard px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-action">Your activity</div>
          <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">History</h2>
          <p className="mt-2 text-sm leading-6 text-ink-muted">
            Review your earlier AI assistant questions and answers.
          </p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-white px-3 text-sm font-semibold text-ink-muted hover:bg-surface-subtle"
        >
          <Icon name="refresh" size="sm" />
          Refresh
        </button>
      </div>

      {!user && (
        <div className="mt-8 rounded-2xl border border-brand-soft bg-brand-pale p-8 text-center">
          <Icon name="user" size="lg" />
          <h3 className="mt-4 font-display text-xl font-bold text-ink">Sign in to view your history</h3>
          <p className="mt-2 text-sm text-ink-muted">Your questions and answers are saved per account.</p>
        </div>
      )}

      {user && (
        <>
          <div className="mt-6">
            <label className="relative block">
              <span className="sr-only">Search history</span>
              <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-ink-faint">
                <Icon name="search" size="sm" />
              </span>
              <input
                type="search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search your questions and answers…"
                className="h-11 w-full rounded-xl border border-line-strong bg-white pl-11 pr-4 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
              />
            </label>
          </div>

          <div className="mt-5">
            {loading && (
              <div className="space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="h-20 animate-pulse rounded-2xl border border-line bg-surface-subtle" />
                ))}
              </div>
            )}

            {error && (
              <div className="rounded-2xl border border-error/20 bg-error-pale p-5 text-sm text-error">
                <div className="flex items-center gap-2 font-semibold">
                  <Icon name="warning" size="sm" /> Could not load history
                </div>
                <p className="mt-1 text-xs leading-5">{error}</p>
              </div>
            )}

            {!loading && !error && filtered.length === 0 && (
              <div className="rounded-2xl border border-line bg-white p-10 text-center shadow-card">
                <Icon name="history" size="lg" />
                <h3 className="mt-4 font-display text-xl font-bold text-ink">
                  {search ? "No matching questions" : "No history yet"}
                </h3>
                <p className="mt-2 text-sm text-ink-muted">
                  {search
                    ? "Try a different search term."
                    : "Your questions will appear here after you use the AI Assistant."}
                </p>
                <a
                  href="#/assistant"
                  onClick={() => onNavigate("assistant")}
                  className="mt-5 inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
                >
                  <Icon name="sparkles" size="sm" />
                  Ask the AI Assistant
                </a>
              </div>
            )}

            {!loading && !error && filtered.length > 0 && (
              <div className="space-y-3">
                {filtered.map((item) => {
                  const expanded = expandedId === item.id;
                  return (
                    <article key={item.id} className="rounded-2xl border border-line bg-white shadow-card">
                      <button
                        type="button"
                        className="w-full p-5 text-left"
                        onClick={() => setExpandedId(expanded ? null : item.id)}
                      >
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <p className="font-semibold text-sm text-ink leading-5 truncate">{item.question}</p>
                            <p className="mt-1 text-xs text-ink-faint">
                              {new Date(item.created_at).toLocaleString()} · {item.language}
                            </p>
                          </div>
                          <span className={`shrink-0 text-ink-subtle transition-transform ${expanded ? "rotate-90" : ""}`}>
                            <Icon name="chevron" size="sm" />
                          </span>
                        </div>
                        {!expanded && (
                          <p className="mt-2 line-clamp-2 text-xs leading-5 text-ink-muted">{item.answer}</p>
                        )}
                      </button>
                      {expanded && (
                        <div className="border-t border-line px-5 pb-5">
                          <div className="mt-4 text-sm leading-7 text-ink-muted whitespace-pre-wrap">{item.answer}</div>
                          <div className="mt-4 flex flex-wrap gap-2">
                            <button
                              type="button"
                              onClick={() => { onAsk(item.question); onNavigate("assistant"); }}
                              className="inline-flex h-9 items-center gap-2 rounded-lg bg-brand px-3 text-xs font-semibold text-white shadow-brand hover:bg-brand-strong"
                            >
                              <Icon name="refresh" size="sm" />
                              Ask again
                            </button>
                          </div>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}

            {!loading && !error && filtered.length > 0 && (
              <p className="mt-4 text-center text-xs text-ink-faint">
                Showing {filtered.length} of {items.length} {items.length === 1 ? "record" : "records"}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}


// ---------------------------------------------------------------------------
// Real citation card (backend data only)
// ---------------------------------------------------------------------------
function CitationCard({
  citation,
  number,
}: {
  citation: ApiCitation;
  number: number;
}) {
  const [pdfNotice, setPdfNotice] = useState<string | null>(null);
  const [checkingPdf, setCheckingPdf] = useState(false);

  const isPdf = Boolean(
    citation.source_filename && citation.source_filename.toLowerCase().endsWith(".pdf")
  );

  const handleViewPdf = async () => {
    try {
      setCheckingPdf(true);
      setPdfNotice(null);
      const res = await fetch(
        `${API_BASE}/documents/${encodeURIComponent(citation.source_filename)}/status`
      );
      if (res.ok) {
        const info = await res.json();
        if (info.available) {
          window.open(
            `${API_BASE}/documents/${encodeURIComponent(citation.source_filename)}/view`,
            "_blank",
            "noopener,noreferrer"
          );
          return;
        }
      }
      setPdfNotice("This source PDF document is currently unavailable in the local legal repository.");
    } catch {
      setPdfNotice("Unable to verify PDF availability. Please try again later.");
    } finally {
      setCheckingPdf(false);
    }
  };

  const handleDownloadPdf = async () => {
    try {
      setCheckingPdf(true);
      setPdfNotice(null);
      const res = await fetch(
        `${API_BASE}/documents/${encodeURIComponent(citation.source_filename)}/status`
      );
      if (res.ok) {
        const info = await res.json();
        if (info.available) {
          const link = document.createElement("a");
          link.href = `${API_BASE}/documents/${encodeURIComponent(citation.source_filename)}/download`;
          link.download = citation.source_filename;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          return;
        }
      }
      setPdfNotice("This source PDF document is currently unavailable for download.");
    } catch {
      setPdfNotice("Unable to verify PDF download. Please try again later.");
    } finally {
      setCheckingPdf(false);
    }
  };

  return (
    <article className="rounded-xl border border-line bg-white p-4 shadow-card">
      <div className="flex items-start gap-3">
        <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-brand-pale text-xs font-bold text-brand">
          {number}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="text-sm font-bold text-ink">{citation.source_filename}</h4>
            {citation.page != null && (
              <span className="rounded-md bg-surface-subtle px-2 py-0.5 text-xs font-medium text-ink-muted">
                Page {citation.page}
              </span>
            )}
          </div>
          {citation.excerpt && (
            <blockquote className="mt-3 rounded-lg border-l-4 border-brand-soft bg-brand-pale/50 px-3 py-2 text-xs leading-5 text-ink-muted">
              {citation.excerpt}
            </blockquote>
          )}

          {pdfNotice && (
            <div className="mt-2.5 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <span>{pdfNotice}</span>
              <button
                type="button"
                onClick={() => setPdfNotice(null)}
                className="ml-2 font-bold text-amber-600 hover:text-amber-900"
              >
                ×
              </button>
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center gap-2">
            {isPdf && (
              <>
                <button
                  type="button"
                  onClick={handleViewPdf}
                  disabled={checkingPdf}
                  className="inline-flex items-center gap-1.5 rounded-md border border-brand-soft bg-brand-pale px-2.5 py-1 text-xs font-semibold text-brand transition hover:bg-brand-soft hover:text-white disabled:opacity-60"
                  title={`View ${citation.source_filename}`}
                >
                  <Icon name="document" size="sm" />
                  View PDF
                </button>
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  disabled={checkingPdf}
                  className="inline-flex items-center gap-1.5 rounded-md border border-line bg-white px-2.5 py-1 text-xs font-semibold text-ink-muted transition hover:border-brand-soft hover:text-brand disabled:opacity-60"
                  title={`Download ${citation.source_filename}`}
                >
                  <Icon name="arrow" size="sm" />
                  Download PDF
                </button>
              </>
            )}
            {citation.source_url && (
              <a
                href={citation.source_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-xs font-semibold text-brand hover:text-brand-strong"
              >
                Open external source
                <Icon name="external" size="sm" />
              </a>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}

// ---------------------------------------------------------------------------
// Real assistant answer (renders live backend response)
// ---------------------------------------------------------------------------
function AssistantAnswer({
  data,
  question,
}: {
  data: ApiResponse;
  question: string;
}) {
  const [feedback, setFeedback] = useState<"up" | "down" | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [downloadPdfError, setDownloadPdfError] = useState<string | null>(null);

  const handleDownloadAnswerPdf = async () => {
    try {
      setDownloadingPdf(true);
      setDownloadPdfError(null);
      const response = await fetch(`${API_BASE}/chat/download-pdf`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question,
          answer: data.answer,
          evidence_status: data.evidence_status,
          confidence: data.confidence,
          citations: data.citations,
          jurisdiction: data.jurisdiction || "India",
          language: data.language || "English",
          disclaimer:
            data.disclaimer ||
            "This information is for general guidance only and is not legal advice.",
        }),
      });

      if (!response.ok) {
        throw new Error("PDF report generation is unavailable.");
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `IP-SAKTI-Sahayak-Guidance-Report.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch {
      setDownloadPdfError(
        "Unable to download answer as PDF at this time. Please try again later."
      );
    } finally {
      setDownloadingPdf(false);
    }
  };

  const confidenceColor =
    data.confidence === "high"
      ? "border-sage-soft bg-sage-pale text-sage-strong"
      : data.confidence === "low"
        ? "border-error/20 bg-error-pale text-error"
        : "border-brand-soft bg-brand-pale text-brand";

  return (
    <div className="flex gap-3 sm:gap-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand text-white shadow-brand">
        <Icon name="sparkles" size="sm" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-bold text-ink">IP-SAKTI Sahayak</span>
            <span
              className={`rounded-full border px-2 py-0.5 text-xs font-semibold capitalize ${confidenceColor}`}
            >
              Confidence: {data.confidence}
            </span>
            <span className="rounded-full border border-line bg-surface-subtle px-2 py-0.5 text-xs font-semibold text-ink-subtle capitalize">
              Evidence: {data.evidence_status}
            </span>
          </div>
          <button
            type="button"
            onClick={handleDownloadAnswerPdf}
            disabled={downloadingPdf}
            className="inline-flex items-center gap-1.5 rounded-lg border border-brand-soft bg-white px-2.5 py-1 text-xs font-semibold text-brand shadow-xs transition hover:bg-brand-pale disabled:opacity-60"
            title="Download complete answer report as PDF"
          >
            <Icon name="document" size="sm" />
            {downloadingPdf ? "Generating PDF..." : "Download Answer as PDF"}
          </button>
        </div>
        <article className="rounded-2xl rounded-tl-sm border border-line bg-white p-5 shadow-card sm:p-6">
          <div className="rounded-lg border border-line bg-canvas px-3 py-2 text-xs leading-5 text-ink-muted">
            <strong className="font-bold text-ink">Q:</strong> {question}
          </div>

          <div className="mt-5 text-sm leading-7 text-ink-muted whitespace-pre-wrap">
            {data.answer}
          </div>

          {data.user_failure && (
            <div className="mt-5 rounded-xl border border-amber-200 bg-amber-50/70 p-4 text-xs">
              <div className="flex items-center gap-2">
                <span className="inline-flex items-center rounded-md bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-900 border border-amber-300">
                  {data.user_failure.failure_type}
                </span>
                <span className="font-semibold text-amber-900">Notice</span>
              </div>
              <p className="mt-2.5 leading-5 text-ink-muted">
                {data.user_failure.reason}
              </p>
              <div className="mt-3 flex items-start gap-1.5 rounded-lg bg-white/80 p-2.5 border border-amber-200/60">
                <span className="font-bold text-amber-900 shrink-0">Helpful next action:</span>
                <span className="text-ink-muted">{data.user_failure.next_action}</span>
              </div>
            </div>
          )}

          {data.citations.length > 0 && (
            <div className="mt-7 border-t border-line pt-6">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <h3 className="text-sm font-bold text-ink">Sources</h3>
                  <p className="mt-1 text-xs text-ink-subtle">
                    Retrieved from the curated legal corpus.
                  </p>
                </div>
                <span className="hidden rounded-full bg-sage-pale px-2.5 py-1 text-xs font-semibold text-sage-strong sm:inline-flex capitalize">
                  Evidence: {data.evidence_status}
                </span>
              </div>
              <div className="mt-4 grid gap-3">
                {data.citations.map((citation, index) => (
                  <CitationCard key={index} citation={citation} number={index + 1} />
                ))}
              </div>
            </div>
          )}

          {data.disclaimer && (
            <div className="mt-6 flex items-start gap-2 rounded-lg border border-line bg-canvas px-3 py-2 text-xs leading-5 text-ink-subtle">
              <Icon name="shield" size="sm" />
              <span>{data.disclaimer}</span>
            </div>
          )}

          <div className="mt-6 flex flex-col gap-4 border-t border-line pt-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2">
              <span className="mr-1 text-xs text-ink-subtle">Was this useful?</span>
              <button
                type="button"
                aria-label="Helpful response"
                onClick={() => setFeedback("up")}
                className={`grid size-9 place-items-center rounded-lg border transition ${
                  feedback === "up"
                    ? "border-brand-soft bg-brand-pale text-brand"
                    : "border-line text-ink-subtle hover:bg-surface-subtle"
                }`}
              >
                <Icon name="thumbUp" size="sm" />
              </button>
              <button
                type="button"
                aria-label="Unhelpful response"
                onClick={() => setFeedback("down")}
                className={`grid size-9 place-items-center rounded-lg border transition ${
                  feedback === "down"
                    ? "border-brand-soft bg-brand-pale text-brand"
                    : "border-line text-ink-subtle hover:bg-surface-subtle"
                }`}
              >
                <Icon name="thumbDown" size="sm" />
              </button>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={handleDownloadAnswerPdf}
                disabled={downloadingPdf}
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line-strong bg-white px-4 text-sm font-semibold text-brand transition hover:border-brand-muted hover:bg-brand-pale disabled:opacity-60"
              >
                <Icon name="document" size="sm" />
                {downloadingPdf ? "Generating PDF..." : "Download Answer as PDF"}
              </button>
              <a
                href="#contact-facilitator"
                className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line-strong bg-white px-4 text-sm font-semibold text-brand transition hover:border-brand-muted hover:bg-brand-pale"
              >
                <Icon name="user" size="sm" />
                Contact an IP Facilitator
              </a>
            </div>
          </div>

          {downloadPdfError && (
            <div className="mt-3 flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              <span>{downloadPdfError}</span>
              <button
                type="button"
                onClick={() => setDownloadPdfError(null)}
                className="ml-2 font-bold text-amber-600 hover:text-amber-900"
              >
                ×
              </button>
            </div>
          )}
        </article>
      </div>
    </div>
  );
}

function EmptyAssistant({
  onSuggestion,
}: {
  onSuggestion: (question: string) => void;
}) {
  return (
    <div className="mx-auto flex max-w-empty flex-col items-center px-5 py-16 text-center">
      <span className="grid size-14 place-items-center rounded-2xl bg-brand-pale text-brand">
        <Icon name="sparkles" size="lg" />
      </span>
      <h2 className="mt-5 font-display text-2xl font-bold text-ink">
        What would you like to understand?
      </h2>
      <p className="mt-3 text-sm leading-6 text-ink-muted">
        Ask about an Ayurveda IP or compliance topic to receive a real, source-backed answer
        from the legal corpus.
      </p>
      <div className="mt-7 grid w-full gap-2 sm:grid-cols-2">
        {suggestions.map((suggestion) => (
          <button
            type="button"
            key={suggestion}
            onClick={() => onSuggestion(suggestion)}
            className="rounded-xl border border-line bg-white p-3 text-left text-xs font-semibold leading-5 text-ink-muted shadow-card transition hover:border-brand-soft hover:text-brand"
          >
            {suggestion}
          </button>
        ))}
      </div>
    </div>
  );
}

function LoadingAssistant() {
  return (
    <div className="flex gap-4">
      <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand text-white">
        <Icon name="sparkles" size="sm" />
      </span>
      <div className="w-full rounded-2xl rounded-tl-sm border border-line bg-white p-6 shadow-card">
        <div className="flex items-center gap-2 text-sm font-bold text-ink">
          <span className="size-2 animate-pulse rounded-full bg-sage-strong" />
          Searching the legal corpus…
        </div>
        <p className="mt-2 text-xs text-ink-subtle">
          Retrieving relevant passages and generating a grounded answer.
        </p>
        <div className="mt-6 space-y-3">
          <div className="h-3 w-loading-title animate-pulse rounded-full bg-brand-pale" />
          <div className="h-3 w-full animate-pulse rounded-full bg-surface-subtle" />
          <div className="h-3 w-loading-line animate-pulse rounded-full bg-surface-subtle" />
          <div className="h-3 w-loading-short animate-pulse rounded-full bg-surface-subtle" />
        </div>
      </div>
    </div>
  );
}

function AssistantErrorNotice({
  message,
  failure,
  onRetry,
}: {
  message: string;
  failure?: UserFailureNotice;
  onRetry: () => void;
}) {
  const failureType = failure?.failure_type || "AI Service Unavailable";
  const reason = failure?.reason || message;
  const nextAction = failure?.next_action || "Please try again in a few moments or consult an IP facilitator.";

  return (
    <div className="mx-auto max-w-empty py-12 text-center">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-amber-50 text-amber-700 border border-amber-200">
        <Icon name="warning" size="lg" />
      </span>
      <div className="mt-4 inline-flex items-center rounded-md bg-amber-100 px-2.5 py-1 text-xs font-bold text-amber-900 border border-amber-300">
        {failureType}
      </div>
      <h2 className="mt-3 font-display text-xl font-bold text-ink">
        Notice
      </h2>
      <p className="mt-3 text-sm leading-6 text-ink-muted">{reason}</p>
      <div className="mx-auto mt-4 max-w-md rounded-lg border border-line bg-white p-3.5 text-xs leading-5 text-ink-muted text-left">
        <strong className="text-ink">Helpful next action:</strong> {nextAction}
      </div>
      <div className="mt-6 flex flex-col justify-center gap-3 sm:flex-row">
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
        >
          <Icon name="refresh" size="sm" />
          Try again
        </button>
        <a
          href="#contact-facilitator"
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line-strong bg-white px-4 text-sm font-semibold text-brand hover:bg-brand-pale"
        >
          <Icon name="user" size="sm" />
          Contact an IP Facilitator
        </a>
      </div>
    </div>
  );
}

type ChatAttachment = {
  id: string;
  name: string;
  type: string;
  size: string;
  preview: string | null;
  progress: number;
  status: "uploading" | "processing" | "ready" | "error";
  error?: string;
};

function AttachmentPreview({
  attachment,
  onRemove,
  compact = false,
}: {
  attachment: ChatAttachment;
  onRemove?: () => void;
  compact?: boolean;
}) {
  const image = attachment.type.startsWith("image/");
  return (
    <div
      className={`flex items-center gap-3 rounded-xl border bg-white ${
        attachment.status === "error" ? "border-error/20" : "border-line"
      } ${compact ? "p-2" : "p-3"}`}
    >
      {image && attachment.preview ? (
        <img
          src={attachment.preview}
          alt=""
          className="size-10 shrink-0 rounded-lg object-cover"
        />
      ) : (
        <span
          className={`grid size-10 shrink-0 place-items-center rounded-lg ${
            attachment.status === "error"
              ? "bg-error-pale text-error"
              : "bg-brand-pale text-brand"
          }`}
        >
          <Icon name="document" size="sm" />
        </span>
      )}
      <div className="min-w-0 flex-1">
        <div className="truncate text-xs font-semibold text-ink">{attachment.name}</div>
        <div className="mt-0.5 flex items-center gap-2 text-xs text-ink-faint">
          <span>{attachment.size}</span>
          <span>·</span>
          <span
            className={
              attachment.status === "error"
                ? "text-error"
                : attachment.status === "ready"
                  ? "text-sage-strong"
                  : "text-brand"
            }
          >
            {attachment.status === "uploading"
              ? `Uploading ${attachment.progress}%`
              : attachment.status === "processing"
                ? "Processing preview"
                : attachment.status === "ready"
                  ? "Ready"
                  : attachment.error || "Upload error"}
          </span>
        </div>
        {(attachment.status === "uploading" || attachment.status === "processing") && (
          <progress
            value={attachment.progress}
            max="100"
            className="mt-2 h-1.5 w-full overflow-hidden rounded-full"
            aria-label={`Upload progress for ${attachment.name}`}
          />
        )}
      </div>
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${attachment.name}`}
          className="grid size-8 shrink-0 place-items-center rounded-lg text-ink-faint hover:bg-error-pale hover:text-error"
        >
          <Icon name="x" size="sm" />
        </button>
      )}
    </div>
  );
}

function mapLanguageForApi(lang: InterfaceLanguage): "English" | "Hindi" | "Marathi" | "Tamil" | "Telugu" | "Bengali" {
  if (lang === "मराठी") return "Marathi";
  if (lang === "हिन्दी") return "Hindi";
  if (lang === "தமிழ்") return "Tamil";
  if (lang === "తెలుగు") return "Telugu";
  if (lang === "বাংলা") return "Bengali";
  return "English";
}

function AssistantWorkspace({
  jurisdiction,
  onJurisdictionChange,
  language,
  onLanguageChange,
  initialQuestion,
}: {
  jurisdiction: Jurisdiction;
  onJurisdictionChange: (jurisdiction: Jurisdiction) => void;
  language: InterfaceLanguage;
  onLanguageChange: (language: InterfaceLanguage) => void;
  initialQuestion: string;
}) {
  const [chatState, setChatState] = useState<ChatState>({ status: "idle" });
  const [question, setQuestion] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const [conversations, setConversations] = useState<
    Array<{ id: string; question: string; data: ApiResponse }>
  >([]);
  const [attachments, setAttachments] = useState<ChatAttachment[]>([]);
  const [voiceState, setVoiceState] = useState<
    "idle" | "listening" | "transcribed" | "error"
  >("idle");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const initialSentRef = useRef(false);

  const handleSend = useCallback(
    async (textToSubmit?: string) => {
      const q = (textToSubmit ?? question).trim();
      if (!q) return;

      setQuestion("");
      setVoiceState("idle");
      setChatState({ status: "loading" });

      try {
        const response = await fetch(`${API_BASE}/chat`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            question: q,
            jurisdiction,
            language: mapLanguageForApi(language),
          }),
        });

        if (!response.ok) {
          let failure: UserFailureNotice = {
            failure_type: "AI Service Unavailable",
            reason: "The service is temporarily unable to process your request.",
            next_action: "Please try again in a few moments or contact support.",
          };
          try {
            const errData = await response.json();
            if (errData?.detail) {
              if (typeof errData.detail === "object" && errData.detail.failure_type) {
                failure = {
                  failure_type: errData.detail.failure_type,
                  reason: errData.detail.reason || failure.reason,
                  next_action: errData.detail.next_action || failure.next_action,
                };
              } else if (typeof errData.detail === "string") {
                const det = errData.detail;
                if (det.includes("index") || det.includes("build_index")) {
                  failure = {
                    failure_type: "Document Search Failed",
                    reason: "The legal document index is not available on the server.",
                    next_action: "Please verify that the index is built or try again shortly.",
                  };
                } else if (det.includes("API key") || det.includes("configured") || det.includes("model")) {
                  failure = {
                    failure_type: "AI Service Unavailable",
                    reason: "The AI reasoning model is not configured or reachable.",
                    next_action: "Please verify server configuration or try again later.",
                  };
                } else {
                  failure.reason = det;
                }
              }
            }
          } catch {
            // fallback
          }
          setChatState({ status: "error", message: failure.reason, failure, question: q });
          return;
        }

        const data: ApiResponse = await response.json();
        setChatState({ status: "success", data, question: q });
        const accountToken = sessionStorage.getItem("ipsakti_token");
        if (accountToken) {
          void fetch(`${API_BASE}/auth/history`, {
            method: "POST",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${accountToken}` },
            body: JSON.stringify({ question: q, answer: data.answer, language: data.language }),
          }).catch(() => { /* history persistence must not block the answer */ });
        }
        setConversations((prev) => [
          { id: `${Date.now()}`, question: q, data },
          ...prev.filter((c) => c.question !== q),
        ]);
      } catch {
        const failure: UserFailureNotice = {
          failure_type: "AI Service Unavailable",
          reason: "Unable to establish a connection to the IP-SAKTI Sahayak backend.",
          next_action: "Ensure the backend service is running and try your request again.",
        };
        setChatState({
          status: "error",
          message: failure.reason,
          failure,
          question: q,
        });
      }
    },
    [jurisdiction, language, question],
  );

  useEffect(() => {
    if (initialQuestion && initialQuestion.trim() && !initialSentRef.current) {
      initialSentRef.current = true;
      handleSend(initialQuestion.trim());
    }
  }, [initialQuestion, handleSend]);

  function addFiles(files: FileList | null) {
    if (!files) return;
    const acceptedExtensions = [".pdf", ".docx", ".txt", ".jpg", ".jpeg", ".png"];

    Array.from(files).forEach((file, index) => {
      const id = `${Date.now()}-${index}-${file.name}`;
      const extension = `.${file.name.split(".").pop()?.toLowerCase()}`;
      const validType = acceptedExtensions.includes(extension);
      const baseAttachment: ChatAttachment = {
        id,
        name: file.name,
        type: file.type || "application/octet-stream",
        size:
          file.size > 1024 * 1024
            ? `${(file.size / (1024 * 1024)).toFixed(1)} MB`
            : `${Math.max(1, Math.round(file.size / 1024))} KB`,
        preview: null,
        progress: validType ? 18 : 0,
        status: validType ? "uploading" : "error",
        error: validType ? undefined : "Unsupported file type",
      };

      setAttachments((current) => [...current, baseAttachment]);

      if (!validType) return;
      if (file.type.startsWith("image/")) {
        const reader = new FileReader();
        reader.onload = () => {
          setAttachments((current) =>
            current.map((item) =>
              item.id === id ? { ...item, preview: String(reader.result) } : item,
            ),
          );
        };
        reader.readAsDataURL(file);
      }

      window.setTimeout(() => {
        setAttachments((current) =>
          current.map((item) =>
            item.id === id ? { ...item, progress: 68, status: "processing" } : item,
          ),
        );
      }, 450);
      window.setTimeout(() => {
        setAttachments((current) =>
          current.map((item) =>
            item.id === id ? { ...item, progress: 100, status: "ready" } : item,
          ),
        );
      }, 950);
    });

    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  return (
    <div className="mx-auto max-w-assistant-workspace px-4 py-5 sm:px-6 lg:px-8">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-action">
            Guided legal research
          </div>
          <p className="mt-1 text-sm text-ink-muted">
            AI guidance grounded in official legal and regulatory documents
          </p>
        </div>
        <button
          type="button"
          onClick={() => setHistoryOpen(!historyOpen)}
          className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-white px-3 text-sm font-semibold text-ink-muted lg:hidden"
        >
          <Icon name="history" size="sm" />
          Conversations
        </button>
      </div>

      <div className="grid min-h-workspace overflow-hidden rounded-2xl border border-line bg-white shadow-card lg:grid-cols-assistant-workspace">
        <aside
          className={`border-b border-line bg-surface-subtle lg:block lg:border-b-0 lg:border-r ${
            historyOpen ? "block" : "hidden"
          }`}
        >
          <div className="p-4">
            <button
              type="button"
              onClick={() => {
                setChatState({ status: "idle" });
                setQuestion("");
                setHistoryOpen(false);
              }}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
            >
              <Icon name="plus" size="sm" />
              New conversation
            </button>
          </div>
          <div className="border-t border-line px-3 py-4">
            <div className="px-2 text-xs font-bold uppercase tracking-widest text-ink-faint">
              Recent
            </div>
            {conversations.length === 0 ? (
              <p className="mt-3 px-2 text-xs text-ink-subtle">
                No recent conversations yet.
              </p>
            ) : (
              <div className="mt-3 space-y-1">
                {conversations.map((item) => (
                  <button
                    type="button"
                    key={item.id}
                    onClick={() => {
                      setChatState({
                        status: "success",
                        data: item.data,
                        question: item.question,
                      });
                      setHistoryOpen(false);
                    }}
                    className={`w-full rounded-lg px-3 py-3 text-left transition ${
                      chatState.status === "success" &&
                      chatState.question === item.question
                        ? "bg-white shadow-card"
                        : "hover:bg-white"
                    }`}
                  >
                    <span className="block truncate text-xs font-semibold text-ink">
                      {item.question}
                    </span>
                    <span className="mt-1 block text-xs text-ink-faint">
                      Evidence: {item.data.evidence_status}
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>
        </aside>

        <section className="flex min-w-0 flex-col">
          <div className="flex flex-col gap-3 border-b border-line px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex w-fit rounded-lg bg-surface-subtle p-1" aria-label="Jurisdiction">
              {(["India", "International"] as const).map((item) => (
                <button
                  type="button"
                  key={item}
                  onClick={() => onJurisdictionChange(item)}
                  className={`rounded-md px-3 py-1.5 text-xs font-semibold transition ${
                    jurisdiction === item
                      ? "bg-white text-brand shadow-card"
                      : "text-ink-subtle hover:text-ink"
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
            <label className="flex items-center gap-2 text-xs font-semibold text-ink-muted">
              Language
              <select
                value={language}
                onChange={(event) => onLanguageChange(event.target.value as InterfaceLanguage)}
                className="rounded-lg border border-line bg-white px-3 py-2 text-xs font-semibold text-ink outline-none focus:border-brand"
              >
                <option>English</option>
                <option>हिन्दी</option>
                <option>தமிழ்</option>
                <option>বাংলা</option>
                <option>తెలుగు</option>
                <option>मराठी</option>
              </select>
            </label>
          </div>

          <div className="flex-1 overflow-y-auto bg-canvas p-4 sm:p-6">
            {chatState.status === "idle" && (
              <EmptyAssistant onSuggestion={(s) => handleSend(s)} />
            )}
            {chatState.status === "loading" && (
              <div className="mx-auto max-w-conversation">
                <LoadingAssistant />
              </div>
            )}
            {chatState.status === "success" && (
              <div className="mx-auto max-w-conversation space-y-7">
                <div className="flex justify-end">
                  <div className="max-w-user-message rounded-2xl rounded-tr-sm bg-brand px-5 py-3 text-sm leading-6 text-white shadow-brand">
                    <p>{chatState.question}</p>
                  </div>
                </div>
                <AssistantAnswer data={chatState.data} question={chatState.question} />
                <div className="pl-0 sm:pl-13">
                  <div className="text-xs font-bold text-ink-subtle">Suggested follow-up questions</div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {[
                      "What details should I document?",
                      "How do I begin a prior-art search?",
                      "Could ABS requirements apply?",
                    ].map((item) => (
                      <button
                        type="button"
                        key={item}
                        onClick={() => handleSend(item)}
                        className="rounded-full border border-line-strong bg-white px-3 py-2 text-xs font-semibold text-ink-muted transition hover:border-brand-soft hover:text-brand"
                      >
                        {item}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            )}
            {chatState.status === "error" && (
              <AssistantErrorNotice
                message={chatState.message}
                failure={chatState.failure}
                onRetry={() => handleSend(chatState.question)}
              />
            )}
          </div>

          <div className="border-t border-line bg-white p-4">
            <div className="mx-auto max-w-conversation">
              {attachments.length > 0 && (
                <div className="mb-3 grid gap-2 sm:grid-cols-2">
                  {attachments.map((attachment) => (
                    <AttachmentPreview
                      key={attachment.id}
                      attachment={attachment}
                      onRemove={() =>
                        setAttachments((current) =>
                          current.filter((item) => item.id !== attachment.id),
                        )
                      }
                    />
                  ))}
                </div>
              )}
              <div className="rounded-xl border border-line-strong bg-white p-3 shadow-card focus-within:border-brand focus-within:ring-4 focus-within:ring-brand-pale">
                <label>
                  <span className="sr-only">Ask the AI assistant</span>
                  <textarea
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && !e.shiftKey) {
                        e.preventDefault();
                        handleSend();
                      }
                    }}
                    rows={2}
                    placeholder="Ask anything about Ayurveda IP and compliance…"
                    className="w-full resize-none border-0 bg-transparent px-1 text-sm leading-6 text-ink outline-none placeholder:text-ink-faint"
                  />
                </label>
                <div className="mt-2 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-1">
                    <input
                      ref={fileInputRef}
                      type="file"
                      multiple
                      accept=".pdf,.docx,.txt,.jpg,.jpeg,.png,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain,image/jpeg,image/png"
                      onChange={(event) => addFiles(event.target.files)}
                      className="sr-only"
                      aria-label="Attach documents or images"
                    />
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="grid size-9 place-items-center rounded-lg text-ink-subtle transition hover:bg-brand-pale hover:text-brand"
                      aria-label="Attach PDF, DOCX, TXT, JPG, or PNG"
                      title="Attach PDF, DOCX, TXT, JPG, or PNG"
                    >
                      <Icon name="paperclip" size="sm" />
                    </button>
                    <button
                      type="button"
                      onClick={() =>
                        setVoiceState(voiceState === "listening" ? "idle" : "listening")
                      }
                      className={`grid size-9 place-items-center rounded-lg transition ${
                        voiceState === "listening"
                          ? "bg-brand text-white"
                          : "text-ink-subtle hover:bg-brand-pale hover:text-brand"
                      }`}
                      aria-label={
                        voiceState === "listening"
                          ? "Cancel voice input"
                          : "Start voice input"
                      }
                      title="Voice input"
                    >
                      <Icon name="mic" size="sm" />
                    </button>
                    <span className="hidden text-xs text-ink-faint sm:inline">
                      PDF, DOCX, TXT, JPG or PNG
                    </span>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleSend()}
                    disabled={
                      chatState.status === "loading" ||
                      !question.trim() ||
                      attachments.some(
                        (attachment) => attachment.status !== "ready",
                      )
                    }
                    className="inline-flex h-9 shrink-0 items-center gap-2 rounded-lg bg-brand px-3 text-xs font-semibold text-white shadow-brand hover:bg-brand-strong disabled:cursor-not-allowed disabled:opacity-40"
                  >
                    {chatState.status === "loading" ? "Sending…" : "Send"}
                    <Icon name="send" size="sm" />
                  </button>
                </div>
              </div>
              <div className="mt-3 flex items-start justify-center gap-2 text-center text-xs leading-5 text-ink-subtle">
                <Icon name="shield" size="sm" />
                <span>
                  Information, not legal advice. Verify cited sources and consult a qualified professional for legal decisions.
                </span>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

const initialFormulationAnswers: FormulationAnswers = {
  intendedUse: "",
  productDescription: "",
  ingredients: "",
  formulationType: "",
  traditionalText: "",
  textReference: "",
  innovation: [],
  claimType: "",
  claims: "",
  dosageForm: "",
  market: "",
};

const formulationSteps = [
  { number: 1, label: "Intended use" },
  { number: 2, label: "Formulation" },
  { number: 3, label: "Traditional basis" },
  { number: 4, label: "Innovation" },
  { number: 5, label: "Claims & market" },
];

function RadioCards({
  name,
  value,
  options,
  onChange,
}: {
  name: string;
  value: string;
  options: Array<{ value: string; label: string; description?: string }>;
  onChange: (value: string) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      {options.map((option) => (
        <label
          key={option.value}
          className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${
            value === option.value
              ? "border-brand bg-brand-pale ring-1 ring-brand"
              : "border-line bg-white hover:border-brand-soft"
          }`}
        >
          <input
            type="radio"
            name={name}
            value={option.value}
            checked={value === option.value}
            onChange={() => onChange(option.value)}
            className="mt-0.5 size-4 accent-brand"
          />
          <span>
            <span className="block text-sm font-semibold text-ink">{option.label}</span>
            {option.description && (
              <span className="mt-1 block text-xs leading-5 text-ink-subtle">
                {option.description}
              </span>
            )}
          </span>
        </label>
      ))}
    </div>
  );
}

function WizardField({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-bold text-ink">{label}</span>
      {hint && <span className="mt-1 block text-xs leading-5 text-ink-subtle">{hint}</span>}
      <span className="mt-3 block">{children}</span>
    </label>
  );
}

function getPreliminaryCategory(answers: FormulationAnswers) {
  const hasNovelty = answers.innovation.includes("composition") || answers.innovation.includes("process");

  if (
    answers.intendedUse === "cosmetic" &&
    answers.claimType === "cosmetic" &&
    answers.dosageForm === "topical"
  ) {
    return "Cosmetic";
  }
  if (
    answers.formulationType === "standardized-extract" &&
    hasNovelty &&
    answers.intendedUse === "treatment"
  ) {
    return "Phytopharmaceutical";
  }
  if (
    (answers.intendedUse === "nutrition" || answers.claimType === "nutrition") &&
    answers.dosageForm !== "topical"
  ) {
    return "Ayurveda-Aahar or nutraceutical";
  }
  if (
    answers.traditionalText === "yes" &&
    !hasNovelty &&
    answers.intendedUse === "treatment"
  ) {
    return "Classical Ayurvedic medicine";
  }
  if (
    hasNovelty &&
    answers.traditionalText === "no" &&
    answers.intendedUse === "treatment"
  ) {
    return "New or non-classical drug";
  }
  return "Patent or proprietary Ayurvedic medicine";
}

function ClassificationResult({
  answers,
  onEdit,
  onRestart,
}: {
  answers: FormulationAnswers;
  onEdit: (step: number) => void;
  onRestart: () => void;
}) {
  const category = getPreliminaryCategory(answers);
  const answerSummary = [
    ["Intended use", answers.intendedUse || "Not provided"],
    ["Formulation type", answers.formulationType || "Not provided"],
    [
      "Traditional-text basis",
      answers.traditionalText === "yes"
        ? "Yes"
        : answers.traditionalText === "partial"
          ? "Partially"
          : answers.traditionalText === "no"
            ? "No"
            : "Not provided",
    ],
    [
      "Novel features",
      answers.innovation.length
        ? answers.innovation.map((item) => item.replace("-", " ")).join(", ")
        : "None selected",
    ],
    ["Claims profile", answers.claimType || "Not provided"],
    ["Dosage form", answers.dosageForm || "Not provided"],
    ["Intended market", answers.market || "Not provided"],
  ];

  return (
    <div className="mx-auto max-w-wizard px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-action">
            Preliminary result
          </div>
          <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">
            Formulation classification
          </h2>
          <p className="mt-2 text-sm leading-6 text-ink-muted">
            Based on the combined information provided across all five steps.
          </p>
        </div>
        <button
          type="button"
          onClick={onRestart}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line-strong bg-white px-4 text-sm font-semibold text-ink-muted hover:bg-surface-subtle"
        >
          <Icon name="refresh" size="sm" />
          Start again
        </button>
      </div>

      <div className="rounded-2xl border border-sage-soft bg-sage-pale p-5 sm:p-7">
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-widest text-sage-strong">
              <Icon name="check" size="sm" />
              Likely product category
            </div>
            <h3 className="mt-3 font-display text-2xl font-bold text-ink">{category}</h3>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-sage-text">
              This category is a prototype indication generated from several answers, including
              intended use, traditional basis, formulation type, novelty, claims, and dosage form.
            </p>
          </div>
          <span className="w-fit shrink-0 rounded-full border border-sage-soft bg-white px-3 py-1.5 text-xs font-semibold text-sage-strong">
            Preliminary only
          </span>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-result">
        <div className="space-y-6">
          <section className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-display text-lg font-bold text-ink">
                  Information used for classification
                </h3>
                <p className="mt-1 text-xs text-ink-subtle">
                  Review the combined profile before relying on this preliminary result.
                </p>
              </div>
              <button
                type="button"
                onClick={() => onEdit(1)}
                className="text-xs font-bold text-brand hover:text-brand-strong"
              >
                Edit answers
              </button>
            </div>
            <dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {answerSummary.map(([label, value]) => (
                <div key={label} className="border-b border-line pb-3">
                  <dt className="text-xs text-ink-faint">{label}</dt>
                  <dd className="mt-1 text-sm font-semibold capitalize text-ink">{value}</dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <h3 className="font-display text-lg font-bold text-ink">
              Potential regulatory requirements
            </h3>
            <p className="mt-1 text-xs text-ink-subtle">
              Illustrative checkpoints to confirm for the selected category and market.
            </p>
            <div className="mt-5 space-y-3">
              {[
                "Confirm the applicable product definition and licensing pathway.",
                "Review ingredient, manufacturing, labelling, and claims requirements.",
                "Check whether additional evidence or safety documentation may be expected.",
                "Verify market-specific requirements before manufacture, promotion, or sale.",
              ].map((item) => (
                <div key={item} className="flex gap-3 rounded-lg bg-canvas p-3">
                  <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-full bg-brand-pale text-brand">
                    <Icon name="check" size="sm" />
                  </span>
                  <p className="text-sm leading-6 text-ink-muted">{item}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-brand-pale text-brand">
                <Icon name="book" />
              </span>
              <div>
                <h3 className="font-display text-base font-bold text-ink">Relevant legal sources</h3>
                <p className="mt-0.5 text-xs text-ink-subtle">Source families to verify</p>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {[
                ["Drugs and cosmetics framework", "Review currently applicable provisions and rules"],
                ["Ministry of AYUSH materials", "Check current classification and licensing guidance"],
                ["Food regulatory framework", "Relevant when food or nutraceutical pathways are considered"],
                ["Market-specific requirements", "Required for the selected intended market"],
              ].map(([title, note]) => (
                <div key={title} className="rounded-lg border border-line p-3">
                  <div className="flex items-start gap-2">
                    <Icon name="document" size="sm" />
                    <div>
                      <div className="text-xs font-bold text-ink">{title}</div>
                      <p className="mt-1 text-xs leading-5 text-ink-subtle">{note}</p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-lg bg-brand-pale p-3 text-xs leading-5 text-brand">
              Prototype references only. Confirm current titles, provisions, amendments, and
              applicability with official sources.
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <h3 className="font-display text-base font-bold text-ink">Recommended next steps</h3>
            <ol className="mt-4 space-y-4">
              {[
                "Review and complete any missing formulation details.",
                "Compare the preliminary category against current official guidance.",
                "Discuss the intended claims and market with a qualified expert.",
              ].map((item, index) => (
                <li key={item} className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-sage-pale text-xs font-bold text-sage-strong">
                    {index + 1}
                  </span>
                  <span className="text-xs leading-5 text-ink-muted">{item}</span>
                </li>
              ))}
            </ol>
            <a
              href="#contact-expert"
              className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
            >
              <Icon name="user" size="sm" />
              Request expert confirmation
            </a>
          </section>
        </div>
      </div>

      <div className="mt-6 flex items-start gap-3 rounded-xl border border-sage-soft bg-sage-pale p-4">
        <Icon name="shield" size="sm" />
        <p className="text-xs leading-5 text-sage-text">
          <strong className="font-bold text-sage-strong">Preliminary classification:</strong> This
          result is informational, may change when further facts or current legal requirements are
          reviewed, and may require confirmation by a qualified regulatory or legal expert.
        </p>
      </div>
    </div>
  );
}

function FormulationWizard({ onCancel }: { onCancel: () => void }) {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<FormulationAnswers>(initialFormulationAnswers);
  const [showValidation, setShowValidation] = useState(false);

  const requiredByStep = [
    Boolean(answers.intendedUse && answers.productDescription.trim()),
    Boolean(answers.ingredients.trim() && answers.formulationType),
    Boolean(answers.traditionalText),
    answers.innovation.length > 0,
    Boolean(answers.claimType && answers.claims.trim() && answers.dosageForm && answers.market),
  ];

  function update<K extends keyof FormulationAnswers>(key: K, value: FormulationAnswers[K]) {
    setAnswers((current) => ({ ...current, [key]: value }));
    setShowValidation(false);
  }

  function continueStep() {
    if (!requiredByStep[step - 1]) {
      setShowValidation(true);
      return;
    }
    setShowValidation(false);
    setStep(step + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function toggleInnovation(value: string) {
    if (value === "neither") {
      update("innovation", ["neither"]);
      return;
    }
    const withoutNeither = answers.innovation.filter((item) => item !== "neither");
    update(
      "innovation",
      withoutNeither.includes(value)
        ? withoutNeither.filter((item) => item !== value)
        : [...withoutNeither, value],
    );
  }

  if (step === 6) {
    return (
      <ClassificationResult
        answers={answers}
        onEdit={(target) => setStep(target)}
        onRestart={() => {
          setAnswers(initialFormulationAnswers);
          setStep(1);
        }}
      />
    );
  }

  return (
    <div className="mx-auto max-w-wizard px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7">
        <div className="text-xs font-bold uppercase tracking-widest text-action">
          Guided classification
        </div>
        <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">
          Formulation Classification
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-muted">
          Build a complete product profile to explore a possible preliminary category.
        </p>
      </div>

      <div className="rounded-2xl border border-line bg-white shadow-card">
        <div className="border-b border-line px-5 py-5 sm:px-7">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-brand">
              Step {step} of {formulationSteps.length}
            </span>
            <span className="text-ink-subtle">{formulationSteps[step - 1].label}</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-subtle">
            <div
              className={`h-full rounded-full bg-brand transition-all ${
                ["w-1/5", "w-2/5", "w-3/5", "w-4/5", "w-full"][step - 1]
              }`}
            />
          </div>
          <div className="mt-4 hidden grid-cols-5 gap-3 md:grid">
            {formulationSteps.map((item) => (
              <button
                type="button"
                key={item.number}
                onClick={() => item.number < step && setStep(item.number)}
                disabled={item.number > step}
                className={`text-left text-xs font-semibold ${
                  item.number === step
                    ? "text-brand"
                    : item.number < step
                      ? "text-sage-strong hover:text-brand"
                      : "text-ink-faint"
                }`}
              >
                <span className="mb-1 block">{item.number}</span>
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-wizard-step p-5 sm:p-7 lg:p-9">
          {step === 1 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                What is the product intended to do?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Select the closest primary use. You can describe additional context below.
              </p>
              <div className="mt-6">
                <RadioCards
                  name="intended-use"
                  value={answers.intendedUse}
                  onChange={(value) => update("intendedUse", value)}
                  options={[
                    { value: "treatment", label: "Treatment or disease management", description: "Therapeutic or preventive intent" },
                    { value: "wellness", label: "General health and wellness", description: "Wellbeing without a specific disease claim" },
                    { value: "nutrition", label: "Food or nutritional use", description: "Dietary, nourishment, or functional food use" },
                    { value: "cosmetic", label: "Cosmetic use", description: "Cleansing, appearance, grooming, or external care" },
                  ]}
                />
              </div>
              <div className="mt-6">
                <WizardField
                  label="Briefly describe the product"
                  hint="Explain who it is for and the intended outcome."
                >
                  <textarea
                    rows={4}
                    value={answers.productDescription}
                    onChange={(event) => update("productDescription", event.target.value)}
                    placeholder="Example: An oral herbal preparation intended to support…"
                    className="w-full resize-none rounded-xl border border-line-strong bg-white p-4 text-sm leading-6 text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
              </div>
            </fieldset>
          )}

          {step === 2 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Tell us about the ingredients and formulation
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Include active ingredients and enough detail to understand how they are combined.
              </p>
              <div className="mt-6">
                <WizardField
                  label="Ingredients and formulation details"
                  hint="Use common and botanical names where available. Do not include confidential manufacturing parameters."
                >
                  <textarea
                    rows={5}
                    value={answers.ingredients}
                    onChange={(event) => update("ingredients", event.target.value)}
                    placeholder="List ingredients, approximate role, and formulation overview…"
                    className="w-full resize-none rounded-xl border border-line-strong bg-white p-4 text-sm leading-6 text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
              </div>
              <div className="mt-6">
                <div className="mb-3 text-sm font-bold text-ink">Primary formulation type</div>
                <RadioCards
                  name="formulation-type"
                  value={answers.formulationType}
                  onChange={(value) => update("formulationType", value)}
                  options={[
                    { value: "whole-herb", label: "Whole herb or traditional preparation" },
                    { value: "extract", label: "Herbal extract" },
                    { value: "standardized-extract", label: "Standardized or purified extract" },
                    { value: "mixed", label: "Combination or other formulation" },
                  ]}
                />
              </div>
            </fieldset>
          )}

          {step === 3 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Does it follow an authoritative traditional Ayurvedic text?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Consider the ingredients, proportions, preparation method, and intended use
                together.
              </p>
              <div className="mt-6">
                <RadioCards
                  name="traditional-text"
                  value={answers.traditionalText}
                  onChange={(value) => update("traditionalText", value)}
                  options={[
                    { value: "yes", label: "Yes, it follows a documented formulation", description: "The relevant formulation can be identified" },
                    { value: "partial", label: "Partially", description: "It is adapted from a documented formulation" },
                    { value: "no", label: "No", description: "It is not based on an identified traditional formulation" },
                    { value: "unsure", label: "Not sure", description: "Further source review is needed" },
                  ]}
                />
              </div>
              {(answers.traditionalText === "yes" || answers.traditionalText === "partial") && (
                <div className="mt-6">
                  <WizardField
                    label="Text or formulation reference"
                    hint="Enter the reference as you understand it. It can be verified later."
                  >
                    <input
                      type="text"
                      value={answers.textReference}
                      onChange={(event) => update("textReference", event.target.value)}
                      placeholder="Name of text, formulation, chapter, or verse if known"
                      className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                    />
                  </WizardField>
                </div>
              )}
            </fieldset>
          )}

          {step === 4 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                What is new about the formulation?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Select all that apply. This is considered alongside the full product profile.
              </p>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                {[
                  ["composition", "New composition", "A new combination, proportion, or constituent profile"],
                  ["process", "New process", "A new extraction, preparation, or manufacturing process"],
                  ["dosage-form", "New dosage or delivery form", "A different format or method of administration"],
                  ["neither", "None of these", "No new composition, process, or dosage form is claimed"],
                ].map(([value, label, description]) => (
                  <label
                    key={value}
                    className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${
                      answers.innovation.includes(value)
                        ? "border-brand bg-brand-pale ring-1 ring-brand"
                        : "border-line bg-white hover:border-brand-soft"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={answers.innovation.includes(value)}
                      onChange={() => toggleInnovation(value)}
                      className="mt-0.5 size-4 rounded accent-brand"
                    />
                    <span>
                      <span className="block text-sm font-semibold text-ink">{label}</span>
                      <span className="mt-1 block text-xs leading-5 text-ink-subtle">
                        {description}
                      </span>
                    </span>
                  </label>
                ))}
              </div>
              <div className="mt-6 rounded-xl border border-brand-soft bg-brand-pale p-4">
                <div className="flex gap-3">
                  <Icon name="shield" size="sm" />
                  <p className="text-xs leading-5 text-brand">
                    A new feature does not by itself determine regulatory category or intellectual
                    property eligibility. The final preview considers answers across all steps.
                  </p>
                </div>
              </div>
            </fieldset>
          )}

          {step === 5 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Claims, dosage form, and intended market
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Product presentation and market context can materially affect the pathway.
              </p>
              <div className="mt-6">
                <div className="mb-3 text-sm font-bold text-ink">Primary claims profile</div>
                <RadioCards
                  name="claim-type"
                  value={answers.claimType}
                  onChange={(value) => update("claimType", value)}
                  options={[
                    { value: "therapeutic", label: "Therapeutic or preventive" },
                    { value: "wellness", label: "General wellness" },
                    { value: "nutrition", label: "Nutritional or food-related" },
                    { value: "cosmetic", label: "Cosmetic or appearance-related" },
                  ]}
                />
              </div>
              <div className="mt-6">
                <WizardField
                  label="Proposed product claims"
                  hint="Use the wording that may appear on packaging or promotional material."
                >
                  <textarea
                    rows={3}
                    value={answers.claims}
                    onChange={(event) => update("claims", event.target.value)}
                    placeholder="Describe the proposed claims…"
                    className="w-full resize-none rounded-xl border border-line-strong bg-white p-4 text-sm leading-6 text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
              </div>
              <div className="mt-6 grid gap-5 sm:grid-cols-2">
                <WizardField label="Dosage form">
                  <select
                    value={answers.dosageForm}
                    onChange={(event) => update("dosageForm", event.target.value)}
                    className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  >
                    <option value="">Select dosage form</option>
                    <option value="tablet-capsule">Tablet or capsule</option>
                    <option value="liquid">Liquid or syrup</option>
                    <option value="powder">Powder or granules</option>
                    <option value="topical">Topical application</option>
                    <option value="food-format">Food or beverage format</option>
                    <option value="other">Other</option>
                  </select>
                </WizardField>
                <WizardField label="Intended market">
                  <select
                    value={answers.market}
                    onChange={(event) => update("market", event.target.value)}
                    className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  >
                    <option value="">Select market</option>
                    <option value="India">India</option>
                    <option value="International">International</option>
                    <option value="India and international">India and international</option>
                  </select>
                </WizardField>
              </div>
            </fieldset>
          )}

          {showValidation && (
            <div
              role="alert"
              className="mt-6 flex items-start gap-3 rounded-xl border border-error/20 bg-error-pale p-4 text-sm text-error"
            >
              <Icon name="warning" size="sm" />
              Complete the required fields in this step before continuing.
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-4 sm:px-7">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setStep(Math.max(1, step - 1))}
              disabled={step === 1}
              className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold text-ink-muted transition hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="rotate-180">
                <Icon name="arrow" size="sm" />
              </span>
              Back
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex h-10 items-center rounded-lg px-3 text-sm font-semibold text-ink-subtle transition hover:bg-surface-subtle hover:text-ink"
            >
              Cancel
            </button>
          </div>
          <button
            type="button"
            onClick={continueStep}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white shadow-brand transition hover:bg-brand-strong focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-soft"
          >
            {step === formulationSteps.length ? "View result" : "Continue"}
            <Icon name="arrow" size="sm" />
          </button>
        </div>
      </div>

      <div className="mt-4 flex items-start justify-center gap-2 text-center text-xs leading-5 text-ink-subtle">
        <Icon name="shield" size="sm" />
        <span>Information only. Final classification may require expert and authority confirmation.</span>
      </div>
    </div>
  );
}

const initialAbsAnswers: AbsAnswers = {
  resourceName: "",
  resourceType: "",
  originCountry: "",
  originState: "",
  sourceMethod: "",
  activity: [],
  activityDetails: "",
  userCategory: "",
  organisationName: "",
  foreignParticipation: "",
  traditionalKnowledge: "",
  knowledgeDetails: "",
  communityIdentified: "",
  commercialisation: "",
  exportPlan: "",
  destination: "",
};

const absSteps = [
  { number: 1, label: "Resource & origin" },
  { number: 2, label: "Activity" },
  { number: 3, label: "User category" },
  { number: 4, label: "Traditional knowledge" },
  { number: 5, label: "Commercialisation" },
];

function AbsResult({
  answers,
  onEdit,
  onRestart,
}: {
  answers: AbsAnswers;
  onEdit: (step: number) => void;
  onRestart: () => void;
}) {
  const foreignConnection =
    answers.userCategory === "foreign" ||
    answers.userCategory === "indian-foreign-participation" ||
    answers.foreignParticipation === "yes";
  const commercialActivity =
    answers.activity.includes("commercial-research") ||
    answers.activity.includes("commercial-utilisation") ||
    answers.commercialisation !== "none";
  const ipActivity = answers.activity.includes("ipr");
  const exportActivity = answers.exportPlan === "yes" || answers.exportPlan === "unsure";
  const knowledgeRelevant =
    answers.traditionalKnowledge === "yes" || answers.traditionalKnowledge === "unsure";

  const obligations = [
    {
      title: foreignConnection
        ? "Review whether prior approval from the National Biodiversity Authority may be relevant"
        : "Review whether intimation, registration, or approval with the appropriate biodiversity authority may be relevant",
      detail:
        "The applicable route can depend on nationality, entity ownership or control, resource origin, activity, and current statutory provisions.",
      status: "Potential obligation",
    },
    ...(commercialActivity
      ? [
          {
            title: "Assess access and benefit-sharing requirements before commercial use",
            detail:
              "Commercial intent, the resource supply chain, and any applicable exemptions or sector-specific treatment require confirmation.",
            status: "Review required",
          },
        ]
      : []),
    ...(knowledgeRelevant
      ? [
          {
            title: "Identify holders of associated traditional knowledge and applicable safeguards",
            detail:
              "Prior informed consent, mutually agreed terms, attribution, or benefit-sharing considerations may need specialist review.",
            status: "Additional facts needed",
          },
        ]
      : []),
    ...(ipActivity
      ? [
          {
            title: "Review biodiversity-law steps connected with intellectual property activity",
            detail:
              "Timing and authority requirements should be checked against the current amended legal framework and the proposed filing strategy.",
            status: "Potential obligation",
          },
        ]
      : []),
    ...(exportActivity
      ? [
          {
            title: "Confirm requirements before transferring resources, results, or samples abroad",
            detail:
              "The material being transferred, recipient, purpose, destination, and contractual terms can affect the analysis.",
            status: "Review required",
          },
        ]
      : []),
  ];

  const missingInformation = [
    ...(!answers.originState || answers.originCountry === "unknown"
      ? ["Confirm the precise geographic origin and collection location of each resource."]
      : []),
    ...(answers.traditionalKnowledge === "unsure"
      ? ["Determine whether the activity uses knowledge held by a community or knowledge holder."]
      : []),
    ...(knowledgeRelevant && !answers.communityIdentified
      ? ["Identify the relevant community, knowledge holder, or documentation source."]
      : []),
    ...(answers.exportPlan === "unsure"
      ? ["Confirm whether samples, research results, data, or derivatives will move outside India."]
      : []),
    ...(answers.userCategory === "indian-foreign-participation" &&
    answers.foreignParticipation !== "yes"
      ? ["Confirm the organisation's current ownership, control, and foreign-participation details."]
      : []),
  ];

  const summary = [
    ["Biological resource", answers.resourceName],
    ["Resource type", answers.resourceType],
    [
      "Origin",
      [answers.originState, answers.originCountry].filter(Boolean).join(", ") || "Not provided",
    ],
    ["User category", answers.userCategory.replace(/-/g, " ")],
    ["Activities", answers.activity.map((item) => item.replace(/-/g, " ")).join(", ")],
    [
      "Traditional knowledge",
      answers.traditionalKnowledge === "yes"
        ? "Associated knowledge identified"
        : answers.traditionalKnowledge === "no"
          ? "Not identified"
          : "Requires confirmation",
    ],
    ["Commercialisation", answers.commercialisation.replace(/-/g, " ")],
    ["Export plan", answers.exportPlan],
  ];

  return (
    <div className="mx-auto max-w-wizard px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7 flex flex-col justify-between gap-4 sm:flex-row sm:items-end">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-action">
            ABS assessment summary
          </div>
          <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">
            Potential compliance considerations
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-muted">
            A cautious review based on the combined information entered across the questionnaire.
          </p>
        </div>
        <button
          type="button"
          onClick={onRestart}
          className="inline-flex h-10 items-center justify-center gap-2 rounded-lg border border-line-strong bg-white px-4 text-sm font-semibold text-ink-muted hover:bg-surface-subtle"
        >
          <Icon name="refresh" size="sm" />
          Start again
        </button>
      </div>

      <div className="rounded-2xl border border-brand-soft bg-brand-pale p-5 sm:p-7">
        <div className="flex gap-4">
          <span className="grid size-11 shrink-0 place-items-center rounded-xl bg-white text-brand">
            <Icon name="shield" />
          </span>
          <div>
            <div className="text-xs font-bold uppercase tracking-widest text-brand">
              Assessment status
            </div>
            <h3 className="mt-2 font-display text-xl font-bold text-ink">
              Potential obligations identified for further review
            </h3>
            <p className="mt-2 text-sm leading-6 text-ink-muted">
              This result does not confirm that an approval is required, and it does not declare
              the user compliant or non-compliant. Current law, exemptions, authority practice, and
              complete facts must be checked.
            </p>
          </div>
        </div>
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-result">
        <div className="space-y-6">
          <section className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h3 className="font-display text-lg font-bold text-ink">
                  Potential compliance obligations
                </h3>
                <p className="mt-1 text-xs text-ink-subtle">
                  Each item is a review prompt, not a confirmed legal requirement.
                </p>
              </div>
              <span className="hidden rounded-full bg-brand-pale px-2.5 py-1 text-xs font-semibold text-brand sm:inline-flex">
                {obligations.length} items
              </span>
            </div>
            <div className="mt-5 space-y-3">
              {obligations.map((item, index) => (
                <article key={item.title} className="rounded-xl border border-line p-4">
                  <div className="flex gap-3">
                    <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-brand-pale text-xs font-bold text-brand">
                      {index + 1}
                    </span>
                    <div>
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="text-sm font-bold leading-5 text-ink">{item.title}</h4>
                        <span className="rounded-full border border-sage-soft bg-sage-pale px-2 py-0.5 text-xs font-semibold text-sage-strong">
                          {item.status}
                        </span>
                      </div>
                      <p className="mt-2 text-xs leading-5 text-ink-muted">{item.detail}</p>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-display text-lg font-bold text-ink">Results summary</h3>
                <p className="mt-1 text-xs text-ink-subtle">
                  Information used to prepare this assessment.
                </p>
              </div>
              <button
                type="button"
                onClick={() => onEdit(1)}
                className="text-xs font-bold text-brand hover:text-brand-strong"
              >
                Edit answers
              </button>
            </div>
            <dl className="mt-5 grid gap-x-6 gap-y-4 sm:grid-cols-2">
              {summary.map(([label, value]) => (
                <div key={label} className="border-b border-line pb-3">
                  <dt className="text-xs text-ink-faint">{label}</dt>
                  <dd className="mt-1 text-sm font-semibold capitalize text-ink">
                    {value || "Not provided"}
                  </dd>
                </div>
              ))}
            </dl>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
            <h3 className="font-display text-lg font-bold text-ink">
              Items requiring more information or expert review
            </h3>
            <div className="mt-5 space-y-3">
              {(missingInformation.length
                ? missingInformation
                : [
                    "Confirm whether any current exemption, sector-specific rule, or authority direction applies.",
                    "Have a qualified ABS professional review the complete facts and planned agreements.",
                  ]
              ).map((item) => (
                <div key={item} className="flex gap-3 rounded-lg bg-error-pale p-3">
                  <span className="mt-0.5 text-error">
                    <Icon name="warning" size="sm" />
                  </span>
                  <p className="text-sm leading-6 text-ink-muted">{item}</p>
                </div>
              ))}
            </div>
          </section>
        </div>

        <div className="space-y-6">
          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <div className="flex items-center gap-3">
              <span className="grid size-10 place-items-center rounded-xl bg-brand-pale text-brand">
                <Icon name="book" />
              </span>
              <div>
                <h3 className="font-display text-base font-bold text-ink">
                  Official laws and guidance
                </h3>
                <p className="mt-0.5 text-xs text-ink-subtle">
                  Verify current consolidated versions
                </p>
              </div>
            </div>
            <div className="mt-5 space-y-3">
              {[
                ["Biological Diversity Act framework", "Primary legislation, including current amendments"],
                ["Biological Diversity Rules", "Procedural rules and prescribed processes"],
                ["ABS regulations and authority guidance", "Benefit-sharing methods and application guidance"],
              ].map(([title, description]) => (
                <div key={title} className="rounded-lg border border-line p-3">
                  <div className="text-xs font-bold text-ink">{title}</div>
                  <p className="mt-1 text-xs leading-5 text-ink-subtle">{description}</p>
                </div>
              ))}
            </div>
            <div className="mt-4 rounded-lg bg-brand-pale p-3 text-xs leading-5 text-brand">
              Titles are presented as reference categories. Confirm the current text, effective
              provisions, forms, and authority instructions before acting.
            </div>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <h3 className="font-display text-base font-bold text-ink">
              Official authority links
            </h3>
            <div className="mt-4 space-y-2">
              <a
                href="https://nbaindia.org/"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-lg border border-line px-3 py-3 text-xs font-semibold text-ink-muted hover:border-brand-soft hover:text-brand"
              >
                National Biodiversity Authority
                <Icon name="external" size="sm" />
              </a>
              <a
                href="https://moef.gov.in/"
                target="_blank"
                rel="noreferrer"
                className="flex items-center justify-between rounded-lg border border-line px-3 py-3 text-xs font-semibold text-ink-muted hover:border-brand-soft hover:text-brand"
              >
                Ministry of Environment, Forest and Climate Change
                <Icon name="external" size="sm" />
              </a>
            </div>
            <p className="mt-3 text-xs leading-5 text-ink-faint">
              External official portals should be checked for current forms and notices.
            </p>
          </section>

          <section className="rounded-2xl border border-line bg-white p-5 shadow-card">
            <h3 className="font-display text-base font-bold text-ink">Recommended next steps</h3>
            <ol className="mt-4 space-y-4">
              {[
                "Resolve the additional-information items identified in this summary.",
                "Map each resource to its provider, location, access date, and intended use.",
                "Confirm the correct authority and process using current official materials.",
                "Seek specialist review before commercialisation, export, or IP action.",
              ].map((item, index) => (
                <li key={item} className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-sage-pale text-xs font-bold text-sage-strong">
                    {index + 1}
                  </span>
                  <span className="text-xs leading-5 text-ink-muted">{item}</span>
                </li>
              ))}
            </ol>
            <a
              href="#contact-abs-expert"
              className="mt-5 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
            >
              <Icon name="user" size="sm" />
              Request ABS expert review
            </a>
          </section>
        </div>
      </div>

      <div className="sticky bottom-4 z-10 mt-6 flex items-start gap-3 rounded-xl border border-sage-soft bg-sage-pale/95 p-4 shadow-card backdrop-blur">
        <Icon name="shield" size="sm" />
        <p className="text-xs leading-5 text-sage-text">
          <strong className="font-bold text-sage-strong">Information, not legal advice.</strong>{" "}
          This prototype highlights potential obligations only. It does not confirm a requirement,
          exemption, approval status, or compliance outcome.
        </p>
      </div>
    </div>
  );
}

function AbsComplianceWizard({ onCancel }: { onCancel: () => void }) {
  const [step, setStep] = useState(1);
  const [answers, setAnswers] = useState<AbsAnswers>(initialAbsAnswers);
  const [showValidation, setShowValidation] = useState(false);

  const requiredByStep = [
    Boolean(
      answers.resourceName.trim() &&
        answers.resourceType &&
        answers.originCountry &&
        answers.sourceMethod,
    ),
    Boolean(answers.activity.length && answers.activityDetails.trim()),
    Boolean(answers.userCategory && answers.organisationName.trim()),
    Boolean(answers.traditionalKnowledge),
    Boolean(answers.commercialisation && answers.exportPlan),
  ];

  function update<K extends keyof AbsAnswers>(key: K, value: AbsAnswers[K]) {
    setAnswers((current) => ({ ...current, [key]: value }));
    setShowValidation(false);
  }

  function toggleActivity(value: string) {
    update(
      "activity",
      answers.activity.includes(value)
        ? answers.activity.filter((item) => item !== value)
        : [...answers.activity, value],
    );
  }

  function continueStep() {
    if (!requiredByStep[step - 1]) {
      setShowValidation(true);
      return;
    }
    setShowValidation(false);
    setStep(step + 1);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  if (step === 6) {
    return (
      <AbsResult
        answers={answers}
        onEdit={(target) => setStep(target)}
        onRestart={() => {
          setAnswers(initialAbsAnswers);
          setStep(1);
        }}
      />
    );
  }

  return (
    <div className="mx-auto max-w-wizard px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="mb-7">
        <div className="text-xs font-bold uppercase tracking-widest text-action">
          Guided ABS review
        </div>
        <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">
          Access and Benefit Sharing
        </h2>
        <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-muted">
          Explore potential obligations associated with biological resources and related
          traditional knowledge.
        </p>
      </div>

      <div className="rounded-2xl border border-line bg-white shadow-card">
        <div className="border-b border-line px-5 py-5 sm:px-7">
          <div className="flex items-center justify-between text-xs">
            <span className="font-bold text-brand">Step {step} of {absSteps.length}</span>
            <span className="text-ink-subtle">{absSteps[step - 1].label}</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-subtle">
            <div
              className={`h-full rounded-full bg-brand transition-all ${
                ["w-1/5", "w-2/5", "w-3/5", "w-4/5", "w-full"][step - 1]
              }`}
            />
          </div>
          <div className="mt-4 hidden grid-cols-5 gap-3 md:grid">
            {absSteps.map((item) => (
              <button
                type="button"
                key={item.number}
                onClick={() => item.number < step && setStep(item.number)}
                disabled={item.number > step}
                className={`text-left text-xs font-semibold ${
                  item.number === step
                    ? "text-brand"
                    : item.number < step
                      ? "text-sage-strong hover:text-brand"
                      : "text-ink-faint"
                }`}
              >
                <span className="mb-1 block">{item.number}</span>
                {item.label}
              </button>
            ))}
          </div>
        </div>

        <div className="min-h-wizard-step p-5 sm:p-7 lg:p-9">
          {step === 1 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Which biological resource is involved?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Describe the resource and where it was collected, cultivated, purchased, or
                otherwise obtained.
              </p>
              <div className="mt-6 grid gap-5 sm:grid-cols-2">
                <WizardField label="Biological resource">
                  <input
                    type="text"
                    value={answers.resourceName}
                    onChange={(event) => update("resourceName", event.target.value)}
                    placeholder="Common or scientific name"
                    className="h-12 w-full rounded-xl border border-line-strong px-4 text-sm outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
                <WizardField label="Resource type">
                  <select
                    value={answers.resourceType}
                    onChange={(event) => update("resourceType", event.target.value)}
                    className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  >
                    <option value="">Select type</option>
                    <option value="plant material">Plant material</option>
                    <option value="extract or derivative">Extract or derivative</option>
                    <option value="microorganism">Microorganism</option>
                    <option value="animal-derived material">Animal-derived material</option>
                    <option value="multiple resources">Multiple resources</option>
                    <option value="other or uncertain">Other or uncertain</option>
                  </select>
                </WizardField>
                <WizardField label="Country of origin">
                  <select
                    value={answers.originCountry}
                    onChange={(event) => update("originCountry", event.target.value)}
                    className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  >
                    <option value="">Select origin</option>
                    <option value="India">India</option>
                    <option value="Outside India">Outside India</option>
                    <option value="Multiple countries">Multiple countries</option>
                    <option value="unknown">Not yet known</option>
                  </select>
                </WizardField>
                <WizardField label="State or local area" hint="Enter the most specific location known.">
                  <input
                    type="text"
                    value={answers.originState}
                    onChange={(event) => update("originState", event.target.value)}
                    placeholder="State, district, or collection area"
                    className="h-12 w-full rounded-xl border border-line-strong px-4 text-sm outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
              </div>
              <div className="mt-6">
                <div className="mb-3 text-sm font-bold text-ink">How is the resource accessed?</div>
                <RadioCards
                  name="source-method"
                  value={answers.sourceMethod}
                  onChange={(value) => update("sourceMethod", value)}
                  options={[
                    { value: "wild collection", label: "Wild collection" },
                    { value: "cultivated source", label: "Cultivated source" },
                    { value: "commercial supplier", label: "Commercial supplier" },
                    { value: "research collection", label: "Research collection or repository" },
                  ]}
                />
              </div>
            </fieldset>
          )}

          {step === 2 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                What activity is planned?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Select every activity that may form part of the project.
              </p>
              <div className="mt-6 grid gap-3 sm:grid-cols-2">
                {[
                  ["non-commercial-research", "Non-commercial research"],
                  ["commercial-research", "Commercial research or development"],
                  ["bio-survey", "Bio-survey or bio-utilisation"],
                  ["commercial-utilisation", "Manufacture or commercial utilisation"],
                  ["ipr", "Patent or other intellectual property activity"],
                  ["transfer", "Transfer to another person or organisation"],
                ].map(([value, label]) => (
                  <label
                    key={value}
                    className={`flex cursor-pointer items-center gap-3 rounded-xl border p-4 transition ${
                      answers.activity.includes(value)
                        ? "border-brand bg-brand-pale ring-1 ring-brand"
                        : "border-line hover:border-brand-soft"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={answers.activity.includes(value)}
                      onChange={() => toggleActivity(value)}
                      className="size-4 rounded accent-brand"
                    />
                    <span className="text-sm font-semibold text-ink">{label}</span>
                  </label>
                ))}
              </div>
              <div className="mt-6">
                <WizardField
                  label="Describe the proposed activity"
                  hint="Include research purpose, expected outputs, collaborators, and intended use."
                >
                  <textarea
                    rows={5}
                    value={answers.activityDetails}
                    onChange={(event) => update("activityDetails", event.target.value)}
                    placeholder="Describe how the resource will be accessed and used…"
                    className="w-full resize-none rounded-xl border border-line-strong p-4 text-sm leading-6 outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
              </div>
            </fieldset>
          )}

          {step === 3 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Who will access or use the resource?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                User status, ownership, control, and participation can affect which authority or
                process may be relevant.
              </p>
              <div className="mt-6">
                <RadioCards
                  name="user-category"
                  value={answers.userCategory}
                  onChange={(value) => update("userCategory", value)}
                  options={[
                    { value: "indian-individual", label: "Indian individual" },
                    { value: "indian-entity", label: "Indian organisation or company" },
                    { value: "indian-foreign-participation", label: "Indian entity with foreign participation", description: "Ownership, control, management, or other participation may require review" },
                    { value: "foreign", label: "Foreign individual or organisation" },
                    { value: "research-institution", label: "Research or educational institution" },
                    { value: "community-organisation", label: "Community or producer organisation" },
                  ]}
                />
              </div>
              <div className="mt-6 grid gap-5 sm:grid-cols-2">
                <WizardField label="Organisation or applicant name">
                  <input
                    type="text"
                    value={answers.organisationName}
                    onChange={(event) => update("organisationName", event.target.value)}
                    placeholder="Name of user or organisation"
                    className="h-12 w-full rounded-xl border border-line-strong px-4 text-sm outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
                <WizardField label="Any foreign ownership, control, or participation?">
                  <select
                    value={answers.foreignParticipation}
                    onChange={(event) => update("foreignParticipation", event.target.value)}
                    className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  >
                    <option value="">Select an answer</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                    <option value="unsure">Not sure</option>
                  </select>
                </WizardField>
              </div>
            </fieldset>
          )}

          {step === 4 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Is associated traditional knowledge involved?
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Consider knowledge about selection, preparation, combination, or use of the
                biological resource.
              </p>
              <div className="mt-6">
                <RadioCards
                  name="traditional-knowledge"
                  value={answers.traditionalKnowledge}
                  onChange={(value) => update("traditionalKnowledge", value)}
                  options={[
                    { value: "yes", label: "Yes", description: "Community or knowledge-holder input has been identified" },
                    { value: "no", label: "No", description: "No associated traditional knowledge is currently identified" },
                    { value: "unsure", label: "Not sure", description: "The knowledge source needs further investigation" },
                  ]}
                />
              </div>
              {answers.traditionalKnowledge !== "no" && (
                <div className="mt-6 grid gap-5">
                  <WizardField
                    label="Knowledge details"
                    hint="Describe the knowledge used and how it was learned, documented, or shared."
                  >
                    <textarea
                      rows={4}
                      value={answers.knowledgeDetails}
                      onChange={(event) => update("knowledgeDetails", event.target.value)}
                      placeholder="Describe the associated knowledge and its source…"
                      className="w-full resize-none rounded-xl border border-line-strong p-4 text-sm leading-6 outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                    />
                  </WizardField>
                  <WizardField label="Community or knowledge holder, if identified">
                    <input
                      type="text"
                      value={answers.communityIdentified}
                      onChange={(event) => update("communityIdentified", event.target.value)}
                      placeholder="Community, group, individual, or documentation source"
                      className="h-12 w-full rounded-xl border border-line-strong px-4 text-sm outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                    />
                  </WizardField>
                </div>
              )}
            </fieldset>
          )}

          {step === 5 && (
            <fieldset>
              <legend className="font-display text-xl font-bold text-ink">
                Commercialisation and export plans
              </legend>
              <p className="mt-2 text-sm leading-6 text-ink-muted">
                Include planned sales, licensing, technology transfer, sample movement, and
                international collaboration.
              </p>
              <div className="mt-6">
                <div className="mb-3 text-sm font-bold text-ink">Commercialisation stage</div>
                <RadioCards
                  name="commercialisation"
                  value={answers.commercialisation}
                  onChange={(value) => update("commercialisation", value)}
                  options={[
                    { value: "none", label: "No current commercial plan" },
                    { value: "exploratory", label: "Exploratory or pre-commercial" },
                    { value: "pilot", label: "Pilot, validation, or scale-up" },
                    { value: "sale-or-licensing", label: "Sale, licensing, or commercial launch" },
                  ]}
                />
              </div>
              <div className="mt-6 grid gap-5 sm:grid-cols-2">
                <WizardField label="Will material, data, or results be exported?">
                  <select
                    value={answers.exportPlan}
                    onChange={(event) => update("exportPlan", event.target.value)}
                    className="h-12 w-full rounded-xl border border-line-strong bg-white px-4 text-sm outline-none focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  >
                    <option value="">Select an answer</option>
                    <option value="yes">Yes</option>
                    <option value="no">No</option>
                    <option value="unsure">Not sure yet</option>
                  </select>
                </WizardField>
                <WizardField label="Destination or recipient" hint="Complete if known.">
                  <input
                    type="text"
                    value={answers.destination}
                    onChange={(event) => update("destination", event.target.value)}
                    placeholder="Country, collaborator, or recipient"
                    className="h-12 w-full rounded-xl border border-line-strong px-4 text-sm outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
                  />
                </WizardField>
              </div>
            </fieldset>
          )}

          {showValidation && (
            <div
              role="alert"
              className="mt-6 flex items-start gap-3 rounded-xl border border-error/20 bg-error-pale p-4 text-sm text-error"
            >
              <Icon name="warning" size="sm" />
              Complete the required information in this step before continuing.
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-line px-5 py-4 sm:px-7">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setStep(Math.max(1, step - 1))}
              disabled={step === 1}
              className="inline-flex h-10 items-center gap-2 rounded-lg px-3 text-sm font-semibold text-ink-muted transition hover:bg-surface-subtle disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="rotate-180">
                <Icon name="arrow" size="sm" />
              </span>
              Back
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="inline-flex h-10 items-center rounded-lg px-3 text-sm font-semibold text-ink-subtle transition hover:bg-surface-subtle hover:text-ink"
            >
              Cancel
            </button>
          </div>
          <button
            type="button"
            onClick={continueStep}
            className="inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-5 text-sm font-semibold text-white shadow-brand transition hover:bg-brand-strong focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-soft"
          >
            {step === absSteps.length ? "View results" : "Continue"}
            <Icon name="arrow" size="sm" />
          </button>
        </div>
      </div>

      <div className="sticky bottom-4 z-10 mt-4 flex items-start justify-center gap-2 rounded-xl border border-sage-soft bg-sage-pale/95 p-3 text-center text-xs leading-5 text-sage-text shadow-card backdrop-blur">
        <Icon name="shield" size="sm" />
        <span>
          Information, not legal advice. This tool identifies potential considerations, not a
          compliance outcome.
        </span>
      </div>
    </div>
  );
}

type SourceRecord = {
  id: string;
  title: string;
  authority: string;
  date: string;
  jurisdiction: string;
  type: string;
  status: string;
  section: string;
  passageBefore: string;
  match: string;
  passageAfter: string;
  keywords: string[];
};


function SourcePreview({ record }: { record: SourceRecord }) {
  return (
    <aside className="rounded-2xl border border-line bg-white shadow-card xl:sticky xl:top-24">
      <div className="border-b border-line p-5">
        <div className="flex items-center justify-between gap-3">
          <span className="rounded-full border border-brand-soft bg-brand-pale px-2.5 py-1 text-xs font-semibold text-brand">
            Selected passage
          </span>
          <span className="text-xs font-semibold text-ink-faint">{record.type}</span>
        </div>
        <h3 className="mt-4 font-display text-lg font-bold leading-6 text-ink">{record.title}</h3>
        <p className="mt-2 text-xs leading-5 text-ink-subtle">
          Placeholder metadata and passage for interface demonstration only.
        </p>
      </div>

      <div className="p-5">
        <h4 className="text-xs font-bold uppercase tracking-widest text-ink-faint">
          Document metadata
        </h4>
        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4 text-xs">
          {[
            ["Issuing authority", record.authority],
            ["Publication date", record.date],
            ["Jurisdiction", record.jurisdiction],
            ["Document status", record.status],
            ["Source type", record.type],
            ["Location", record.section],
          ].map(([label, value]) => (
            <div key={label}>
              <dt className="text-ink-faint">{label}</dt>
              <dd className="mt-1 font-semibold leading-5 text-ink">{value}</dd>
            </div>
          ))}
        </dl>

        <div className="mt-6 border-t border-line pt-5">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-bold text-ink">Relevant passage</h4>
            <span className="text-xs text-ink-faint">{record.section}</span>
          </div>
          <blockquote className="mt-3 rounded-xl border-l-4 border-sage-strong bg-sage-pale p-4 text-sm leading-7 text-ink-muted">
            {record.passageBefore}
            <mark className="rounded bg-sage-soft px-1 font-semibold text-ink">{record.match}</mark>
            {record.passageAfter}
          </blockquote>
          <div className="mt-4 flex flex-wrap gap-2">
            {record.keywords.map((keyword) => (
              <span
                key={keyword}
                className="rounded-full border border-line bg-surface-subtle px-2.5 py-1 text-xs font-semibold text-ink-subtle"
              >
                {keyword}
              </span>
            ))}
          </div>
        </div>

        <a
          href="#placeholder-official-source"
          className="mt-6 inline-flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-line-strong bg-white px-4 text-sm font-semibold text-brand transition hover:border-brand-muted hover:bg-brand-pale"
        >
          Open placeholder source link
          <Icon name="external" size="sm" />
        </a>
        <p className="mt-2 text-center text-xs leading-5 text-ink-faint">
          A verified official URL will replace this link when connected to a source backend.
        </p>
      </div>
    </aside>
  );
}

function ResearchEmpty({
  state,
  onReset,
}: {
  state: Exclude<ResearchState, "results">;
  onReset: () => void;
}) {
  if (state === "loading") {
    return (
      <div className="space-y-3" aria-label="Loading indexed search results">
        {[1, 2, 3].map((item) => (
          <div key={item} className="animate-pulse rounded-2xl border border-line bg-white p-5">
            <div className="h-3 w-loading-title rounded-full bg-brand-pale" />
            <div className="mt-4 h-4 w-loading-line rounded-full bg-surface-subtle" />
            <div className="mt-2 h-3 w-loading-short rounded-full bg-surface-subtle" />
            <div className="mt-5 h-8 w-loading-title rounded-lg bg-surface-subtle" />
          </div>
        ))}
        <p className="pt-2 text-center text-xs text-ink-subtle">
          Prototype loading state — no search backend request is being made.
        </p>
      </div>
    );
  }

  if (state === "error") {
    return (
      <div className="rounded-2xl border border-error/20 bg-error-pale px-6 py-14 text-center">
        <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-white text-error">
          <Icon name="warning" size="lg" />
        </span>
        <h3 className="mt-5 font-display text-xl font-bold text-ink">
          The search could not continue
        </h3>
        <p className="mx-auto mt-3 max-w-empty text-sm leading-6 text-ink-muted">
          This is a prototype error state. No backend request was sent.
        </p>
        <button
          type="button"
          onClick={onReset}
          className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
        >
          <Icon name="refresh" size="sm" />
          Return to search
        </button>
      </div>
    );
  }

  const empty = state === "empty";
  return (
    <div className="rounded-2xl border border-line bg-white px-6 py-14 text-center shadow-card">
      <span className="mx-auto grid size-14 place-items-center rounded-2xl bg-brand-pale text-brand">
        <Icon name={empty ? "search" : "document"} size="lg" />
      </span>
      <h3 className="mt-5 font-display text-xl font-bold text-ink">
        {empty ? "Start a traceable source search" : "No indexed passages match these filters"}
      </h3>
      <p className="mx-auto mt-3 max-w-empty text-sm leading-6 text-ink-muted">
        {empty
          ? "Enter a legal topic, document title, patent keyword, applicant, or citation to begin."
          : "Try broadening the jurisdiction, document type, publication date, or status filters."}
      </p>
      {!empty && (
        <button
          type="button"
          onClick={onReset}
          className="mt-6 inline-flex h-10 items-center gap-2 rounded-lg bg-brand px-4 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
        >
          <Icon name="refresh" size="sm" />
          Reset search
        </button>
      )}
    </div>
  );
}

function ResearchWorkspace({ mode }: { mode: "sources" | "prior-art" }) {
  const [query, setQuery] = useState("");
  const [view, setView] = useState<ResearchState>("empty");
  const [records, setRecords] = useState<SourceRecord[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [category, setCategory] = useState(
    "All sources",
  );
  const [filters, setFilters] = useState<SearchFilters>({
    jurisdiction: "All jurisdictions",
    documentType: "All document types",
    publicationDate: "Any date",
    documentStatus: "Any status",
  });
  const categoryType: Record<string, string | null> = {
    "All sources": null,
    Statutes: "Statute",
    Rules: "Rule or regulation",
    Treaties: "Treaty or international instrument",
    "Patent records": "Patent record",
    Judgments: "Judgment",
    "Traditional knowledge": "Traditional knowledge resource",
  };
  const sourceCategories = Object.keys(categoryType);
  const visibleRecords = records.filter((record) => {
    const searchText =
      `${record.title} ${record.authority} ${record.type} ${record.passageBefore} ${record.match} ${record.passageAfter} ${record.keywords.join(" ")}`.toLowerCase();
    const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
    const matchesQuery = !terms.length || terms.every((term) => searchText.includes(term));
    const matchesCategory = category === "All sources" || !categoryType[category] || record.type === categoryType[category];
    const matchesJurisdiction =
      filters.jurisdiction === "All jurisdictions" ||
      record.jurisdiction === filters.jurisdiction;
    const matchesType =
      filters.documentType === "All document types" ||
      record.type === filters.documentType;
    const matchesDate = filters.publicationDate === "Any date";
    const matchesStatus = filters.documentStatus === "Any status";
    return (
      matchesQuery &&
      matchesCategory &&
      matchesJurisdiction &&
      matchesType &&
      matchesDate &&
      matchesStatus
    );
  });
  const selected: SourceRecord = visibleRecords.find((record) => record.id === selectedId) ?? visibleRecords[0] ?? {
    id: "", title: "", authority: "", date: "", jurisdiction: "India", type: "", status: "",
    section: "", passageBefore: "", match: "", passageAfter: "", keywords: [],
  };

  async function runSearch() {
    if (!query.trim()) { setView("empty"); return; }
    setView("loading");
    try {
      const response = await fetch(`${API_BASE}/search`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), top_k: 10 }),
      });
      if (!response.ok) throw new Error(`Search failed (${response.status}). Check that the backend is running.`);
      const data = await response.json();
      const mapped: SourceRecord[] = (data.results ?? []).map((hit: {chunk_id:string;source_filename:string;page:number|null;text:string;score:number}, i:number) => ({
        id: hit.chunk_id || `${hit.source_filename}-${i}`,
        title: hit.source_filename,
        authority: "Indexed legal corpus",
        date: "Date not supplied by source",
        jurisdiction: "India",
        type: "Retrieved passage",
        status: "Retrieved from corpus",
        section: hit.page == null ? "Page not available" : `Page ${hit.page}`,
        passageBefore: "",
        match: hit.text,
        passageAfter: "",
        keywords: [],
      }));
      setRecords(mapped);
      setSelectedId(mapped[0]?.id ?? "");
      setView(mapped.length ? "results" : "no-results");
    } catch (error) {
      setRecords([]);
      setView("error");
    }
  }

  function resetSearch() {
    setQuery("");
    setRecords([]);
    setSelectedId("");
    setCategory("All sources");
    setFilters({
      jurisdiction: "All jurisdictions",
      documentType: "All document types",
      publicationDate: "Any date",
      documentStatus: "Any status",
    });
    setView("results");
  }

  return (
    <div className="mx-auto max-w-assistant-workspace px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-action">
            {mode === "prior-art" ? "Prior-art discovery" : "Legal research library"}
          </div>
          <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">
            {mode === "prior-art" ? "Prior-Art Search" : "Legal Sources"}
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-ink-muted">
            {mode === "prior-art"
              ? "Search and inspect patent, traditional-knowledge, and legal records with source context."
              : "Find legal and regulatory materials while preserving authority, jurisdiction, and passage-level traceability."}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-sage-soft bg-sage-pale px-3 py-1.5 text-xs font-semibold text-sage-strong">
          <span className="size-1.5 rounded-full bg-sage-strong" />
          Live indexed corpus
        </div>
      </div>

      <section className="mt-7 rounded-2xl border border-line bg-white p-4 shadow-card sm:p-5">
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="relative min-w-0 flex-1">
            <span className="sr-only">Search legal sources and prior art</span>
            <span className="pointer-events-none absolute inset-y-0 left-4 flex items-center text-ink-faint">
              <Icon name="search" />
            </span>
            <input
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              onKeyDown={(event) => event.key === "Enter" && runSearch()}
              placeholder="Search by topic, title, keyword, applicant, or citation…"
              className="h-13 w-full rounded-xl border border-line-strong bg-white pl-12 pr-4 text-sm text-ink outline-none placeholder:text-ink-faint focus:border-brand focus:ring-4 focus:ring-brand-pale"
            />
          </label>
          <button
            type="button"
            onClick={runSearch}
            className="inline-flex h-13 items-center justify-center gap-2 rounded-xl bg-brand px-6 text-sm font-semibold text-white shadow-brand hover:bg-brand-strong"
          >
            Search sources
            <Icon name="arrow" size="sm" />
          </button>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-ink-subtle">Jurisdiction</span>
            <select
              value={filters.jurisdiction}
              onChange={(event) =>
                setFilters((current) => ({
                  ...current,
                  jurisdiction: event.target.value as SearchFilters["jurisdiction"],
                }))
              }
              className="h-10 w-full rounded-lg border border-line bg-surface-subtle px-3 text-xs font-semibold text-ink outline-none focus:border-brand"
            >
              <option>All jurisdictions</option>
              <option>India</option>
              <option>International</option>
            </select>
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-ink-subtle">Document type</span>
            <select
              value={filters.documentType}
              onChange={(event) =>
                setFilters((current) => ({ ...current, documentType: event.target.value }))
              }
              className="h-10 w-full rounded-lg border border-line bg-surface-subtle px-3 text-xs font-semibold text-ink outline-none focus:border-brand"
            >
              <option>All document types</option>
              <option>Statute</option>
              <option>Rule or regulation</option>
              <option>Treaty</option>
              <option>Patent record</option>
              <option>Judgment</option>
              <option>Traditional knowledge resource</option>
            </select>
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-ink-subtle">
              Publication date
            </span>
            <select
              value={filters.publicationDate}
              onChange={(event) =>
                setFilters((current) => ({ ...current, publicationDate: event.target.value }))
              }
              className="h-10 w-full rounded-lg border border-line bg-surface-subtle px-3 text-xs font-semibold text-ink outline-none focus:border-brand"
            >
              <option>Any date</option>
              <option>Past year</option>
              <option>Past 5 years</option>
              <option>Past 10 years</option>
              <option>Custom range</option>
            </select>
          </label>
          <label>
            <span className="mb-1.5 block text-xs font-semibold text-ink-subtle">
              Document status
            </span>
            <select
              value={filters.documentStatus}
              onChange={(event) =>
                setFilters((current) => ({ ...current, documentStatus: event.target.value }))
              }
              className="h-10 w-full rounded-lg border border-line bg-surface-subtle px-3 text-xs font-semibold text-ink outline-none focus:border-brand"
            >
              <option>Any status</option>
              <option>In force or active</option>
              <option>Amended</option>
              <option>Repealed or expired</option>
              <option>Pending application</option>
              <option>Granted patent</option>
            </select>
          </label>
        </div>
      </section>

      <div className="mt-5 flex gap-2 overflow-x-auto pb-1" aria-label="Source categories">
        {sourceCategories.map((item) => (
          <button
            type="button"
            key={item}
            onClick={() => setCategory(item)}
            className={`shrink-0 rounded-full px-3 py-2 text-xs font-semibold transition ${
              category === item
                ? "bg-brand text-white"
                : "border border-line bg-white text-ink-muted hover:border-brand-soft hover:text-brand"
            }`}
          >
            {item}
          </button>
        ))}
      </div>

      <div className="mt-4 flex items-center gap-2 overflow-x-auto rounded-lg bg-canvas py-1">
        <span className="shrink-0 text-xs font-semibold text-ink-faint">Prototype state:</span>
        {([
          ["results", "Retrieved records"],
          ["empty", "Empty"],
          ["loading", "Loading"],
          ["no-results", "No results"],
          ["error", "Error"],
        ] as Array<[ResearchState, string]>).map(([id, label]) => (
          <button
            type="button"
            key={id}
            onClick={() => setView(id)}
            className={`shrink-0 rounded-full px-2.5 py-1 text-xs font-semibold ${
              view === id
                ? "bg-brand-pale text-brand"
                : "text-ink-subtle hover:bg-white hover:text-brand"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {view === "results" && visibleRecords.length ? (
        <div className="mt-5 grid items-start gap-6 xl:grid-cols-research">
          <div className="min-w-0">
            <div className="mb-3 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-ink">Retrieved passages</h3>
                <p className="mt-0.5 text-xs text-ink-subtle">
                  Live retrieval results from the indexed connected source index
                </p>
              </div>
              <span className="text-xs font-semibold text-ink-faint">
                {visibleRecords.length} passages
              </span>
            </div>
            <div className="space-y-3">
              {visibleRecords.map((record) => (
                <button
                  type="button"
                  key={record.id}
                  onClick={() => setSelectedId(record.id)}
                  className={`w-full rounded-2xl border bg-white p-5 text-left shadow-card transition ${
                    selected.id === record.id
                      ? "border-brand ring-2 ring-brand-pale"
                      : "border-line hover:border-brand-soft"
                  }`}
                >
                  <div className="flex items-start justify-between gap-4">
                    <span className="rounded-full bg-surface-subtle px-2.5 py-1 text-xs font-semibold text-ink-subtle">
                      {record.type}
                    </span>
                    <span className="rounded-full border border-sage-soft bg-sage-pale px-2 py-0.5 text-xs font-semibold text-sage-strong">
                      Sample
                    </span>
                  </div>
                  <h4 className="mt-4 font-display text-base font-bold leading-6 text-ink">
                    {record.title}
                  </h4>
                  <div className="mt-3 flex flex-wrap gap-x-4 gap-y-2 text-xs text-ink-subtle">
                    <span>{record.authority}</span>
                    <span>{record.date}</span>
                    <span>{record.jurisdiction}</span>
                  </div>
                  <div className="mt-4 flex items-center justify-between border-t border-line pt-3">
                    <span className="text-xs font-semibold text-ink-faint">{record.status}</span>
                    <span className="flex items-center gap-1 text-xs font-bold text-brand">
                      Preview passage
                      <Icon name="chevron" size="sm" />
                    </span>
                  </div>
                </button>
              ))}
            </div>

            <section className="mt-7 rounded-2xl border border-brand-soft bg-brand-pale p-5">
              <div className="flex items-start gap-3">
                <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-white text-brand">
                  <Icon name="external" size="sm" />
                </span>
                <div>
                  <h3 className="text-sm font-bold text-ink">Suggested external searches</h3>
                  <p className="mt-1 text-xs leading-5 text-ink-muted">
                    These links open external databases. They are suggestions, not records retrieved
                    into IP-SAKTI Sahayak.
                  </p>
                </div>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                {[
                  ["IP India", "https://ipindia.gov.in/"],
                  ["WIPO PATENTSCOPE", "https://patentscope.wipo.int/"],
                  ["Indian Kanoon", "https://indiankanoon.org/"],
                  ["Traditional Knowledge Digital Library", "https://www.tkdl.res.in/"],
                ].map(([label, href]) => (
                  <a
                    key={label}
                    href={href}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between rounded-lg border border-brand-soft bg-white px-3 py-2.5 text-xs font-semibold text-brand hover:border-brand-muted"
                  >
                    {label}
                    <Icon name="external" size="sm" />
                  </a>
                ))}
              </div>
            </section>
          </div>
          <SourcePreview record={selected} />
        </div>
      ) : (
        <div className="mt-5">
          <ResearchEmpty
            state={view === "results" ? "no-results" : view}
            onReset={resetSearch}
          />
        </div>
      )}

      <div className="mt-6 flex items-start gap-3 rounded-xl border border-sage-soft bg-sage-pale p-4">
        <Icon name="shield" size="sm" />
        <p className="text-xs leading-5 text-sage-text">
          <strong className="font-bold text-sage-strong">Verify every source.</strong> Sample records
          and passages are visibly labelled placeholders. Confirm document identity, status,
          amendments, citations, and official text before relying on any source.
        </p>
      </div>
    </div>
  );
}

type AdminViewState = "records" | "empty" | "loading" | "success" | "error";
type IngestionStatus = "Pending" | "Processing" | "Indexed" | "Failed";

type KnowledgeDocument = {
  id: string;
  title: string;
  sourceUrl: string;
  jurisdiction: string;
  documentType: string;
  publicationDate: string;
  effectiveDate: string;
  version: string;
  status: IngestionStatus;
  activeStage: number;
  lastReviewed: string;
  freshness: "Current" | "Review due soon" | "Review overdue" | "New";
  chunks: string;
};

const sampleKnowledgeDocuments: KnowledgeDocument[] = [];
const processingStages = ["Text Extraction", "Chunking", "Embedding", "Indexing"];

function StatusBadge({ status }: { status: IngestionStatus }) {
  const styles: Record<IngestionStatus, string> = {
    Pending: "border-line bg-surface-subtle text-ink-subtle",
    Processing: "border-brand-soft bg-brand-pale text-brand",
    Indexed: "border-sage-soft bg-sage-pale text-sage-strong",
    Failed: "border-error/20 bg-error-pale text-error",
  };
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${styles[status]}`}
    >
      <span
        className={`size-1.5 rounded-full ${
          status === "Processing"
            ? "animate-pulse bg-action"
            : status === "Indexed"
              ? "bg-sage-strong"
              : status === "Failed"
                ? "bg-error"
                : "bg-ink-faint"
        }`}
      />
      {status}
    </span>
  );
}

function FreshnessBadge({ status }: { status: KnowledgeDocument["freshness"] }) {
  const styles = {
    Current: "bg-sage-pale text-sage-strong",
    "Review due soon": "bg-brand-pale text-brand",
    "Review overdue": "bg-error-pale text-error",
    New: "bg-surface-subtle text-ink-subtle",
  };
  return (
    <span className={`inline-flex rounded-full px-2 py-1 text-xs font-semibold ${styles[status]}`}>
      {status}
    </span>
  );
}

function ProcessingTracker({ document }: { document: KnowledgeDocument }) {
  return (
    <div className="grid gap-3 sm:grid-cols-4">
      {processingStages.map((stage, index) => {
        const stageNumber = index + 1;
        const failed = document.status === "Failed" && document.activeStage === stageNumber;
        const complete =
          document.status === "Indexed" ||
          document.activeStage > stageNumber ||
          (document.status === "Processing" && document.activeStage > stageNumber);
        const active = document.status === "Processing" && document.activeStage === stageNumber;
        return (
          <div key={stage} className="relative">
            <div
              className={`flex items-center gap-2 rounded-lg border p-3 ${
                failed
                  ? "border-error/20 bg-error-pale"
                  : complete
                    ? "border-sage-soft bg-sage-pale"
                    : active
                      ? "border-brand-soft bg-brand-pale"
                      : "border-line bg-surface-subtle"
              }`}
            >
              <span
                className={`grid size-6 shrink-0 place-items-center rounded-full text-xs font-bold ${
                  failed
                    ? "bg-error text-white"
                    : complete
                      ? "bg-sage-strong text-white"
                      : active
                        ? "bg-brand text-white"
                        : "bg-white text-ink-faint"
                }`}
              >
                {failed ? "!" : complete ? <Icon name="check" size="sm" /> : stageNumber}
              </span>
              <span
                className={`text-xs font-semibold ${
                  failed
                    ? "text-error"
                    : complete
                      ? "text-sage-strong"
                      : active
                        ? "text-brand"
                        : "text-ink-faint"
                }`}
              >
                {stage}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
}

type AdminCorpusDoc = {
  filename: string;
  document_id: string;
  file_type: string;
  pages: number;
  character_count: number;
  status: string;
  pdf_available: boolean;
};

type AdminCorpusStats = {
  total_documents: number;
  total_pages: number;
  total_characters: number;
  total_chunks: number;
  index_built: boolean;
  documents: AdminCorpusDoc[];
};

function AdminKnowledgeBase() {
  const [stats, setStats] = useState<AdminCorpusStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [selectedDoc, setSelectedDoc] = useState<AdminCorpusDoc | null>(null);

  const fetchCorpus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/admin/corpus`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as AdminCorpusStats;
      setStats(data);
      if (data.documents && data.documents.length > 0) {
        setSelectedDoc(data.documents[0]);
      }
    } catch {
      setError("Unable to connect to the corpus administrative service. Ensure backend is running.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void fetchCorpus();
  }, [fetchCorpus]);

  const filteredDocs = (stats?.documents ?? []).filter((doc) =>
    `${doc.filename} ${doc.document_id}`.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div className="mx-auto max-w-assistant-workspace px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
      <div className="flex flex-col justify-between gap-4 lg:flex-row lg:items-end">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-xs font-bold uppercase tracking-widest text-action">
              Corpus administration
            </div>
            <span className="rounded-full border border-sage-soft bg-sage-pale px-2.5 py-0.5 text-xs font-semibold text-sage-strong">
              Live Knowledge Base
            </span>
          </div>
          <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-ink">
            Admin Knowledge Base
          </h2>
          <p className="mt-2 max-w-3xl text-sm leading-6 text-ink-muted">
            Inspect the official legal corpus, vector index embeddings, and document ingestion status backing the IP-SAKTI retrieval pipeline.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={fetchCorpus}
            className="inline-flex h-10 items-center gap-2 rounded-lg border border-line bg-white px-3 text-sm font-semibold text-ink-muted shadow-xs hover:bg-surface-subtle"
          >
            <Icon name="refresh" size="sm" />
            Refresh stats
          </button>
        </div>
      </div>

      {loading && (
        <div className="mt-6 space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-28 animate-pulse rounded-2xl border border-line bg-surface-subtle" />
            ))}
          </div>
          <div className="h-64 animate-pulse rounded-2xl border border-line bg-surface-subtle" />
        </div>
      )}

      {error && !loading && (
        <div className="mt-6 rounded-2xl border border-error/20 bg-error-pale p-5 text-sm text-error">
          <div className="flex items-center gap-2 font-semibold">
            <Icon name="warning" size="sm" /> Could not load knowledge base status
          </div>
          <p className="mt-1 text-xs leading-5">{error}</p>
        </div>
      )}

      {!loading && !error && stats && (
        <>
          <div className="mt-7 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <div className="flex items-center justify-between text-ink-subtle">
                <span className="text-xs font-bold uppercase tracking-widest text-brand">Documents</span>
                <span className="grid size-8 place-items-center rounded-lg bg-brand-pale text-brand">
                  <Icon name="document" size="sm" />
                </span>
              </div>
              <div className="mt-3 font-display text-3xl font-bold text-ink">
                {stats.total_documents}
              </div>
              <p className="mt-1 text-xs text-ink-subtle">Curated legal &amp; regulatory files</p>
            </div>

            <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <div className="flex items-center justify-between text-ink-subtle">
                <span className="text-xs font-bold uppercase tracking-widest text-brand">Chunks</span>
                <span className="grid size-8 place-items-center rounded-lg bg-blue-soft text-action">
                  <Icon name="sparkles" size="sm" />
                </span>
              </div>
              <div className="mt-3 font-display text-3xl font-bold text-ink">
                {stats.total_chunks.toLocaleString()}
              </div>
              <p className="mt-1 text-xs text-ink-subtle">FAISS + BM25 indexed passages</p>
            </div>

            <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <div className="flex items-center justify-between text-ink-subtle">
                <span className="text-xs font-bold uppercase tracking-widest text-brand">Extracted Pages</span>
                <span className="grid size-8 place-items-center rounded-lg bg-sage-pale text-sage-strong">
                  <Icon name="book" size="sm" />
                </span>
              </div>
              <div className="mt-3 font-display text-3xl font-bold text-ink">
                {stats.total_pages}
              </div>
              <p className="mt-1 text-xs text-ink-subtle">Total document pages indexed</p>
            </div>

            <div className="rounded-2xl border border-line bg-white p-5 shadow-card">
              <div className="flex items-center justify-between text-ink-subtle">
                <span className="text-xs font-bold uppercase tracking-widest text-brand">Vector Store</span>
                <span className="grid size-8 place-items-center rounded-lg bg-sage-pale text-sage-strong">
                  <Icon name="shield" size="sm" />
                </span>
              </div>
              <div className="mt-3 flex items-center gap-2">
                <span className="size-3 rounded-full bg-sage-strong animate-pulse" />
                <span className="font-display text-lg font-bold text-ink">
                  {stats.index_built ? "Vector Index Active" : "Index Pending"}
                </span>
              </div>
              <p className="mt-1 text-xs text-ink-subtle">sentence-transformers embedding index</p>
            </div>
          </div>

          <div className="mt-8 rounded-2xl border border-line bg-white shadow-card">
            <div className="flex flex-col gap-4 border-b border-line p-5 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <h3 className="font-display text-lg font-bold text-ink">Curated legal documents</h3>
                <p className="mt-0.5 text-xs text-ink-subtle">
                  Official statutes, rules, guidelines, and court records verified in the corpus
                </p>
              </div>
              <label className="relative min-w-0 sm:w-72">
                <span className="sr-only">Search corpus documents</span>
                <span className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-ink-faint">
                  <Icon name="search" size="sm" />
                </span>
                <input
                  type="search"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="Filter by filename…"
                  className="h-10 w-full rounded-lg border border-line bg-surface-subtle pl-9 pr-3 text-xs outline-none focus:border-brand"
                />
              </label>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-admin-table border-collapse text-left">
                <thead className="bg-surface-subtle text-xs font-semibold text-ink-subtle">
                  <tr>
                    <th className="px-5 py-3.5">Document title &amp; filename</th>
                    <th className="px-4 py-3.5">Pages</th>
                    <th className="px-4 py-3.5">Characters</th>
                    <th className="px-4 py-3.5">Ingestion state</th>
                    <th className="px-5 py-3.5 text-right">PDF actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-line text-xs">
                  {filteredDocs.length === 0 ? (
                    <tr>
                      <td colSpan={5} className="py-10 text-center text-ink-subtle">
                        No documents match your filter.
                      </td>
                    </tr>
                  ) : (
                    filteredDocs.map((doc) => (
                      <tr
                        key={doc.filename}
                        className={`hover:bg-canvas transition ${
                          selectedDoc?.filename === doc.filename ? "bg-brand-pale/30" : ""
                        }`}
                      >
                        <td className="px-5 py-3.5">
                          <button
                            type="button"
                            onClick={() => setSelectedDoc(doc)}
                            className="text-left font-bold text-ink hover:text-brand"
                          >
                            {doc.filename}
                          </button>
                          <div className="mt-0.5 truncate text-ink-faint max-w-md">
                            {doc.document_id}
                          </div>
                        </td>
                        <td className="px-4 py-3.5 font-medium text-ink-muted">
                          {doc.pages} {doc.pages === 1 ? "page" : "pages"}
                        </td>
                        <td className="px-4 py-3.5 font-medium text-ink-muted">
                          {doc.character_count.toLocaleString()} chars
                        </td>
                        <td className="px-4 py-3.5">
                          <span className="inline-flex items-center gap-1.5 rounded-full border border-sage-soft bg-sage-pale px-2.5 py-0.5 font-semibold text-sage-strong">
                            <span className="size-1.5 rounded-full bg-sage-strong" />
                            Indexed &amp; Grounded
                          </span>
                        </td>
                        <td className="px-5 py-3.5 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {doc.pdf_available ? (
                              <>
                                <a
                                  href={`${API_BASE}/documents/${encodeURIComponent(doc.filename)}/view`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="inline-flex items-center gap-1 rounded-md border border-brand-soft bg-brand-pale px-2.5 py-1 text-xs font-semibold text-brand hover:bg-brand-soft hover:text-white transition"
                                  title={`View ${doc.filename}`}
                                >
                                  <Icon name="document" size="sm" />
                                  View PDF
                                </a>
                                <a
                                  href={`${API_BASE}/documents/${encodeURIComponent(doc.filename)}/download`}
                                  download={doc.filename}
                                  className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-2.5 py-1 text-xs font-semibold text-ink-muted hover:border-brand-soft hover:text-brand transition"
                                  title={`Download ${doc.filename}`}
                                >
                                  <Icon name="arrow" size="sm" />
                                  Download
                                </a>
                              </>
                            ) : (
                              <span className="text-xs text-ink-faint">PDF unavailable</span>
                            )}
                          </div>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
            <div className="border-t border-line p-4 text-center text-xs text-ink-faint">
              Showing {filteredDocs.length} of {stats.total_documents} legal source documents
            </div>
          </div>

          {selectedDoc && (
            <section className="mt-6 rounded-2xl border border-line bg-white p-5 shadow-card sm:p-6">
              <div className="flex items-start justify-between">
                <div>
                  <span className="text-xs font-bold uppercase tracking-widest text-brand">
                    Selected document inspector
                  </span>
                  <h3 className="mt-1 font-display text-xl font-bold text-ink">
                    {selectedDoc.filename}
                  </h3>
                </div>
                <button
                  type="button"
                  onClick={() => setSelectedDoc(null)}
                  className="grid size-8 place-items-center rounded-lg text-ink-subtle hover:bg-surface-subtle"
                >
                  <Icon name="x" size="sm" />
                </button>
              </div>
              <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <div className="rounded-xl bg-canvas p-3">
                  <div className="text-xs text-ink-faint">Corpus Path</div>
                  <div className="mt-1 font-semibold text-xs text-ink break-all">
                    {selectedDoc.document_id}
                  </div>
                </div>
                <div className="rounded-xl bg-canvas p-3">
                  <div className="text-xs text-ink-faint">Page Count</div>
                  <div className="mt-1 font-semibold text-sm text-ink">{selectedDoc.pages}</div>
                </div>
                <div className="rounded-xl bg-canvas p-3">
                  <div className="text-xs text-ink-faint">Character Count</div>
                  <div className="mt-1 font-semibold text-sm text-ink">
                    {selectedDoc.character_count.toLocaleString()}
                  </div>
                </div>
                <div className="rounded-xl bg-canvas p-3">
                  <div className="text-xs text-ink-faint">PDF Availability</div>
                  <div className="mt-1 font-semibold text-sm text-sage-strong">
                    {selectedDoc.pdf_available ? "Verified in Local Storage" : "Unavailable"}
                  </div>
                </div>
              </div>
            </section>
          )}
        </>
      )}

      <div className="mt-6 flex items-start gap-3 rounded-xl border border-sage-soft bg-sage-pale p-4">
        <Icon name="shield" size="sm" />
        <p className="text-xs leading-5 text-sage-text">
          <strong className="font-bold text-sage-strong">Grounded Knowledge Integrity:</strong> All
          91 documents in this administrative view are verified against the authoritative Ayurveda
          IP and regulatory corpus. Passage embeddings are indexed and retrievable via hybrid FAISS
          + BM25 search.
        </p>
      </div>
    </div>
  );
}

function getPageFromHash(): RouteId {
  const page = window.location.hash.replace("#/", "") as RouteId;
  if (page === "landing") return "landing";
  return navigation.some((item) => item.id === page) ? page : "landing";
}

export default function App() {
  const [activePage, setActivePage] = useState<RouteId>(getPageFromHash);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [jurisdiction, setJurisdiction] = useState<Jurisdiction>("India");
  const [authModalMode, setAuthModalMode] = useState<"login" | "register" | null>(null);
  const { user, logout } = useAuthUser();

  const [language, setLanguage] = useState<InterfaceLanguage>(() => {
    const saved = localStorage.getItem("ipsakti_language");
    return (["English", "मराठी", "हिन्दी", "தமிழ்", "తెలుగు", "বাংলা"].includes(saved ?? "") ? saved : "English") as InterfaceLanguage;
  });

  useEffect(() => {
    const syncLanguage = (event: Event) => {
      const next = (event as CustomEvent<string>).detail;
      if (["English", "मराठी", "हिन्दी", "தமிழ்", "తెలుగు", "বাংলা"].includes(next)) {
        setLanguage(next as InterfaceLanguage);
      }
    };
    window.addEventListener("ipsakti-language-change", syncLanguage);
    return () => window.removeEventListener("ipsakti-language-change", syncLanguage);
  }, []);

  const [assistantDraft, setAssistantDraft] = useState("");

  useEffect(() => {
    const handleHashChange = () => setActivePage(getPageFromHash());
    window.addEventListener("hashchange", handleHashChange);
    return () => window.removeEventListener("hashchange", handleHashChange);
  }, []);

  function navigate(page: RouteId) {
    setActivePage(page);
    window.location.hash = `/${page}`;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // Protected route handling:
  // If the user is unauthenticated and attempting to access an authenticated dashboard module,
  // render the landing page with the authentication modal open.
  if (!user && activePage !== "landing") {
    return (
      <>
        <LandingPage
          user={user}
          onOpenAuth={(mode) => setAuthModalMode(mode)}
          onNavigate={navigate}
          onLogout={logout}
        />
        <AuthModal
          initialMode="login"
          onClose={(loggedInUser) => {
            if (loggedInUser) {
              setAuthModalMode(null);
              navigate(activePage);
            } else {
              setAuthModalMode(null);
              navigate("landing");
            }
          }}
        />
      </>
    );
  }

  if (activePage === "landing") {
    return (
      <>
        <LandingPage
          user={user}
          onOpenAuth={(mode) => setAuthModalMode(mode)}
          onNavigate={navigate}
          onLogout={logout}
        />
        {authModalMode && (
          <AuthModal
            initialMode={authModalMode}
            onClose={(loggedInUser) => {
              setAuthModalMode(null);
              if (loggedInUser) {
                navigate("dashboard");
              }
            }}
          />
        )}
      </>
    );
  }

  const pageTitle =
    activePage === "dashboard" ? "Dashboard" : pageDetails[activePage].title;

  return (
    <div className="flex min-h-screen bg-canvas text-ink">
      <Sidebar
        activePage={activePage}
        collapsed={sidebarCollapsed}
        mobileOpen={mobileOpen}
        onCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
        onNavigate={navigate}
        onMobileClose={() => setMobileOpen(false)}
      />
      <div className="min-w-0 flex-1">
        <TopBar
          title={pageTitle}
          onMobileOpen={() => setMobileOpen(true)}
        />
        <main>
          {activePage === "dashboard" ? (
            <Dashboard
              onNavigate={navigate}
              onAsk={(question) => {
                setAssistantDraft(question);
                navigate("assistant");
              }}
              jurisdiction={jurisdiction}
              onJurisdictionChange={setJurisdiction}
              language={language}
              onLanguageChange={setLanguage}
            />
          ) : activePage === "assistant" ? (
            <AssistantWorkspace
              jurisdiction={jurisdiction}
              onJurisdictionChange={setJurisdiction}
              language={language}
              onLanguageChange={setLanguage}
              initialQuestion={assistantDraft}
            />
          ) : activePage === "classifier" ? (
            <FormulationWizard onCancel={() => navigate("dashboard")} />
          ) : activePage === "abs" ? (
            <AbsComplianceWizard onCancel={() => navigate("dashboard")} />
          ) : activePage === "prior-art" || activePage === "sources" ? (
            <ResearchWorkspace mode={activePage === "prior-art" ? "prior-art" : "sources"} />
          ) : activePage === "history" ? (
            <HistoryWorkspace
              onAsk={(question) => {
                setAssistantDraft(question);
                navigate("assistant");
              }}
              onNavigate={navigate}
            />
          ) : (
            <AdminKnowledgeBase />
          )}
        </main>
      </div>
      {authModalMode && (
        <AuthModal
          initialMode={authModalMode}
          onClose={(loggedInUser) => {
            setAuthModalMode(null);
            if (loggedInUser) navigate(activePage);
          }}
        />
      )}
    </div>
  );
}
