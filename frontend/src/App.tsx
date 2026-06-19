import { useState } from "react";
import GameLevel from "./game/levels/lesson1-see";
import type { GameResult } from "./game/types";

// Dev harness for the hand-built worked example. It mounts ONE GameLevel, captures the contract
// callbacks (onComplete / onProgress), and offers a replay. This is a stand-in for the Sandpack
// play-test panel that arrives in B10 — same role: render a GameLevel and let a human play it.
export default function App() {
  const [result, setResult] = useState<GameResult | null>(null);
  const [runId, setRunId] = useState(0);

  return (
    <div className="min-h-full bg-gradient-to-b from-sky-50 to-white">
      <header className="pt-8 pb-2 text-center">
        <h1 className="text-3xl font-bold text-slate-800">Learn with Spark</h1>
        <p className="text-slate-500">
          Lesson 1 — Teach Your Robot to See{" "}
          <span className="text-slate-400">(hand-built worked example)</span>
        </p>
      </header>

      <main className="mx-auto max-w-3xl">
        <GameLevel
          key={runId}
          onComplete={(r) => setResult(r)}
          onProgress={(s) => console.log("progress:", s)}
        />

        {result && (
          <div className="mt-4 mb-10 text-center">
            <div className="inline-block rounded-xl bg-white px-5 py-3 shadow">
              <div className="text-slate-700">
                onComplete → <code className="rounded bg-slate-100 px-1">{JSON.stringify(result)}</code>
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
    </div>
  );
}
