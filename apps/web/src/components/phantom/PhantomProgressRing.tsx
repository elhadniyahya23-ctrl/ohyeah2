"use client";

import type { ReactNode } from "react";
import { useAnimatedValue } from "@/hooks/useAnimatedValue";

const R = 52;
const C = 2 * Math.PI * R;

interface RingProps {
  pct: number;
  detail?: ReactNode;
}

export function PhantomProgressRing({ pct, detail }: RingProps) {
  const animated = useAnimatedValue(pct);
  const offset = C - (animated / 100) * C;

  return (
    <div className="progress-ring-wrap">
      <svg className="progress-ring" viewBox="0 0 120 120">
        <circle className="progress-ring-bg" cx="60" cy="60" r={R} />
        <circle
          className="progress-ring-fill"
          cx="60"
          cy="60"
          r={R}
          strokeDasharray={C}
          strokeDashoffset={offset}
          style={{ transition: "stroke-dashoffset 0.4s ease" }}
        />
      </svg>
      <div className="progress-center">
        <span className="progress-pct">{Math.round(animated)}%</span>
        {detail != null && <span className="progress-detail">{detail}</span>}
      </div>
    </div>
  );
}

export function AnimatedNum({
  value,
  decimals = 0,
  className,
  duration = 400,
}: {
  value: number;
  decimals?: number;
  className?: string;
  duration?: number;
}) {
  const v = useAnimatedValue(value, duration);
  return (
    <span className={className}>
      {decimals > 0 ? v.toFixed(decimals) : Math.round(v)}
    </span>
  );
}
