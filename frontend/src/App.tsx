import { useState } from "react";
import Lesson1 from "./game/levels/lesson1-see";
import { Playtest } from "./playtest/Playtest";
import type { GameResult } from "./game/types";

// Dev shell with two tabs:
//   - "Worked example" — the hand-built Lesson 1 (the coding agent's reference).
//   - "Play-test"      — paste a generated GameLevel.tsx and play it in an isolated Sandpack iframe.
// The play-test tab is B10: it's how the owner play-tests an agent-generated level (Gate 3).

// A tiny sample so the play-test preview shows something on load. Replace it by pasting any file
// from backend/generated/<concept>__<idea>.tsx — generated levels import ./Spark and ./types, which
// Sandpack provides.
const SAMPLE_CODE = `import { useState } from "react";
import { Spark } from "./Spark";
import type { GameLevelProps, SparkMood } from "./types";

const CHOICES = [
  { id: "wall", label: "wall", emoji: "🧱", correct: true },
  { id: "apple", label: "apple", emoji: "🍎", correct: false },
  { id: "moon", label: "moon", emoji: "🌙", correct: false },
];

export default function GameLevel({ onComplete }: GameLevelProps) {
  const [mood, setMood] = useState<SparkMood>("curious");
  const [says, setSays] = useState('"The cat sat on the ___" — what comes next?');
  return (
    <div className="flex flex-col items-center gap-4 p-6 text-center">
      <Spark mood={mood} className="h-24 w-24" />
      <p className="text-lg text-slate-700">{says}</p>
      <div className="flex gap-3">
        {CHOICES.map((c) => (
          <button
            key={c.id}
            onClick={() => {
              if (c.correct) {
                setMood("excited");
                setSays("Yes — the wall!");
                onComplete({ won: true, score: 1 });
              } else {
                setMood("confused");
                setSays("Hmm, not quite — try again!");
              }
            }}
            className="rounded-2xl bg-amber-100 px-5 py-4 ring-2 ring-amber-200"
          >
            <div className="text-4xl">{c.emoji}</div>
            <div className="mt-1 font-medium text-slate-700">{c.label}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
`;

export default function App() {
  const [tab, setTab] = useState<"lesson1" | "playtest">("lesson1");

  // Worked-example tab state
  const [result, setResult] = useState<GameResult | null>(null);
  const [runId, setRunId] = useState(0);

  // Play-test tab state: `draft` is the textarea; `code` is what Sandpack renders (on "Render").
  const [draft, setDraft] = useState(SAMPLE_CODE);
  const [code, setCode] = useState(SAMPLE_CODE);

  const tabClass = (t: string) =>
    `rounded-lg px-4 py-1.5 text-sm font-medium ${
      tab === t ? "bg-slate-800 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"
    }`;

  return (
    <div className="min-h-full bg-gradient-to-b from-sky-50 to-white">
      <header className="pt-8 pb-3 text-center">
        <h1 className="text-3xl font-bold text-slate-800">Learn with Spark</h1>
        <div className="mt-3 flex justify-center gap-2">
          <button className={tabClass("lesson1")} onClick={() => setTab("lesson1")}>
            Worked example
          </button>
          <button className={tabClass("playtest")} onClick={() => setTab("playtest")}>
            Play-test a generated level
          </button>
        </div>
      </header>

      {tab === "lesson1" && (
        <main className="mx-auto max-w-3xl">
          <p className="mb-2 text-center text-slate-400">
            Lesson 1 — Teach Your Robot to See (hand-built worked example)
          </p>
          <Lesson1
            key={runId}
            onComplete={(r) => setResult(r)}
            onProgress={(s) => console.log("progress:", s)}
          />
          {result && (
            <div className="mt-4 mb-10 text-center">
              <div className="inline-block rounded-xl bg-white px-5 py-3 shadow">
                <div className="text-slate-700">
                  onComplete →{" "}
                  <code className="rounded bg-slate-100 px-1">{JSON.stringify(result)}</code>
                </div>
                <button
                  onClick={() => {
                    setResult(null);
                    setRunId((n) => n + 1);
                  }}
                  className="mt-2 rounded-lg bg-slate-800 px-4 py-2 text-sm text-white"
                >
                  Play again
                </button>
              </div>
            </div>
          )}
        </main>
      )}

      {tab === "playtest" && (
        <main className="mx-auto max-w-5xl px-4 pb-10">
          <p className="mb-2 text-center text-slate-500">
            Paste a generated <code>GameLevel.tsx</code> (from <code>backend/generated/</code>) and
            press <b>Render</b> to play it in an isolated sandbox.
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="flex flex-col">
              <textarea
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                spellCheck={false}
                className="h-[560px] w-full rounded-xl border border-slate-200 bg-white p-3 font-mono text-xs text-slate-700"
              />
              <button
                onClick={() => setCode(draft)}
                className="mt-2 self-start rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white"
              >
                Render ▶
              </button>
            </div>
            <div className="overflow-hidden rounded-xl border border-slate-200">
              <Playtest code={code} />
            </div>
          </div>
        </main>
      )}
    </div>
  );
}
