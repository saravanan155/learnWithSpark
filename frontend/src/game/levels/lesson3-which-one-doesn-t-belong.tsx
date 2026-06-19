import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Spark } from "./Spark";
import type { GameLevelProps, SparkMood } from "./types";

// LESSON — "Which One Doesn't Belong?" (cut off date).
// Spark's brain only has movie info up to 2022. One movie came out AFTER that,
// so Spark has never heard of it. The child finds the odd one out.

type Item = { id: string; label: string; emoji: string; year: number };

const ITEMS: Item[] = [
  { id: "movie_1", label: "The Avengers", emoji: "🦸‍♂️", year: 2012 },
  { id: "movie_2", label: "The Lion King", emoji: "🦁", year: 1994 },
  { id: "movie_3", label: "Top Gun: Maverick", emoji: "🚀", year: 2023 },
  { id: "movie_4", label: "The Jungle Book", emoji: "🐒", year: 1967 },
];

const SOLUTION = "movie_3";

const sparkMoods = { start: "unsure" as SparkMood, won: "confident" as SparkMood };

export default function GameLevel({ onComplete, onProgress }: GameLevelProps) {
  const [phase, setPhase] = useState<"play" | "won">("play");
  const [mood, setMood] = useState<SparkMood>(sparkMoods.start);
  const [says, setSays] = useState(
    "My movie brain only knows things up to 2022. Which movie is NEW to me?",
  );
  const [wrongId, setWrongId] = useState<string | null>(null);
  const [tries, setTries] = useState(0);

  function choose(item: Item) {
    if (phase === "won") return;
    if (item.id === SOLUTION) {
      setPhase("won");
      setMood(sparkMoods.won);
      setSays(
        "Well done! Spark doesn't know about Top Gun: Maverick because it came out after 2022.",
      );
      onProgress?.("won");
      const score = Math.max(1, 5 - tries);
      onComplete({ won: true, score });
    } else {
      setTries((n) => n + 1);
      setWrongId(item.id);
      setMood("confused");
      setSays("Not quite, try again! Remember, Spark only knows things up to 2022.");
      window.setTimeout(() => {
        setWrongId(null);
        setMood(sparkMoods.start);
      }, 1200);
    }
  }

  return (
    <div className="flex flex-col items-center px-4 py-6">
      <div className="flex flex-col items-center gap-3">
        <motion.div
          animate={{ scale: mood === "confident" ? 1.07 : 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 15 }}
          className="flex h-52 w-80 max-w-[88vw] items-center justify-center rounded-3xl bg-sky-100 ring-4 ring-sky-200"
        >
          <Spark mood={mood} className="h-48 w-80 max-w-full" />
        </motion.div>

        <AnimatePresence mode="wait">
          <motion.div
            key={says}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="max-w-md rounded-2xl bg-white px-4 py-2 text-center text-lg text-slate-700 shadow"
          >
            {says}
          </motion.div>
        </AnimatePresence>
      </div>

      {phase === "play" && (
        <div className="mt-6 w-full">
          <p className="mb-3 text-center text-slate-500">
            Which movie doesn't belong in Spark's movie list? Tap it (or press Enter).
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            {ITEMS.map((item) => (
              <motion.button
                key={item.id}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.96 }}
                animate={
                  wrongId === item.id
                    ? { x: [0, -8, 8, -6, 6, 0] }
                    : { x: 0 }
                }
                transition={{ duration: 0.4 }}
                onClick={() => choose(item)}
                aria-label={`Choose ${item.label}`}
                className="w-40 cursor-pointer touch-none rounded-2xl bg-amber-100 px-5 py-4 text-center shadow ring-2 ring-amber-200"
              >
                <div className="text-5xl">{item.emoji}</div>
                <div className="mt-2 font-semibold text-slate-700">{item.label}</div>
              </motion.button>
            ))}
          </div>
        </div>
      )}

      {phase === "won" && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mt-6 flex max-w-md flex-col items-center gap-3 text-center"
        >
          <div className="text-2xl font-semibold text-slate-800">🎉 You found it!</div>
          <div className="rounded-2xl bg-emerald-50 px-5 py-3 text-slate-700 ring-2 ring-emerald-200">
            📅 Spark has a <b>cut off date</b> — it only knows things from before 2022.
          </div>
          <div className="rounded-2xl bg-sky-50 px-5 py-3 text-slate-700 ring-2 ring-sky-200">
            🚀 Anything newer, like <b>Top Gun: Maverick</b>, is a mystery to Spark!
          </div>
        </motion.div>
      )}
    </div>
  );
}
