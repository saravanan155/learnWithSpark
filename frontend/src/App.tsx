import { useEffect, useState } from "react";
import { Spark } from "./game/Spark";
import { LEVELS } from "./game/levels";
import { Playtest } from "./playtest/Playtest";
import type { GameResult } from "./game/types";

// Dev shell:
//   - Welcome       — learner entry screen.
//   - Game          — the hand-built Lesson 1 worked example.
//   - Play-test     — paste a generated GameLevel.tsx and play it in Sandpack.
//   - Admin portal  — Streamlit pipeline runner, currently a separate dev app.

type Mode = "welcome" | "game" | "playtest";

const ADMIN_URL = import.meta.env.VITE_ADMIN_URL || "http://localhost:8501";

function modeFromHash(hash: string): Mode {
  if (hash === "#game") return "game";
  if (hash === "#playtest") return "playtest";
  return "welcome";
}

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
      <Spark mood={mood} className="h-40 w-60 max-w-full" />
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
  const [mode, setMode] = useState<Mode>(() => modeFromHash(window.location.hash));

  // Learner game state
  const [currentLevelIndex, setCurrentLevelIndex] = useState(0);
  const [result, setResult] = useState<GameResult | null>(null);
  const [runId, setRunId] = useState(0);

  // Play-test state: `draft` is the textarea; `code` is what Sandpack renders (on "Render").
  const [draft, setDraft] = useState(SAMPLE_CODE);
  const [code, setCode] = useState(SAMPLE_CODE);

  useEffect(() => {
    const syncMode = () => setMode(modeFromHash(window.location.hash));
    window.addEventListener("hashchange", syncMode);
    return () => window.removeEventListener("hashchange", syncMode);
  }, []);

  function navigate(next: Mode) {
    const hash = next === "welcome" ? "" : `#${next}`;
    if (window.location.hash !== hash) {
      window.location.hash = hash;
    }
    setMode(next);
  }

  function startGame() {
    setCurrentLevelIndex(0);
    setResult(null);
    setRunId((n) => n + 1);
    navigate("game");
  }

  function goToNextLevel() {
    if (currentLevelIndex >= LEVELS.length - 1) {
      return;
    }
    setCurrentLevelIndex((n) => n + 1);
    setResult(null);
    setRunId((n) => n + 1);
  }

  function replayCurrentLevel() {
    setResult(null);
    setRunId((n) => n + 1);
  }

  const navButtonClass = (target: Mode) =>
    `rounded-lg px-4 py-1.5 text-sm font-medium ${
      mode === target ? "bg-slate-800 text-white" : "bg-white text-slate-600 ring-1 ring-slate-200"
    }`;

  return (
    <div className="min-h-full bg-gradient-to-b from-sky-50 to-white">
      <header className="border-b border-slate-200 bg-white/80 px-4 py-3 backdrop-blur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3">
          <button
            onClick={() => navigate("welcome")}
            className="text-left text-xl font-bold text-slate-800"
          >
            Learn with Spark
          </button>
          <nav className="flex flex-wrap items-center gap-2">
            <button className={navButtonClass("welcome")} onClick={() => navigate("welcome")}>
              Welcome
            </button>
            <button className={navButtonClass("game")} onClick={startGame}>
              Game
            </button>
            <button className={navButtonClass("playtest")} onClick={() => navigate("playtest")}>
              Play-test
            </button>
            <a
              href={ADMIN_URL}
              className="rounded-lg bg-sky-500 px-4 py-1.5 text-sm font-semibold text-white shadow-sm"
            >
              Admin portal
            </a>
          </nav>
        </div>
      </header>

      {mode === "welcome" && (
        <main className="mx-auto flex min-h-[calc(100vh-64px)] max-w-5xl flex-col items-center justify-center px-4 py-10 text-center">
          <Spark mood="curious" className="h-72 w-[28rem] max-w-full" />
          <h1 className="mt-4 text-4xl font-bold text-slate-800 sm:text-5xl">
            Welcome to Learn with Spark
          </h1>
          <p className="mt-3 max-w-xl text-lg text-slate-600">
            Teach Spark how AI learns by playing a short visual game.
          </p>
          <button
            onClick={startGame}
            className="mt-7 rounded-xl bg-sky-500 px-7 py-3 text-lg font-semibold text-white shadow-sm transition hover:bg-sky-600"
          >
            Start the game
          </button>
        </main>
      )}

      {mode === "game" && (
        <main className="mx-auto max-w-3xl px-4 py-8">
          {currentLevelIndex < LEVELS.length ? (
            <>
              <div className="mb-4 text-center">
                <p className="text-sm font-medium text-slate-400">
                  Lesson {currentLevelIndex + 1} of {LEVELS.length}
                </p>
                <h1 className="text-2xl font-bold text-slate-800">
                  {LEVELS[currentLevelIndex].title}
                </h1>
              </div>
              {(() => {
                const ActiveLevel = LEVELS[currentLevelIndex].Component;
                return (
                  <ActiveLevel
                    key={`${LEVELS[currentLevelIndex].id}-${runId}`}
                    onComplete={(r) => setResult(r)}
                    onProgress={(s) => console.log("progress:", s)}
                  />
                );
              })()}
              {result && (
                <div className="mt-4 mb-10 text-center">
                  <div className="inline-block rounded-xl bg-white px-5 py-3 shadow">
                    <div className="text-slate-700">
                      Completed with score{" "}
                      <code className="rounded bg-slate-100 px-1">{result.score}</code>
                    </div>
                    <div className="mt-3 flex flex-wrap justify-center gap-2">
                      <button
                        onClick={replayCurrentLevel}
                        className="rounded-lg bg-white px-4 py-2 text-sm font-medium text-slate-700 ring-1 ring-slate-200"
                      >
                        Play again
                      </button>
                      {currentLevelIndex < LEVELS.length - 1 ? (
                        <button
                          onClick={goToNextLevel}
                          className="rounded-lg bg-sky-500 px-4 py-2 text-sm font-semibold text-white"
                        >
                          Next level
                        </button>
                      ) : (
                        <button
                          onClick={() => setCurrentLevelIndex(LEVELS.length)}
                          className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-white"
                        >
                          Finish game
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="flex min-h-[calc(100vh-160px)] flex-col items-center justify-center text-center">
              <Spark mood="confident" className="h-72 w-[28rem] max-w-full" />
              <h1 className="mt-4 text-4xl font-bold text-slate-800">You finished the game!</h1>
              <p className="mt-3 max-w-md text-lg text-slate-600">
                Spark learned to see, talk, and know its limits.
              </p>
              <button
                onClick={startGame}
                className="mt-7 rounded-xl bg-sky-500 px-7 py-3 text-lg font-semibold text-white shadow-sm"
              >
                Play from the start
              </button>
            </div>
          )}
        </main>
      )}

      {mode === "playtest" && (
        <main className="mx-auto max-w-5xl px-4 py-8">
          <p className="mb-2 text-center text-slate-500">
            Paste a generated <code>GameLevel.tsx</code> from <code>backend/generated/</code> and
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
                Render
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
