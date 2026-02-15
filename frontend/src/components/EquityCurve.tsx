import { useEffect, useRef } from "react";
import {
  createChart,
  LineSeries,
  AreaSeries,
  type IChartApi,
  type UTCTimestamp,
} from "lightweight-charts";

interface Trade {
  profit_abs?: number;
  close_date?: string;
  [key: string]: unknown;
}

interface EquityCurveProps {
  trades: Trade[];
  initialBalance?: number;
  height?: number;
}

export function EquityCurve({ trades, initialBalance = 10000, height = 300 }: EquityCurveProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current || trades.length === 0) return;

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: "#1e293b" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#334155" },
        horzLines: { color: "#334155" },
      },
      rightPriceScale: { borderColor: "#334155" },
      timeScale: { borderColor: "#334155" },
    });

    // Sort trades by close date
    const sorted = [...trades]
      .filter((t) => t.close_date && t.profit_abs != null)
      .sort((a, b) => new Date(a.close_date!).getTime() - new Date(b.close_date!).getTime());

    if (sorted.length === 0) {
      chart.remove();
      return;
    }

    // Build equity curve from cumulative P&L
    let equity = initialBalance;
    let peak = initialBalance;
    const equityData: { time: UTCTimestamp; value: number }[] = [];
    const drawdownData: { time: UTCTimestamp; value: number }[] = [];

    for (const trade of sorted) {
      equity += trade.profit_abs ?? 0;
      peak = Math.max(peak, equity);
      const dd = ((equity - peak) / peak) * 100;
      const time = (new Date(trade.close_date!).getTime() / 1000) as UTCTimestamp;
      equityData.push({ time, value: equity });
      drawdownData.push({ time, value: dd });
    }

    // Equity line
    const equitySeries = chart.addSeries(LineSeries, {
      color: "#22c55e",
      lineWidth: 2,
      priceLineVisible: false,
    });
    equitySeries.setData(equityData);

    // Drawdown area
    if (drawdownData.some((d) => d.value < 0)) {
      const ddSeries = chart.addSeries(AreaSeries, {
        topColor: "rgba(239, 68, 68, 0.0)",
        bottomColor: "rgba(239, 68, 68, 0.3)",
        lineColor: "#ef4444",
        lineWidth: 1,
        priceLineVisible: false,
        priceScaleId: "drawdown",
      });
      ddSeries.setData(drawdownData);
      chart.priceScale("drawdown").applyOptions({
        scaleMargins: { top: 0.7, bottom: 0 },
      });
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        chart.applyOptions({ width: entry.contentRect.width });
      }
    });
    observer.observe(containerRef.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [trades, initialBalance, height]);

  if (trades.length === 0) return null;

  return (
    <div>
      <h4 className="mb-2 text-sm font-medium text-[var(--color-text-muted)]">Equity Curve</h4>
      <div ref={containerRef} className="w-full rounded-lg" />
    </div>
  );
}
