import type { ReactNode } from "react";
import { formatCompact, formatMoney } from "../lib/money";
import styles from "./charts.module.css";

/* Charts, drawn by hand in SVG.
 *
 * No charting library. Every one of these is a handful of points turned
 * into a path, and a library would arrive with its own idea of colour and
 * type that then has to be fought back into the theme -- which is the whole
 * problem, because these have to be correct in brass and paper at once.
 * Reading --chart-* directly is what makes that automatic.
 *
 * They draw into a viewBox and scale to their container, so "mobile" is not
 * a separate code path: the same SVG is simply narrower.
 */

/** The plot area inside the viewBox, leaving room for the axis labels. */
const BOX = { width: 640, height: 220 };
const PAD = { top: 12, right: 8, bottom: 26, left: 52 };

const plot = {
  x: PAD.left,
  y: PAD.top,
  width: BOX.width - PAD.left - PAD.right,
  height: BOX.height - PAD.top - PAD.bottom,
};

/** "2026-08" as "Aug", which is all that fits under a tick. */
function shortMonth(month: string): string {
  const [year, index] = month.split("-");
  return new Date(Number(year), Number(index) - 1, 1)
    .toLocaleDateString("en-IN", { month: "short" });
}

/** A scale from data values to pixels, with a little headroom. */
function scaleFor(values: number[]) {
  const highest = Math.max(0, ...values);
  const lowest = Math.min(0, ...values);
  // A flat series of zeros would divide by zero and draw nothing; give it a
  // nominal range so the baseline still appears.
  const span = highest - lowest || 1;
  return {
    highest,
    lowest,
    y: (value: number) =>
      plot.y + plot.height - ((value - lowest) / span) * plot.height,
  };
}

export function ChartFrame(
  { title, note, empty, children }:
  { title: string; note?: string; empty?: boolean; children: ReactNode },
) {
  return (
    <figure className={styles.figure}>
      <figcaption className={styles.caption}>
        <span className={styles.title}>{title}</span>
        {note && <span className={styles.note}>{note}</span>}
      </figcaption>
      {empty ? <p className={styles.empty}>Nothing to draw yet.</p> : children}
    </figure>
  );
}

/** Horizontal guide lines and the figures that label them. */
function Gridlines({ scale }: { scale: ReturnType<typeof scaleFor> }) {
  const steps = [0, 0.25, 0.5, 0.75, 1];
  return (
    <g>
      {steps.map((step) => {
        const value = scale.lowest + (scale.highest - scale.lowest) * step;
        const y = scale.y(value);
        return (
          <g key={step}>
            <line className={styles.grid} x1={plot.x} x2={plot.x + plot.width}
                  y1={y} y2={y} />
            <text className={styles.axis} x={plot.x - 6} y={y + 3}
                  textAnchor="end">
              {formatCompact(Math.round(value))}
            </text>
          </g>
        );
      })}
    </g>
  );
}

/** The month labels along the bottom, thinned so they never collide. */
function MonthAxis({ months }: { months: string[] }) {
  // At twelve points on a phone every label would overlap, so only every
  // other one is drawn once there are more than eight.
  const every = months.length > 8 ? 2 : 1;
  const step = plot.width / Math.max(months.length, 1);
  return (
    <g>
      {months.map((month, index) => (
        index % every === 0 && (
          <text
            key={month} className={styles.axis}
            x={plot.x + step * index + step / 2}
            y={BOX.height - 8} textAnchor="middle"
          >
            {shortMonth(month)}
          </text>
        )
      ))}
    </g>
  );
}

export interface Series {
  month: string;
  value: number;
}

/**
 * Income against expense, as paired bars.
 *
 * Paired rather than stacked: the question is which is bigger, and a stack
 * answers a different question -- the total, which for income and expense
 * together is a number that means nothing.
 */
