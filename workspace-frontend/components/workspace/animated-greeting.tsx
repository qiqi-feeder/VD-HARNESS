"use client";

import { useEffect, useRef, useState } from "react";

const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&*?!<>{}[]";
const GREETING = "有什么我可以帮您？";
const DECODE_DURATION = 1200;
const STEPS_PER_CHAR = 4;
const GLOW_FADE_DURATION = 2000; // ms for neon glow to fade out after decode completes

export function AnimatedGreeting() {
  const [display, setDisplay] = useState("");
  const [phase, setPhase] = useState<"waiting" | "decoding" | "glowing" | "settled">("waiting");
  const rafRef = useRef<number>(0);
  const startRef = useRef<number>(0);

  useEffect(() => {
    const chars = [...GREETING];
    const total = chars.length;
    const charDuration = DECODE_DURATION / total;

    function animate(timestamp: number) {
      if (!startRef.current) startRef.current = timestamp;
      const elapsed = timestamp - startRef.current;

      let result = "";
      for (let i = 0; i < total; i++) {
        const charStart = i * charDuration * 0.6;
        const charElapsed = elapsed - charStart;

        if (charElapsed < 0) {
          result += " ";
        } else if (charElapsed < charDuration) {
          const progress = charElapsed / charDuration;
          const step = Math.floor(progress * STEPS_PER_CHAR);
          if (step >= STEPS_PER_CHAR - 1) {
            result += chars[i];
          } else {
            result += CHARS[Math.floor(Math.random() * CHARS.length)];
          }
        } else {
          result += chars[i];
        }
      }

      setDisplay(result);

      const lastCharStart = (total - 1) * charDuration * 0.6;
      if (elapsed > lastCharStart + charDuration) {
        setDisplay(GREETING);
        setPhase("glowing");
        // Start glow fade after a beat
        setTimeout(() => setPhase("settled"), GLOW_FADE_DURATION);
        return;
      }

      rafRef.current = requestAnimationFrame(animate);
    }

    const timer = setTimeout(() => {
      setPhase("decoding");
      rafRef.current = requestAnimationFrame(animate);
    }, 300);

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <div className="relative inline-block">
      {/* Neon glow backdrop — intense during decode, fades after */}
      <div
        className="absolute inset-0 -inset-x-8 -inset-y-4 rounded-2xl pointer-events-none transition-opacity"
        style={{
          background: "radial-gradient(ellipse at center, rgba(0,212,255,0.15) 0%, rgba(168,85,247,0.08) 40%, transparent 70%)",
          opacity: phase === "decoding" || phase === "glowing" ? 1 : 0,
          transitionDuration: phase === "settled" ? "2000ms" : "300ms",
          filter: "blur(20px)",
        }}
      />

      <h1
        className="relative text-2xl font-medium tracking-tight font-heading"
        style={{
          color: phase === "settled" ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.95)",
          textShadow:
            phase === "decoding"
              ? "0 0 20px rgba(0,212,255,0.6), 0 0 40px rgba(168,85,247,0.3), 0 0 80px rgba(0,212,255,0.15)"
              : phase === "glowing"
                ? "0 0 30px rgba(0,212,255,0.5), 0 0 60px rgba(168,85,247,0.25), 0 0 100px rgba(0,212,255,0.1)"
                : "0 0 0 transparent",
          transition: "text-shadow 2s ease-out, color 2s ease-out",
          minHeight: "2em",
        }}
      >
        {display}
        {phase === "decoding" && (
          <span
            className="inline-block w-[2px] h-[1.1em] ml-0.5 align-middle animate-typing-cursor"
            style={{
              background: "linear-gradient(180deg, #00ffff, #a855f7)",
              boxShadow: "0 0 8px rgba(0,255,255,0.6)",
            }}
          />
        )}
      </h1>

      {/* Scan line effect during decode */}
      {phase === "decoding" && (
        <div
          className="absolute top-0 left-0 w-full h-full pointer-events-none overflow-hidden rounded-lg"
          style={{ mixBlendMode: "screen" }}
        >
          <div
            className="absolute top-0 left-0 w-full h-[2px]"
            style={{
              background: "linear-gradient(90deg, transparent, rgba(0,255,255,0.4), rgba(168,85,247,0.3), transparent)",
              animation: "neon-scanline 0.8s ease-in-out infinite",
            }}
          />
        </div>
      )}
    </div>
  );
}
