"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Image from "next/image";
import {
  ArrowRight,
  Code2,
  GitFork,
  Shield,
  Brain,
  Zap,
  Terminal,
  Layers,
  Workflow,
} from "lucide-react";

import { NeonBackground } from "./neon-background";
import "./landing.css";

/* ── SVG Logo ── */
function VdFlowLogo({ size = 28 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
    >
      {/* Outer hexagon */}
      <path
        d="M16 2L28.124 9V23L16 30L3.876 23V9L16 2Z"
        stroke="url(#logo-grad)"
        strokeWidth="2"
        fill="none"
      />
      {/* Inner flow symbol */}
      <path
        d="M11 12L16 8L21 12L16 20L11 12Z"
        fill="url(#logo-grad)"
        opacity="0.8"
      />
      <circle cx="16" cy="14" r="2" fill="#050508" />
      <defs>
        <linearGradient id="logo-grad" x1="4" y1="2" x2="28" y2="30" gradientUnits="userSpaceOnUse">
          <stop stopColor="#00ffff" />
          <stop offset="0.5" stopColor="#a855f7" />
          <stop offset="1" stopColor="#ff00ff" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/* ── Intersection Observer for reveal ── */
function useReveal() {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("visible");
          }
        });
      },
      { threshold: 0.15, rootMargin: "0px 0px -40px 0px" }
    );

    const elements = container.querySelectorAll(".reveal");
    elements.forEach((el) => observer.observe(el));

    return () => observer.disconnect();
  }, []);

  return containerRef;
}

/* ── Feature Data ── */
const features = [
  {
    icon: Code2,
    title: "Research & Code",
    desc: "Autonomously browses the web, reads documentation, and writes production-ready code — all in one continuous flow.",
    image: "/landing/research-coding.png",
  },
  {
    icon: GitFork,
    title: "Subagent Parallelism",
    desc: "Spawns specialized subagents that work in parallel — research, code, and create simultaneously to slash completion time.",
    image: "/landing/subagent-parallel.png",
  },
  {
    icon: Shield,
    title: "Sandbox Protection",
    desc: "Every execution runs in an isolated sandbox with thread-level file isolation, preventing any cross-contamination between tasks.",
    image: "/landing/sandbox-protection.png",
  },
  {
    icon: Brain,
    title: "Memory & Skills",
    desc: "Persistent memory across sessions. Learned skills are stored and reused, making the agent smarter with every interaction.",
    image: "/landing/memory-skills.png",
  },
];

/* ── Capability cards ── */
const capabilities = [
  {
    icon: Terminal,
    title: "Tool Execution",
    desc: "File I/O, shell commands, browser automation, code analysis — 15+ built-in tools with extensible plugin architecture.",
  },
  {
    icon: Layers,
    title: "Context Compression",
    desc: "Intelligent middleware compresses context on the fly, enabling hour-long tasks without losing critical information.",
  },
  {
    icon: Workflow,
    title: "Task Orchestration",
    desc: "Multi-phase planning with guardrails and loop detection. From simple fixes to multi-file refactors, handled end-to-end.",
  },
];

