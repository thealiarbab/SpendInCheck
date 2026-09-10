import { useSyncExternalStore, type ReactNode } from "react";
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
 * They draw into a viewBox and scale to their container. The only thing a
 * narrow screen changes is which viewBox -- see the note on WIDE and NARROW.
 */

/* The plot area inside the viewBox, leaving room for the axis labels.
 *
 * There are two of these because an SVG scales its text along with
 * everything else. A 640-unit viewBox drawn 325 pixels wide on a phone
 * halves the axis labels to about five pixels, which is not small type, it
 * is decoration. Drawing the same chart into a narrower viewBox instead
 * means it barely scales at all, so ten units stays roughly ten pixels --
 * the labels keep their size and the chart loses width, which is the right
 * thing to give up.
 */
const WIDE = {
  width: 640, height: 220,
  pad: { top: 12, right: 8, bottom: 26, left: 52 },
};
const NARROW = {
  width: 360, height: 200,
  pad: { top: 10, right: 6, bottom: 24, left: 46 },
};

/* Below this the single-column layout has taken over and the charts are as
 * wide as they will get, so it is the point where scaling starts to bite. */
const NARROW_SCREEN = "(max-width: 40rem)";

function watchWidth(onChange: () => void) {
  const query = window.matchMedia(NARROW_SCREEN);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}

type Shape = typeof WIDE & {
  plot: { x: number; y: number; width: number; height: number };
};

/** Which viewBox this chart should draw into, kept current as the window
 *  is resized. */
function useShape(): Shape {
  const narrow = useSyncExternalStore(
    watchWidth,
    () => window.matchMedia(NARROW_SCREEN).matches,
    () => false,
  );
  const box = narrow ? NARROW : WIDE;
  return {
    ...box,
    plot: {
      x: box.pad.left,
      y: box.pad.top,
      width: box.width - box.pad.left - box.pad.right,
      height: box.height - box.pad.top - box.pad.bottom,
    },
  };
}

/** "2026-08" as "Aug", which is all that fits under a tick. */
function shortMonth(month: string): string {
  const [year, index] = month.split("-");
  return new Date(Number(year), Number(index) - 1, 1)
    .toLocaleDateString("en-IN", { month: "short" });
}

/** A scale from data values to pixels, with a little headroom. */
function scaleFor(values: number[], plot: Shape["plot"]) {
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
function Gridlines(
  { scale, plot }: { scale: ReturnType<typeof scaleFor>; plot: Shape["plot"] },
) {
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
function MonthAxis({ months, shape }: { months: string[]; shape: Shape }) {
  const { plot } = shape;
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
            y={shape.height - 8} textAnchor="middle"
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
  const shape = useShape();
  const { plot } = shape;
  const scale = scaleFor([...income, ...expense], plot);
  const step = plot.width / Math.max(months.length, 1);
  // A gutter of a fifth of the slot, so neighbouring months stay separate
  // pairs rather than reading as one wide block.
  const gutter = step / 5;
  const barWidth = Math.max(1, (step - gutter) / 2);
  const zero = scale.y(0);

  return (
    <svg className={styles.svg} viewBox={`0 0 ${shape.width} ${shape.height}`}
         role="img" aria-label="Income and expense for each month">
      <Gridlines scale={scale} plot={plot} />
      {months.map((month, index) => {
        const left = plot.x + step * index + gutter / 2;
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
      <MonthAxis months={months} shape={shape} />
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
  const shape = useShape();
  const { plot } = shape;
  const scale = scaleFor(values, plot);
  const step = plot.width / Math.max(values.length, 1);
  const at = (index: number) => plot.x + step * index + step / 2;

  const line = values.map((value, index) =>
    `${index === 0 ? "M" : "L"} ${at(index)} ${scale.y(value)}`).join(" ");
  const area = values.length
    ? `${line} L ${at(values.length - 1)} ${scale.y(scale.lowest)}`
      + ` L ${at(0)} ${scale.y(scale.lowest)} Z`
    : "";

  return (
    <svg className={styles.svg} viewBox={`0 0 ${shape.width} ${shape.height}`}
         role="img" aria-label={label}>
      <Gridlines scale={scale} plot={plot} />
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
      <MonthAxis months={months} shape={shape} />
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

/* A swatch is an HTML span, not an SVG shape, so it takes a background and
 * not a fill -- reusing the chart classes here would have produced three
 * invisible squares. */
const SWATCH = {
  income: styles.swatchIncome,
  expense: styles.swatchExpense,
  line: styles.swatchLine,
};

/** A key, so the colours in a chart mean something without hovering. */
export function Legend(
  { items }: { items: { label: string; kind: keyof typeof SWATCH }[] },
) {
  return (
    <ul className={styles.legend}>
      {items.map((item) => (
        <li key={item.label}>
          <span className={`${styles.swatch} ${SWATCH[item.kind]}`} aria-hidden="true" />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
