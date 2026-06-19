import { SandpackProvider, SandpackPreview } from "@codesandbox/sandpack-react";
import sparkSource from "../game/Spark.tsx?raw";
import typesSource from "../game/types.ts?raw";

// B10 — SANDPACK PLAY-TEST. Renders a generated GameLevel.tsx safely in an isolated iframe so the
// owner can play-test it (Gate 3). The generated code imports only `./Spark` + `./types`, so we
// hand Sandpack those exact files (read from the real frontend source via ?raw, single source of
// truth), a tiny host that mounts the level, and Tailwind via the Play CDN so classNames style.
// The level code itself never runs in the main app — Sandpack is the safety boundary.

const HOST_APP = `import { useState } from "react";
import GameLevel from "./GameLevel";
import type { GameResult } from "./types";

export default function App() {
  const [result, setResult] = useState<GameResult | null>(null);
  const [runId, setRunId] = useState(0);
  return (
    <div className="min-h-screen bg-gradient-to-b from-sky-50 to-white p-4">
      <GameLevel
        key={runId}
        onComplete={(r) => setResult(r)}
        onProgress={(s) => console.log("progress:", s)}
      />
      {result && (
        <div className="mt-4 text-center">
          <code className="rounded bg-white px-2 py-1 shadow">{JSON.stringify(result)}</code>
          <button
            onClick={() => { setResult(null); setRunId((n) => n + 1); }}
            className="ml-2 rounded-lg bg-slate-800 px-3 py-1 text-sm text-white"
          >
            Play again
          </button>
        </div>
      )}
    </div>
  );
}
`;

const INDEX_HTML = `<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <script src="https://cdn.tailwindcss.com"></script>
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
`;

export function Playtest({ code }: { code: string }) {
  return (
    <SandpackProvider
      template="react-ts"
      theme="light"
      customSetup={{ dependencies: { "framer-motion": "latest" } }}
      files={{
        "/GameLevel.tsx": code,
        "/Spark.tsx": sparkSource,
        "/types.ts": typesSource,
        "/App.tsx": HOST_APP,
        "/public/index.html": INDEX_HTML,
      }}
    >
      <SandpackPreview
        showOpenInCodeSandbox={false}
        showRefreshButton
        style={{ height: 560 }}
      />
    </SandpackProvider>
  );
}