/* ── Main Component ── */
export function LandingPage() {
  const router = useRouter();
  const revealRef = useReveal();

  const handleGetStarted = () => {
    router.push("/workspace/chats/new");
  };

  return (
    <div ref={revealRef}>
      <NeonBackground />

      <div className="landing-page">
        {/* ─── Navbar ─── */}
        <nav className="landing-nav">
          <a href="/" className="landing-nav-logo">
            <VdFlowLogo />
            <span>VD-FLOW</span>
          </a>
          <div className="landing-nav-actions">
            {/* GitHub link placeholder */}
            {/* <a href="#" className="cta-secondary" style={{ padding: "8px 16px", fontSize: "13px" }}>
              <Github className="h-4 w-4" /> GitHub
            </a> */}
            <button
              type="button"
              className="cta-button"
              onClick={handleGetStarted}
              style={{ padding: "10px 24px", fontSize: "13px" }}
            >
              Get Started
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </nav>

        {/* ─── Hero ─── */}
        <section className="landing-hero" id="hero">
          <div className="hero-badge">
            <span className="hero-badge-dot" />
            Open Source SuperAgent Framework
          </div>

          <h1 className="hero-title">
            An open-source{" "}
            <span className="title-gradient">SuperAgent harness</span>{" "}
            that researches, codes, and creates.
          </h1>

          <p className="hero-subtitle">
            With the help of sandboxes, memories, tools, skills and subagents,
            it handles different levels of tasks that could take minutes to hours.
          </p>

          <div style={{ display: "flex", gap: "16px", flexWrap: "wrap", justifyContent: "center" }}>
            <button
              type="button"
              className="cta-button"
              onClick={handleGetStarted}
              id="hero-cta"
            >
              Getting Started with vd-flow
              <ArrowRight className="h-5 w-5" />
            </button>
          </div>

          {/* Terminal Preview */}
          <div className="hero-terminal">
            <div className="hero-terminal-bar">
              <div className="hero-terminal-dot" />
              <div className="hero-terminal-dot" />
              <div className="hero-terminal-dot" />
            </div>
            <div className="hero-terminal-body">
              <div><span className="t-muted">$</span> <span className="t-green">vd-flow</span> <span className="t-white">start</span></div>
              <div className="t-muted" style={{ marginTop: 8 }}>{">"} Initializing agent harness...</div>
              <div><span className="t-cyan">✓</span> <span className="t-white">Sandbox</span> <span className="t-muted">isolated environment ready</span></div>
              <div><span className="t-cyan">✓</span> <span className="t-white">Memory</span> <span className="t-muted">persistent context loaded (3 sessions)</span></div>
              <div><span className="t-cyan">✓</span> <span className="t-white">Tools</span>  <span className="t-muted">15 tools registered</span></div>
              <div><span className="t-cyan">✓</span> <span className="t-white">Skills</span> <span className="t-muted">ui-ux-pro-max, code-review loaded</span></div>
              <div style={{ marginTop: 8 }}><span className="t-magenta">⚡</span> <span className="t-white">Agent ready.</span> <span className="t-cyan">Awaiting your task...</span></div>
            </div>
          </div>
        </section>

        {/* ─── Features ─── */}
        <section className="landing-section" id="features">
          <div className="section-label reveal">
            <span className="section-label-line" />
            Core Capabilities
          </div>
          <h2 className="section-title reveal">
            Everything you need to build{" "}
            <span style={{ color: "#00ffff" }}>autonomous agents</span>
          </h2>
          <p className="section-subtitle reveal">
            A complete framework with sandboxed execution, parallel subagents,
            persistent memory, and an extensible skill system.
          </p>

          <div className="features-grid reveal-stagger">
            {features.map((f) => (
              <div key={f.title} className="feature-card reveal">
                <div style={{ overflow: "hidden" }}>
                  <Image
                    src={f.image}
                    alt={f.title}
                    width={600}
                    height={220}
                    className="feature-card-image"
                    style={{ width: "100%", height: "220px", objectFit: "cover" }}
                  />
                </div>
                <div className="feature-card-body">
                  <div className="feature-card-icon">
                    <f.icon className="h-5 w-5" />
                  </div>
                  <h3 className="feature-card-title">{f.title}</h3>
                  <p className="feature-card-desc">{f.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ─── Architecture / Capabilities ─── */}
        <section className="landing-section" id="architecture">
          <div className="section-label reveal">
            <span className="section-label-line" />
            Under the Hood
          </div>
          <h2 className="section-title reveal">
            Built for{" "}
            <span style={{ color: "#a855f7" }}>complex, long-running tasks</span>
          </h2>
          <p className="section-subtitle reveal">
            Intelligent middleware handles context compression, loop detection,
            and multi-phase task orchestration automatically.
          </p>

          <div className="showcase-grid reveal-stagger">
            {capabilities.map((c) => (
              <div key={c.title} className="showcase-card reveal">
                <div className="showcase-icon">
                  <c.icon className="h-6 w-6" />
                </div>
                <h3 className="showcase-title">{c.title}</h3>
                <p className="showcase-desc">{c.desc}</p>
              </div>
            ))}
          </div>

          {/* Stats */}
          <div className="stats-row reveal">
            <div className="stat-item">
              <div className="stat-value">15+</div>
              <div className="stat-label">Built-in Tools</div>
            </div>
            <div className="stat-item">
              <div className="stat-value">∞</div>
              <div className="stat-label">Parallel Subagents</div>
            </div>
            <div className="stat-item">
              <div className="stat-value">100%</div>
              <div className="stat-label">Sandboxed</div>
            </div>
            <div className="stat-item">
              <div className="stat-value">24/7</div>
              <div className="stat-label">Persistent Memory</div>
            </div>
          </div>
        </section>

        {/* ─── Footer CTA ─── */}
        <footer className="landing-footer" id="footer">
          <div className="reveal">
            <h2 className="footer-cta-title">
              Ready to harness the power of{" "}
              <span style={{ color: "#00ffff" }}>autonomous AI</span>?
            </h2>
            <p className="footer-cta-subtitle">
              Start building with vd-flow today. Open source, fully extensible.
            </p>
            <button
              type="button"
              className="cta-button"
              onClick={handleGetStarted}
              id="footer-cta"
            >
              Getting Started with vd-flow
              <ArrowRight className="h-5 w-5" />
            </button>
          </div>

          <div className="footer-bottom">
            <a href="/" className="landing-nav-logo" style={{ gap: 8 }}>
              <VdFlowLogo size={20} />
              <span style={{ fontSize: 14 }}>VD-FLOW</span>
            </a>
            <span>Open Source SuperAgent Harness</span>
          </div>
        </footer>
      </div>
    </div>
  );
}
