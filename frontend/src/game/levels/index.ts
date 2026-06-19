import type { ComponentType } from "react";
import type { GameLevelProps } from "../types";
import Lesson1 from "./lesson1-see";
import Lesson2 from "./lesson2-spark-s-sentence-helper";

export interface LevelEntry {
  id: string;
  title: string;
  Component: ComponentType<GameLevelProps>;
}

export const LEVELS: LevelEntry[] = [
  {
    id: "lesson-1-see",
    title: "Teach Your Robot to See",
    Component: Lesson1,
  },
  {
    id: "lesson-2-spark-s-sentence-helper",
    title: "Spark's Sentence Helper",
    Component: Lesson2,
  },
];
