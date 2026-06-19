import { useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Spark } from "../Spark";
import type { GameLevelProps, SparkMood } from "../types";

// LESSON 1 — "Teach Your Robot to See" (AI learns from examples).
//
// HAND-BUILT WORKED EXAMPLE (PLAN.md → "The component contract" / build plan B9-React). The polished
// reference the coding agent pattern-matches against, so it follows the contract exactly:
//   - one default-exported GameLevel({ onComplete, onProgress })
//   - imports only react + framer-motion + <Spark>; no network / storage / external assets
//   - keyboard- AND touch-accessible (each item is a draggable <button>: drag, tap, or Enter)
//   - calls onComplete({ won, score }) when the child wins
//
// One level = one file under game/levels/. Every level (hand-built or agent-generated) exports the
// contract's default `GameLevel`; the filename says which lesson it is.
//
// Two takeaways, both shown by PLAYING (not narration):
//   1. AI only knows what YOU teach it.
//   2. When it doesn't know, it can be confidently WRONG — a "hallucination" (it guesses the
//      closest thing it was taught), or it admits "I don't know".
// Arc: TEACH a few items -> QUIZ Spark interactively (drag items, it answers) -> see a correct
// answer AND a hallucination -> finish.

type Item = { label: string; emoji: string };

// What the child teaches Spark in phase 1.
const ITEMS: Item[] = [
  { label: "apple", emoji: "🍎" },
  { label: "ball", emoji: "⚽" },
  { label: "dog", emoji: "🐶" },
  { label: "car", emoji: "🚗" },
  { label: "banana", emoji: "🍌" },
];

// The quiz tray: some items Spark was taught (it answers correctly) and some it was NOT.
// `hallucinateAs` = the taught label Spark will confidently (and wrongly) blurt out for an untaught
// item — its nearest known thing. No `hallucinateAs` => Spark honestly says "I don't know".
type QuizCard = Item & { untaught?: boolean; hallucinateAs?: string };

const QUIZ: QuizCard[] = [
  { label: "apple", emoji: "🍎" }, // taught -> correct
  { label: "dog", emoji: "🐶" }, // taught -> correct
  { label: "cat", emoji: "🐱", untaught: true, hallucinateAs: "dog" }, // confident + wrong
  { label: "orange", emoji: "🍊", untaught: true, hallucinateAs: "apple" }, // confident + wrong
  { label: "bus", emoji: "🚌", untaught: true, hallucinateAs: "car" }, // confident + wrong
  { label: "kite", emoji: "🪁", untaught: true }, // nothing close -> "I don't know"
];

const emojiOf = (label: string) => ITEMS.find((i) => i.label === label)?.emoji ?? "";

