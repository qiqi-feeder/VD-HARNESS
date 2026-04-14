"use client";

import { useEffect, useRef, useState } from "react";

const CHARS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789@#$%&*?!<>{}[]";
const GREETING = "有什么我可以帮您？";
const DECODE_DURATION = 1200; // total ms
const STEPS_PER_CHAR = 4; // how many random chars before settling

export function AnimatedGreeting() {
  const [display, setDisplay] = useState("");
  const [done, setDone] = useState(false);
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
        const charStart = i * charDuration * 0.6; // overlap for wave effect
        const charElapsed = elapsed - charStart;

        if (charElapsed < 0) {
          // not started yet — show nothing or dim placeholder
          result += " ";
        } else if (charElapsed < charDuration) {
          // decoding phase — show random chars
          const progress = charElapsed / charDuration;
          const step = Math.floor(progress * STEPS_PER_CHAR);
          if (step >= STEPS_PER_CHAR - 1) {
            result += chars[i];
          } else {
            result += CHARS[Math.floor(Math.random() * CHARS.length)];
          }
        } else {
          // settled
          result += chars[i];
        }
      }

      setDisplay(result);

      // Check if all characters are done
      const lastCharStart = (total - 1) * charDuration * 0.6;
      if (elapsed > lastCharStart + charDuration) {
        setDisplay(GREETING);
        setDone(true);
        return;
      }

      rafRef.current = requestAnimationFrame(animate);
    }

    // Small initial delay before starting
    const timer = setTimeout(() => {
      rafRef.current = requestAnimationFrame(animate);
    }, 300);

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(rafRef.current);
    };
  }, []);

  return (
    <h1
      className={`text-2xl font-medium tracking-tight font-heading transition-all duration-700 ${
        done ? "greeting-glow text-white/95" : "text-white/70"
      }`}
      style={{ minHeight: "2em" }}
    >
      {display}
      {!done && (
        <span className="inline-block w-[2px] h-[1.1em] bg-[#00d4ff] ml-0.5 align-middle animate-typing-cursor" />
      )}
    </h1>
  );
}
