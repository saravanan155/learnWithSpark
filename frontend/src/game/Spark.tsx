import { useState } from "react";
import type { SparkMood } from "./types";

// THE SPARK MASCOT WRAPPER (PLAN.md → "Spark mascot"). Levels render Spark ONLY through this
// component — never their own art. The real mascot is 6 pre-made transparent PNGs in
// /assets/spark/; until the owner drops those in, we fall back to a mood emoji so the game is
// fully playable today. Swapping in the PNGs needs no other code change.
const SPARK_IMAGES: Record<SparkMood, string> = {
  curious: "/assets/spark/spark_curious.png",
  proud: "/assets/spark/spark_proud.png",
  confused: "/assets/spark/spark_confused.png",
  excited: "/assets/spark/spark_excited.png",
  unsure: "/assets/spark/spark_unsure.png",
  confident: "/assets/spark/spark_confident.png",
};

const SPARK_EMOJI: Record<SparkMood, string> = {
  curious: "🤔",
  proud: "😄",
  confused: "😕",
  excited: "🤩",
  unsure: "😟",
  confident: "😎",
};

export function Spark({ mood, className = "" }: { mood: SparkMood; className?: string }) {
  const [failed, setFailed] = useState(false);

  // Placeholder until the real PNGs exist: a robot with a small mood badge.
  if (failed) {
    return (
      <div
        role="img"
        aria-label={`Spark the robot, feeling ${mood}`}
        className={`relative flex items-center justify-center select-none ${className}`}
      >
        <span className="text-7xl leading-none">🤖</span>
        <span className="absolute -bottom-1 -right-1 text-3xl">{SPARK_EMOJI[mood]}</span>
      </div>
    );
  }

  return (
    <img
      src={SPARK_IMAGES[mood]}
      alt={`Spark the robot, feeling ${mood}`}
      onError={() => setFailed(true)}
      className={`select-none pointer-events-none object-contain ${className}`}
    />
  );
}