export default function GameLevel({ onComplete, onProgress }: GameLevelProps) {
  const [taught, setTaught] = useState<string[]>([]);
  const [phase, setPhase] = useState<"teach" | "quiz" | "won">("teach");
  const [mood, setMood] = useState<SparkMood>("curious");
  const [says, setSays] = useState("Hi! My brain is empty. Teach me by dragging things to me!");
  const [reveal, setReveal] = useState<string | null>(null); // the "actually it's a kite!" tag
  const [sawCorrect, setSawCorrect] = useState(false);
  const [sawHallucination, setSawHallucination] = useState(false);
  const [quizzes, setQuizzes] = useState(0);
  const dropRef = useRef<HTMLDivElement>(null);

  const remaining = ITEMS.filter((i) => !taught.includes(i.label));
  const readyToFinish = sawCorrect && sawHallucination;

  function overSpark(point: { x: number; y: number }) {
    const el = dropRef.current;
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return point.x >= r.left && point.x <= r.right && point.y >= r.top && point.y <= r.bottom;
  }

  function teach(item: Item) {
    if (taught.includes(item.label)) return;
    const next = [...taught, item.label];
    setTaught(next);
    setMood("proud");
    setSays(`Ooh! Now I know ${item.emoji} ${item.label}!`);
    if (next.length === ITEMS.length) {
      onProgress?.("quiz");
      window.setTimeout(() => {
        setPhase("quiz");
        setMood("curious");
        setSays("Now QUIZ me! Drag something onto me and I'll tell you what it is.");
      }, 700);
    } else {
      window.setTimeout(() => setMood("curious"), 600);
    }
  }

  function quiz(card: QuizCard) {
    setQuizzes((n) => n + 1);
    if (taught.includes(card.label)) {
      // Spark really learned this one.
      setMood("confident");
      setSays(`That's a ${card.label}! ${card.emoji} You taught me that. ✅`);
      setReveal(null);
      setSawCorrect(true);
    } else if (card.hallucinateAs) {
      // Confidently wrong — it guesses the nearest thing it WAS taught.
      setMood("confident");
      setSays(`Oh, easy! That's a ${card.hallucinateAs}! ${emojiOf(card.hallucinateAs)}`);
      setReveal(
        `🤫 Actually it's a ${card.label} ${card.emoji} — Spark was SURE but WRONG. ` +
          `It guessed the closest thing it knew. That's a hallucination!`,
      );
      setSawHallucination(true);
    } else {
      // Honest limit — nothing close enough to guess.
      setMood("unsure");
      setSays("Hmm… I don't know that one. You never taught me! 🤷");
      setReveal(null);
    }
  }

  function finish() {
    setPhase("won");
    setMood("proud");
    setSays("Now I get it — I only know what you teach me!");
    setReveal(null);
    onProgress?.("won");
    onComplete({ won: true, score: ITEMS.length + quizzes });
  }

  return (
    <div className="flex flex-col items-center px-4 py-6">
      {/* Spark + speech bubble. The card is the drop target for dragged item cards. */}
      <div className="flex flex-col items-center gap-3">
        <motion.div
          ref={dropRef}
          animate={{ scale: mood === "proud" || mood === "confident" ? 1.07 : 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 15 }}
          className="flex h-44 w-44 items-center justify-center rounded-3xl bg-sky-100 ring-4 ring-sky-200"
        >
          <Spark mood={mood} className="h-28 w-28" />
        </motion.div>
        <AnimatePresence mode="wait">
          <motion.div
            key={says}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="max-w-md rounded-2xl bg-white px-4 py-2 text-lg text-slate-700 shadow"
          >
            {says}
          </motion.div>
        </AnimatePresence>
        <AnimatePresence>
          {reveal && (
            <motion.div
              key={reveal}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-md rounded-2xl bg-rose-50 px-4 py-2 text-sm text-rose-700 ring-2 ring-rose-200"
            >
              {reveal}
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      {phase === "teach" && (
        <div className="mt-6 w-full">
          <p className="mb-3 text-center text-slate-500">
            Drag a card onto Spark (or tap it) to teach it. {taught.length}/{ITEMS.length} taught
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            {remaining.map((item) => (
              <motion.button
                key={item.label}
                drag
                dragSnapToOrigin
                whileHover={{ scale: 1.05 }}
                whileDrag={{ scale: 1.15, zIndex: 50 }}
                onDragEnd={(_, info) => {
                  if (overSpark(info.point)) teach(item);
                }}
                onClick={() => teach(item)}
                aria-label={`Teach Spark ${item.label}`}
                className="cursor-grab touch-none rounded-2xl bg-amber-100 px-5 py-4 text-center shadow ring-2 ring-amber-200 active:cursor-grabbing"
              >
                <div className="text-5xl">{item.emoji}</div>
                <div className="mt-1 font-medium text-slate-700">{item.label}</div>
              </motion.button>
            ))}
          </div>
        </div>
      )}

      {phase === "quiz" && (
        <div className="mt-6 w-full">
          <p className="mb-3 text-center text-slate-500">
            Drag a card onto Spark to quiz it. Try one you taught — and one you didn't!
          </p>
          <div className="flex flex-wrap justify-center gap-4">
            {QUIZ.map((card) => (
              <motion.button
                key={card.label}
                drag
                dragSnapToOrigin
                whileHover={{ scale: 1.05 }}
                whileDrag={{ scale: 1.15, zIndex: 50 }}
                onDragEnd={(_, info) => {
                  if (overSpark(info.point)) quiz(card);
                }}
                onClick={() => quiz(card)}
                aria-label={`Quiz Spark with ${card.label}`}
                className="cursor-grab touch-none rounded-2xl bg-violet-100 px-5 py-4 text-center shadow ring-2 ring-violet-200 active:cursor-grabbing"
              >
                <div className="text-5xl">{card.emoji}</div>
                <div className="mt-1 font-medium text-slate-700">{card.label}</div>
              </motion.button>
            ))}
          </div>

          <div className="mt-5 flex flex-col items-center gap-2">
            <div className="flex gap-4 text-sm text-slate-500">
              <span>{sawCorrect ? "✅" : "⬜"} saw a correct answer</span>
              <span>{sawHallucination ? "✅" : "⬜"} caught a hallucination</span>
            </div>
            {readyToFinish && (
              <motion.button
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.97 }}
                onClick={finish}
                className="rounded-2xl bg-sky-500 px-6 py-3 text-lg font-semibold text-white shadow"
              >
                I get it! Finish ▶
              </motion.button>
            )}
          </div>
        </div>
      )}

      {phase === "won" && (
        <motion.div
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className="mt-6 flex max-w-md flex-col items-center gap-3 text-center"
        >
          <div className="text-2xl font-semibold text-slate-800">🎉 You taught Spark to see!</div>
          <div className="rounded-2xl bg-emerald-50 px-5 py-3 text-slate-700 ring-2 ring-emerald-200">
            🧠 AI only knows what <b>you</b> teach it.
          </div>
          <div className="rounded-2xl bg-amber-50 px-5 py-3 text-slate-700 ring-2 ring-amber-200">
            🤔 When it doesn't know, it can be <b>confidently wrong</b> — that's a hallucination.
          </div>
        </motion.div>
      )}
    </div>
  );
}
