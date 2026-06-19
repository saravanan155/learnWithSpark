// THE COMPONENT CONTRACT — every generated level MUST match `GameLevelProps` exactly.
// (See PLAN.md → "The component contract".) The coding agent is told to obey this verbatim:
// export ONE default `GameLevel`, call `onComplete` on win, use only react + framer-motion + <Spark>.

export type SparkMood =
  | "curious"
  | "proud"
  | "confused"
  | "excited"
  | "unsure"
  | "confident";

export interface GameResult {
  won: boolean;
  score: number;
}

export interface GameLevelProps {
  onComplete: (result: GameResult) => void;
  onProgress?: (step: string) => void;
}