export function PairedBars(
  { months, income, expense }:
  { months: string[]; income: number[]; expense: number[] },
) {
  const scale = scaleFor([...income, ...expense]);
  const step = plot.width / Math.max(months.length, 1);
  const barWidth = Math.max(2, (step - 6) / 2);
  const zero = scale.y(0);

  return (
    <svg className={styles.svg} viewBox={`0 0 ${BOX.width} ${BOX.height}`}
         role="img" aria-label="Income and expense for each month">
      <Gridlines scale={scale} />
      {months.map((month, index) => {
        const left = plot.x + step * index + 3;
        return (
          <g key={month}>
            <rect className={styles.income} x={left} width={barWidth}
                  y={scale.y(income[index])}
                  height={Math.max(0, zero - scale.y(income[index]))} />
            <rect className={styles.expense} x={left + barWidth} width={barWidth}
                  y={scale.y(expense[index])}
                  height={Math.max(0, zero - scale.y(expense[index]))} />
            <title>
              {shortMonth(month)}: {formatMoney(income[index])} in,{" "}
              {formatMoney(expense[index])} out
            </title>
          </g>
        );
      })}
      <MonthAxis months={months} />
    </svg>
  );
}

/**
 * A single line, for a running total.
 *
 * The zero line is drawn separately and only when the series crosses it,
 * because a cashflow that has never been negative does not need reminding
 * where zero is.
 */
export function LineChart(
  { months, values, label, fill }:
  { months: string[]; values: number[]; label: string; fill?: boolean },
) {
  const scale = scaleFor(values);
  const step = plot.width / Math.max(values.length, 1);
  const at = (index: number) => plot.x + step * index + step / 2;

  const line = values.map((value, index) =>
    `${index === 0 ? "M" : "L"} ${at(index)} ${scale.y(value)}`).join(" ");
  const area = values.length
    ? `${line} L ${at(values.length - 1)} ${scale.y(scale.lowest)}`
      + ` L ${at(0)} ${scale.y(scale.lowest)} Z`
    : "";

  return (
    <svg className={styles.svg} viewBox={`0 0 ${BOX.width} ${BOX.height}`}
         role="img" aria-label={label}>
      <Gridlines scale={scale} />
      {fill && area && <path className={styles.area} d={area} />}
      <path className={styles.line} d={line} />
      {values.map((value, index) => (
        <g key={months[index]}>
          <circle className={styles.point} cx={at(index)} cy={scale.y(value)} r="3" />
          <title>{shortMonth(months[index])}: {formatMoney(value)}</title>
        </g>
      ))}
      {scale.lowest < 0 && (
        <line className={styles.zero} x1={plot.x} x2={plot.x + plot.width}
              y1={scale.y(0)} y2={scale.y(0)} />
      )}
      <MonthAxis months={months} />
    </svg>
  );
}

/**
 * A ranked list as horizontal bars.
 *
 * Horizontal because the labels are names, and names set sideways under a
 * vertical bar are either rotated or truncated, both of which are worse
 * than simply turning the chart.
 */
export function RankedBars(
  { rows }: { rows: { label: string; value: number; caption?: string }[] },
) {
  const highest = Math.max(1, ...rows.map((row) => row.value));
  return (
    <ol className={styles.ranked}>
      {rows.map((row) => (
        <li key={row.label} className={styles.rank}>
          <span className={styles.rankLabel} title={row.label}>{row.label}</span>
          <span className={styles.track}>
            <span className={styles.bar}
                  style={{ width: `${(row.value / highest) * 100}%` }} />
          </span>
          <span className={styles.rankValue}>
            {formatMoney(row.value)}
            {row.caption && <em className={styles.rankCaption}>{row.caption}</em>}
          </span>
        </li>
      ))}
    </ol>
  );
}

/** A key, so the colours in a chart mean something without hovering. */
export function Legend({ items }: { items: { label: string; kind: string }[] }) {
  return (
    <ul className={styles.legend}>
      {items.map((item) => (
        <li key={item.label}>
          <span className={`${styles.swatch} ${styles[item.kind]}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
