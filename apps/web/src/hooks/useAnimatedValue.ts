"use client";

import { useEffect, useRef, useState } from "react";

export function useAnimatedValue(target: number, duration = 400): number {
  const [value, setValue] = useState(target);
  const from = useRef(target);
  const start = useRef<number | null>(null);

  useEffect(() => {
    from.current = value;
    start.current = null;

    let frame: number;
    const step = (ts: number) => {
      if (start.current === null) start.current = ts;
      const t = Math.min((ts - start.current) / duration, 1);
      const eased = 1 - (1 - t) ** 3;
      setValue(from.current + (target - from.current) * eased);
      if (t < 1) frame = requestAnimationFrame(step);
    };

    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- animate from captured value at effect start
  }, [target, duration]);

  return value;
}
