import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Spark } from "./Spark";
import type { GameLevelProps, SparkMood } from "./types";

// LESSON — "Spark's Sentence Helper"
// A language model helps PREDICT the word that best completes a sentence.
// Spark is stuck mid-story; the child drags the word that fits the blank.
// Each round shows the prediction idea: the words that "fit" vs ones that don't.

type Item = { id: string; label: string; emoji: string };

const ITEMS: Item[] = [
  { id: "cat", label: "cat", emoji: "🐈" },
  { id: "dog", label: "dog", emoji: "🐕" },
  { id: "house", label: "house", emoji: "🏠" },
  { id: "car", label: "car", emoji: "🚗" },
];

// Each round: a sentence with a blank and the one word that best completes it.
type Round = { before: string; after: string; answer: string };

const ROUNDS: Round[] = [
  { before: "The fluffy", after: "purred softly on the warm mat.", answer: "cat" },
  { before: "I took my", after: "for a long walk in the park.", answer: "dog" },
  { before: "We live in a big cozy", after: "with a red door.", answer: "house" },
  { before: "Dad drives a fast red", after: "down the road.", answer: "car" },
];

const emojiOf = (id: string) => ITEMS.find((i) => i.id === id)?.emoji ?? "";

export default function GameLevel({ onComplete, onProgress }: GameLevelProps) {
  const [round, setRound] = useState(0);
  const [filled, setFilled] = useState<string | null>(null);
  const [phase, setPhase] = useState<"play" | "won">("play");
  const [mood, setMood] = useState<SparkMood>("confused");
  const [says, setSays] = useState(
    "I'm writing a story but I'm stuck! Help me pick the word that fits.",
  );
  const [wrong, setWrong] = useState<string | null>(null);
  const [score, setScore] = useState(0);
  const blankRef = useRef<HTMLSpanElement>(null);

  const current = ROUNDS[round];

  function overBlank(point: { x: number; y: number }) {
    const el = blankRef.current;
    if (!el) return false;
    const r = el.getBoundingClientRect();
    // generous hit area
    return (
      point.x >= r.left - 30 &&
      point.x <= r.right + 30 &&
      point.y >= r.top - 30 &&
      point.y <= r.bottom + 30
    );
  }

  function tryWord(item: Item) {
    if (filled) return; // already solved this round
    if (item.id === current.answer) {
      setFilled(item.id);
      setWrong(null);
      setMood("excited");
      setSays("Yes! That word fits perfectly. ✅");
      const newScore = score + 1;
      setScore(newScore);
      onProgress?.(`solved-${current.answer}`);

      window.setTimeout(() => {
        if (round + 1 < ROUNDS.length) {
          setRound((r) => r + 1);
          setFilled(null);
          setMood("curious");
          setSays("Ooh, what comes next? Drag the best word into the blank!");
        } else {
          setPhase("won");
          setMood("proud");
          setSays("Great job! Spark can write a story now!");
          onProgress?.("won");
          onComplete({ won: true, score: newScore });
        }
      }, 1100);
    } else {
      setWrong(item.id);
      setMood("unsure");
      setSays("Try again, Spark needs a little help. That word doesn't quite fit.");
      window.setTimeout(() => setWrong(null), 900);
    }
  }

  return (
    <div className="flex flex-col items-center px-4 py-6">
      {/* Spark + speech bubble */}
      <div className="flex flex-col items-center gap-3">
        <motion.div
          animate={{ scale: mood === "excited" || mood === "proud" ? 1.07 : 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 15 }}
          className="flex h-48 w-72 max-w-[88vw] items-center justify-center rounded-3xl bg-sky-100 ring-4 ring-sky-200"
        >
          <Spark mood={mood} className="h-44 w-72 max-w-full" />
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
          <p className="mb-2 text-center text-sm text-slate-500">
            A language model predicts the word that fits best. Sentence {round + 1}/
            {ROUNDS.length}
          </p>

          {/* The sentence with a blank drop-target */}
          <motion.div
            key={round}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="mx-auto flex max-w-xl flex-wrap items-center justify-center gap-2 rounded-2xl bg-amber-50 px-5 py-5 text-2xl text-slate-700 ring-2 ring-amber-200"
          >
            <span>{current.before}</span>
            <motion.span
              ref={blankRef}
              animate={{
                backgroundColor: filled ? "#bbf7d0" : "#fde68a",
                scale: filled ? 1.05 : 1,
              }}
              className="inline-flex min-w-[5rem] items-center justify-center rounded-xl border-2 border-dashed border-amber-400 px-3 py-1 font-semibold"
            >
              {filled ? (
                <span className="flex items-center gap-1">
                  <span className="text-3xl">{emojiOf(filled)}</span>
                  {filled}
                </span>
              ) : (
                <span className="text-amber-500">＿＿</span>
              )}
            </motion.span>
            <span>{current.after}</span>
          </motion.div>

          {/* Word tray */}
          <div className="mt-6 flex flex-wrap justify-center gap-4">
            {ITEMS.map((item) => (
              <motion.button
                key={item.id}
                drag={!filled}
                dragSnapToOrigin
                whileHover={{ scale: 1.05 }}
                whileDrag={{ scale: 1.15, zIndex: 50 }}
                animate={
                  wrong === item.id
                    ? { x: [0, -8, 8, -8, 8, 0] }
                    : { x: 0 }
                }
                transition={{ duration: 0.4 }}
                onDragEnd={(_, info) => {
                  if (overBlank(info.point)) tryWord(item);
                }}
                onClick={() => tryWord(item)}
                disabled={!!filled}
                aria-label={`Put the word ${item.label} in the sentence`}
                className={`cursor-grab touch-none rounded-2xl px-5 py-4 text-center shadow ring-2 active:cursor-grabbing disabled:opacity-50 ${
                  wrong === item.id
                    ? "bg-rose-100 ring-rose-300"
                    : "bg-violet-100 ring-violet-200"
                }`}
              >
                <div className="text-5xl">{item.emoji}</div>
                <div className="mt-1 font-medium text-slate-700">{item.label}</div>
              </motion.button>
            ))}
          </div>
          <p className="mt-4 text-center text-xs text-slate-400">
            Drag a word into the blank — or tap it. ⭐ {score} fit so far
          </p>
        </div>
      )}

      {phase === "won" && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mt-6 flex max-w-md flex-col items-center gap-3 text-center"
        >
          <div className="text-2xl font-semibold text-slate-800">
            🎉 You finished Spark's story!
          </div>
          <div className="rounded-2xl bg-emerald-50 px-5 py-3 text-slate-700 ring-2 ring-emerald-200">
            🧠 A <b>language model</b> predicts the word that best fits a sentence.
          </div>
          <div className="rounded-2xl bg-amber-50 px-5 py-3 text-slate-700 ring-2 ring-amber-200">
            ✨ You helped Spark guess the next word — just like a real AI writer!
          </div>
        </motion.div>
      )}
    </div>
  );
}
