import type { WritingChart } from "@/mock-data/writing";
import { chartScale } from "./chart";

const COLORS = ["#213d68", "#eba45e", "#4f7bc4", "#a8571a", "#7fa3e0"];

const color = (i: number) => COLORS[i % COLORS.length];

/** Biểu đồ cột nhóm của đề Task 1, vẽ từ bảng số liệu. Bản lớn (trong hộp Phóng to) có ghi số trên cột. */
export function BarChart({ chart, large = false }: { chart: WritingChart; large?: boolean }) {
  const width = large ? 580 : 390;
  const height = large ? 300 : 235;
  const left = large ? 56 : 44;
  const bottom = large ? 30 : 25;
  const top = large ? 20 : 12;
  const plotWidth = width - left - 10;
  const plotHeight = height - top - bottom;
  const { max, ticks } = chartScale(chart.series.flatMap((s) => s.values));
  const groupWidth = plotWidth / chart.categories.length;
  const barWidth = Math.min(large ? 30 : 18, (groupWidth * 0.8) / chart.series.length);
  const y = (v: number) => top + plotHeight - (v / max) * plotHeight;
  const font = large ? 13 : 11;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" role="img" aria-label={`Biểu đồ cột: ${chart.unit}, ${chart.categories.join(", ")}`}>
      {ticks.map((t) => (
        <g key={t}>
          <line x1={left} x2={width - 10} y1={y(t)} y2={y(t)} stroke="rgb(33 61 104 / 0.13)" />
          <text x={left - 6} y={y(t) + 4} textAnchor="end" fontSize={font} fill="#52627f">
            {t}
          </text>
        </g>
      ))}
      {chart.categories.map((category, ci) => {
        const groupStart = left + ci * groupWidth + (groupWidth - barWidth * chart.series.length - 3 * (chart.series.length - 1)) / 2;
        return (
          <g key={category}>
            {chart.series.map((series, si) => {
              const value = series.values[ci];
              const x = groupStart + si * (barWidth + 3);
              return (
                <g key={series.name}>
                  <rect x={x} y={y(value)} width={barWidth} height={y(0) - y(value)} rx={large ? 4 : 3} fill={color(si)}>
                    <title>{`${series.name}, ${category}: ${value}`}</title>
                  </rect>
                  {large && (
                    <text x={x + barWidth / 2} y={y(value) - 6} textAnchor="middle" fontSize={12} fill="#17233c">
                      {value}
                    </text>
                  )}
                </g>
              );
            })}
            <text x={left + ci * groupWidth + groupWidth / 2} y={height - (large ? 8 : 7)} textAnchor="middle" fontSize={large ? 14 : 12} fill="#52627f">
              {category}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export function ChartLegend({ chart, large = false }: { chart: WritingChart; large?: boolean }) {
  return (
    <ul className={`flex flex-wrap gap-x-3.5 gap-y-1 ${large ? "text-[13px]" : "text-xs"}`}>
      {chart.series.map((series, i) => (
        <li key={series.name} className="flex items-center gap-1.5">
          <i aria-hidden="true" className={`block rounded-[3px] ${large ? "size-3" : "size-2.5"}`} style={{ background: color(i) }} />
          {series.name}
        </li>
      ))}
    </ul>
  );
}

/** Bảng số liệu của biểu đồ: cũng là cách đọc biểu đồ cho trình đọc màn hình. */
export function ChartTable({ chart }: { chart: WritingChart }) {
  return (
    <table className="w-full border-collapse text-sm">
      <caption className="px-3 pb-1 text-left font-bold">Bảng số liệu</caption>
      <thead>
        <tr className="text-right text-xs text-muted">
          <th scope="col" className="px-3 py-2 text-left font-semibold">
            Năm
          </th>
          {chart.series.map((s) => (
            <th key={s.name} scope="col" className="px-3 py-2 font-semibold">
              {s.name}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {chart.categories.map((category, ci) => (
          <tr key={category} className="border-t border-navy/8">
            <th scope="row" className="px-3 py-2 text-left font-semibold">
              {category}
            </th>
            {chart.series.map((s) => (
              <td key={s.name} className="px-3 py-2 text-right">
                {s.values[ci]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
