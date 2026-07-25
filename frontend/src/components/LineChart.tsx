import { useId, useMemo, useState } from "react";

export interface Series {
  key: string;
  label: string;
  color: string;
  points: (number | null)[];
}

interface Props {
  title: string;
  /** Подписи по оси X — номера эпох. */
  labels: number[];
  series: Series[];
  /** Сколько знаков после запятой в подписях значений. */
  precision?: number;
  /** Нижняя граница шкалы. У точности это 0, у потерь — авто. */
  min?: number;
  max?: number;
}

const WIDTH = 640;
const HEIGHT = 260;
const PAD = { top: 16, right: 56, bottom: 32, left: 46 };

const PLOT_W = WIDTH - PAD.left - PAD.right;
const PLOT_H = HEIGHT - PAD.top - PAD.bottom;

/** Пять делений сетки — больше превращает фон в решётку. */
const TICKS = 5;

export function LineChart({ title, labels, series, precision = 2, min, max }: Props) {
  const titleId = useId();
  const [hover, setHover] = useState<number | null>(null);

  const scale = useMemo(() => {
    const values = series.flatMap((s) => s.points.filter((v): v is number => v !== null));
    const lo = min ?? Math.min(...values);
    const hi = max ?? Math.max(...values);
    const pad = (hi - lo) * 0.1 || 0.1;
    return { lo: min ?? lo - pad, hi: max ?? hi + pad };
  }, [series, min, max]);

  const x = (index: number) =>
    PAD.left + (labels.length < 2 ? PLOT_W / 2 : (index / (labels.length - 1)) * PLOT_W);
  const y = (value: number) =>
    PAD.top + PLOT_H - ((value - scale.lo) / (scale.hi - scale.lo)) * PLOT_H;

  const ticks = Array.from({ length: TICKS }, (_, i) => scale.lo + ((scale.hi - scale.lo) * i) / (TICKS - 1));

  const path = (points: (number | null)[]) =>
    points
      .map((value, index) => (value === null ? "" : `${index === 0 ? "M" : "L"}${x(index)} ${y(value)}`))
      .join(" ");

  return (
    <figure className="chart">
      <figcaption className="chart__title" id={titleId}>
        {title}
      </figcaption>

      <div className="chart__legend">
        {series.map((s) => (
          <span className="chart__legend-item" key={s.key}>
            <span className="chart__legend-swatch" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>

      <svg
        className="chart__svg"
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-labelledby={titleId}
        onMouseLeave={() => setHover(null)}
      >
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              className="chart__grid"
              x1={PAD.left}
              x2={PAD.left + PLOT_W}
              y1={y(tick)}
              y2={y(tick)}
            />
            <text className="chart__tick" x={PAD.left - 8} y={y(tick)} textAnchor="end" dy="0.32em">
              {tick.toFixed(precision)}
            </text>
          </g>
        ))}

        {labels.map((label, index) =>
          index % Math.ceil(labels.length / 8) === 0 || index === labels.length - 1 ? (
            <text
              className="chart__tick"
              key={label}
              x={x(index)}
              y={HEIGHT - 10}
              textAnchor="middle"
            >
              {label}
            </text>
          ) : null,
        )}

        {series.map((s) => (
          <path key={s.key} className="chart__line" d={path(s.points)} stroke={s.color} />
        ))}

        {/* Подпись последнего значения — так серию видно без сверки с легендой. */}
        {series.map((s) => {
          const lastIndex = s.points.length - 1;
          const value = s.points[lastIndex];
          if (value === null || value === undefined) return null;
          return (
            <text
              key={s.key}
              className="chart__endlabel"
              x={x(lastIndex) + 8}
              y={y(value)}
              dy="0.32em"
              fill={s.color}
            >
              {value.toFixed(precision)}
            </text>
          );
        })}

        {hover !== null && (
          <>
            <line
              className="chart__crosshair"
              x1={x(hover)}
              x2={x(hover)}
              y1={PAD.top}
              y2={PAD.top + PLOT_H}
            />
            {series.map((s) => {
              const value = s.points[hover];
              if (value === null || value === undefined) return null;
              return (
                <circle
                  key={s.key}
                  className="chart__marker"
                  cx={x(hover)}
                  cy={y(value)}
                  r={5}
                  fill={s.color}
                />
              );
            })}
          </>
        )}

        {/* Прозрачные полосы — область наведения шире самой точки. */}
        {labels.map((label, index) => (
          <rect
            key={label}
            x={x(index) - PLOT_W / labels.length / 2}
            y={PAD.top}
            width={PLOT_W / labels.length}
            height={PLOT_H}
            fill="transparent"
            onMouseEnter={() => setHover(index)}
          />
        ))}
      </svg>

      {hover !== null && (
        <div className="chart__tooltip">
          <span className="chart__tooltip-title">эпоха {labels[hover]}</span>
          {series.map((s) => {
            const value = s.points[hover];
            return (
              <span className="chart__tooltip-row" key={s.key}>
                <span className="chart__legend-swatch" style={{ background: s.color }} />
                {s.label}
                <b>{value === null || value === undefined ? "—" : value.toFixed(precision)}</b>
              </span>
            );
          })}
        </div>
      )}
    </figure>
  );
}
