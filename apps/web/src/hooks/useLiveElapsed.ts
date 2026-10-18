"use client";

import { useEffect, useRef, useState } from "react";

/** Smooth 1s elapsed timer between status updates. */
export function useLiveElapsed(elapsedSeconds: number, live: boolean): number {
  const anchorRef = useRef({ wallMs: 0, elapsed: elapsedSeconds });
  const [display, setDisplay] = useState(elapsedSeconds);

  useEffect(() => {
    anchorRef.current = { wallMs: Date.now(), elapsed: elapsedSeconds };
    setDisplay(elapsedSeconds);
  }, [elapsedSeconds]);

  useEffect(() => {
    if (!live) {
      setDisplay(elapsedSeconds);
      return;
    }
    const tick = () => {
      const { wallMs, elapsed } = anchorRef.current;
      setDisplay(elapsed + Math.floor((Date.now() - wallMs) / 1000));
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [live, elapsedSeconds]);

  return live ? display : elapsedSeconds;
}
