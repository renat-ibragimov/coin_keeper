import type { ReactNode } from 'react';

import styles from './ProgressRing.module.css';

interface ProgressRingProps {
  /** 0..1 */
  value: number;
  size?: number;
  stroke?: number;
  /** Text drawn in the middle of the ring, e.g. "82%". */
  children?: ReactNode;
  'aria-label'?: string;
}

export function ProgressRing({
  value,
  size = 56,
  stroke = 5,
  children,
  ...rest
}: ProgressRingProps) {
  const clamped = Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  return (
    <span
      className={styles.ring}
      style={{ width: size, height: size }}
      role="img"
      aria-label={rest['aria-label']}
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true">
        <circle
          className={styles.track}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
        />
        <circle
          className={styles.value}
          cx={size / 2}
          cy={size / 2}
          r={radius}
          strokeWidth={stroke}
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - clamped)}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
        />
      </svg>
      {children ? <span className={`${styles.label} tabular`}>{children}</span> : null}
    </span>
  );
}
