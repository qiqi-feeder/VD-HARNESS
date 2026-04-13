"use client";

export function NeonBackground() {
  // Generate particles with deterministic positions
  const particles = Array.from({ length: 12 }, (_, i) => ({
    id: i,
    left: `${(i * 8.3) % 100}%`,
    top: `${(i * 13.7 + 20) % 100}%`,
    delay: `${i * 1.1}s`,
    duration: `${10 + (i % 5) * 2}s`,
    size: i % 3 === 0 ? 4 : 2,
    color: i % 3 === 0 ? "rgba(255, 0, 255, 0.5)" : i % 3 === 1 ? "rgba(0, 255, 255, 0.6)" : "rgba(168, 85, 247, 0.5)",
  }));

  return (
    <div className="neon-bg" aria-hidden="true">
      {/* Grid */}
      <div className="neon-grid" />

      {/* Gradient orbs */}
      <div className="neon-orb neon-orb-1" />
      <div className="neon-orb neon-orb-2" />
      <div className="neon-orb neon-orb-3" />
      <div className="neon-orb neon-orb-4" />

      {/* Scan lines */}
      <div className="neon-scanline" style={{ animationDelay: "0s" }} />
      <div className="neon-scanline" style={{ animationDelay: "4s" }} />

      {/* Floating particles */}
      {particles.map((p) => (
        <div
          key={p.id}
          className="neon-particle"
          style={{
            left: p.left,
            top: p.top,
            animationDelay: p.delay,
            animationDuration: p.duration,
            width: p.size,
            height: p.size,
            background: p.color,
            boxShadow: `0 0 6px ${p.color}`,
          }}
        />
      ))}

      {/* Horizontal glow lines */}
      <div className="neon-hline" style={{ top: "25%", left: "5%", width: "40%", animationDelay: "0s" }} />
      <div className="neon-hline" style={{ top: "55%", left: "30%", width: "50%", animationDelay: "3s" }} />
      <div className="neon-hline" style={{ top: "80%", left: "10%", width: "35%", animationDelay: "1.5s" }} />
    </div>
  );
}
