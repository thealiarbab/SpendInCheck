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

/* Built once, and each answer kept. toLocaleDateString constructs a
   formatter on every call, and the Reports screen draws four charts from the
   same twelve months -- every tick label and every tooltip title asking for
   one of twelve strings that never change. Constructing the formatter is the
   expensive part of that, and none of it depended on anything per-render. */
const MONTH_LABEL = new Intl.DateTimeFormat("en-IN", { month: "short" });
const shortMonths = new Map<string, string>();

/** "2026-08" as "Aug", which is all that fits under a tick. */
function shortMonth(month: string): string {
  const known = shortMonths.get(month);
  if (known !== undefined) return known;

  const [year, index] = month.split("-");
  const label = MONTH_LABEL.format(new Date(Number(year), Number(index) - 1, 1));
  shortMonths.set(month, label);
  return label;
}

/**
 * A scale that spans the data rather than starting at zero.
 *
 * For series where the interesting question is movement against a
 * reference, not size against nothing. A tenth of the range is left as
 * padding at each end so the line never touches the frame.
 */
function scaleAround(values: number[], plot: Shape["plot"]) {
  const top = Math.max(...values);
  const bottom = Math.min(...values);
  const padding = (top - bottom || 1) * 0.1;
  const highest = top + padding;
  const lowest = bottom - padding;
  return {
    highest,
    lowest,
    y: (value: number) =>
      plot.y + plot.height
        - ((value - lowest) / (highest - lowest)) * plot.height,
  };
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
  { scale, plot, tick = (value: number) => formatCompact(Math.round(value)) }: {
    scale: ReturnType<typeof scaleFor>;
    plot: Shape["plot"];
    /** How to label a value. Defaults to money, because most of these are
     *  money -- but an index is not, and labelling 76.6 as "₹1" is worse
     *  than labelling it not at all. */
    tick?: (value: number) => string;
  },
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
              {tick(value)}
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
  market: styles.swatchMarket,
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

/**
 * A holding's recent shape, at the size of a table cell.
 *
 * Deliberately not a small LineChart. At 72 by 22 the axes, gridlines and
 * per-point circles that make a real chart readable are all noise, and the
 * only thing that survives being this small is the shape -- so that is all
 * this draws.
 *
 * It scales to its own range rather than to zero. A stock that moved
 * between 1,240 and 1,260 is a flat line against a zero baseline, which is
 * true of the price and useless as a picture of the month.
 *
 * Colour comes from first against last, not from the day's move, because a
 * line drawn over thirty days should be coloured by those thirty days.
 */
export function Sparkline(
  { values, label }: { values: number[]; label: string },
) {
  // Two points is the fewest that can be a line. One is a dot nobody can
  // read anything from, and none is nothing.
  if (values.length < 2) return null;

  const width = 72;
  const height = 22;
  const pad = 2;
  const lowest = Math.min(...values);
  const highest = Math.max(...values);
  // A flat series would divide by zero; drawing it down the middle is the
  // honest picture of a price that did not move.
  const span = highest - lowest || 1;

  const step = (width - pad * 2) / (values.length - 1);
  const y = (value: number) =>
    height - pad - ((value - lowest) / span) * (height - pad * 2);

  const path = values
    .map((value, index) =>
      `${index === 0 ? "M" : "L"} ${(pad + step * index).toFixed(1)} ${y(value).toFixed(1)}`)
    .join(" ");

  const first = values[0]!;
  const last = values[values.length - 1]!;
  const tone = last > first ? styles.sparkUp
    : last < first ? styles.sparkDown : styles.sparkFlat;

  return (
    <svg className={styles.spark} viewBox={`0 0 ${width} ${height}`}
         role="img" aria-label={label} preserveAspectRatio="none">
      <path className={`${styles.sparkLine} ${tone}`} d={path} />
    </svg>
  );
}


/**
 * Two series on one pair of axes, already rebased to a common start.
 *
 * Separate from LineChart because the shared scale is the whole point: the
 * two lines have to be measured against each other, so they cannot each
 * pick their own range the way two LineCharts side by side would. That is
 * also why this takes numbers that have already been rebased -- a basket
 * worth 180,000 and an ETF unit worth 267 share no axis until both are
 * expressed as what a hundred became.
 *
 * The 100 line is drawn explicitly. Without it "above the start" and
 * "below the start" have to be inferred from the gridline labels, which is
 * the one thing anybody reads this chart for.
 */
export function Comparison(
  { months, mine, market, mineLabel, marketLabel }: {
    months: string[]; mine: number[]; market: number[];
    mineLabel: string; marketLabel: string;
  },
) {
  const shape = useShape();
  const { plot } = shape;
  // One scale across both series, with the start line inside it so the
  // reference is never off the top or bottom of the plot.
  //
  // Not scaleFor, which anchors at zero. That is right for money -- a bar
  // of spending cut off above zero lies about its size -- and wrong here:
  // an index moving between 76 and 108 drawn from zero puts every point
  // in the top quarter of the plot and flattens the only thing the chart
  // is for. Nobody reads "how far is my portfolio from being worthless".
  const scale = scaleAround([...mine, ...market, 100], plot);
  const step = plot.width / Math.max(months.length, 1);
  const at = (index: number) => plot.x + step * index + step / 2;

  const path = (values: number[]) => values
    .map((value, index) =>
      `${index === 0 ? "M" : "L"} ${at(index)} ${scale.y(value)}`).join(" ");

  return (
    <svg className={styles.svg} viewBox={`0 0 ${shape.width} ${shape.height}`}
         role="img"
         aria-label={`${mineLabel} against ${marketLabel}, both from 100`}>
      {/* Plain numbers: these are index points, not rupees. Left on the
          money default they read "₹0 ₹0 ₹1 ₹1 ₹1", which is what
          formatCompact does to the number 76. */}
      <Gridlines scale={scale} plot={plot}
                 tick={(value) => value.toFixed(0)} />
      <line className={styles.zero} x1={plot.x} x2={plot.x + plot.width}
            y1={scale.y(100)} y2={scale.y(100)} />
      <path className={styles.lineMarket} d={path(market)} />
      <path className={styles.line} d={path(mine)} />
      {mine.map((value, index) => (
        <g key={months[index]}>
          <circle className={styles.point} cx={at(index)} cy={scale.y(value)} r="3" />
          <title>
            {shortMonth(months[index])}: {mineLabel} {value.toFixed(1)},{" "}
            {marketLabel} {market[index]?.toFixed(1)}
          </title>
        </g>
      ))}
      <MonthAxis months={months} shape={shape} />
    </svg>
  );
}
