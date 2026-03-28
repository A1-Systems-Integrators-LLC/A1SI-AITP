import { useEffect, useRef } from "react";
import {
  createChart,
  CandlestickSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type CandlestickData,
  type UTCTimestamp,
} from "lightweight-charts";
import type { AssetClass, OHLCVData } from "../types";
import { useTheme } from "../hooks/useTheme";

function getChartColors(theme: string) {
  const isDark = theme !== "light";
  return {
    bg: isDark ? "#1e293b" : "#ffffff",
    text: isDark ? "#94a3b8" : "#475569",
    grid: isDark ? "#334155" : "#e2e8f0",
    up: "#22c55e",
    down: "#ef4444",
  };
}

const INDICATOR_COLORS: Record<string, string> = {
  sma_21: "#f59e0b",
  sma_50: "#3b82f6",
  sma_200: "#ef4444",
  ema_21: "#f59e0b",
  ema_50: "#3b82f6",
  bb_upper: "#6366f1",
  bb_mid: "#8b5cf6",
  bb_lower: "#6366f1",
  rsi_14: "#f59e0b",
  macd: "#3b82f6",
  macd_signal: "#ef4444",
  macd_hist: "#22c55e",
  volume_ratio: "#8b5cf6",
};

interface PriceChartProps {
  data: OHLCVData[];
  height?: number;
  indicatorData?: Record<string, number | null>[];
  overlayIndicators?: string[];
  paneIndicators?: string[];
  assetClass?: AssetClass;
}

export function PriceChart({
  data,
  height = 400,
  indicatorData,
  overlayIndicators = [],
  paneIndicators = [],
  assetClass = "crypto",
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const paneContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const paneChartRef = useRef<IChartApi | null>(null);
  const { theme } = useTheme();

  useEffect(() => {
    if (!containerRef.current) return;

    const priceDecimals = assetClass === "forex" ? 5 : 2;
    const colors = getChartColors(theme);

    const chart = createChart(containerRef.current, {
      height,
      layout: {
        background: { color: colors.bg },
        textColor: colors.text,
      },
      grid: {
        vertLines: { color: colors.grid },
        horzLines: { color: colors.grid },
      },
      localization: {
        priceFormatter: (price: number) => price.toFixed(priceDecimals),
      },
    });

    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: colors.up,
      downColor: colors.down,
      borderDownColor: colors.down,
      borderUpColor: colors.up,
      wickDownColor: colors.down,
      wickUpColor: colors.up,
    });

    const chartData: CandlestickData[] = data.map((d) => ({
      time: (d.timestamp / 1000) as UTCTimestamp,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    }));

    candlestickSeries.setData(chartData);

    // Add overlay indicators
    if (indicatorData && overlayIndicators.length > 0) {
      for (const ind of overlayIndicators) {
        const series = chart.addSeries(LineSeries, {
          color: INDICATOR_COLORS[ind] || "#94a3b8",
          lineWidth: 1,
          priceLineVisible: false,
        });
        const lineData = indicatorData
          .filter((d) => d[ind] != null && d.timestamp != null)
          .map((d) => ({
            time: (d.timestamp! / 1000) as UTCTimestamp,
            value: d[ind] as number,
          }));
        if (lineData.length > 0) {
          series.setData(lineData);
        }
      }
    }

    chart.timeScale().fitContent();
    chartRef.current = chart;

    // Pane chart for RSI, MACD, etc.
    let paneChart: IChartApi | null = null;
    if (paneContainerRef.current && indicatorData && paneIndicators.length > 0) {
      paneChart = createChart(paneContainerRef.current, {
        height: 150,
        layout: {
          background: { color: colors.bg },
          textColor: colors.text,
        },
        grid: {
          vertLines: { color: colors.grid },
          horzLines: { color: colors.grid },
        },
      });

      for (const ind of paneIndicators) {
        if (ind === "macd_hist") {
          const series = paneChart.addSeries(HistogramSeries, {
            color: "#22c55e",
          });
          const histData = indicatorData
            .filter((d) => d[ind] != null && d.timestamp != null)
            .map((d) => ({
              time: (d.timestamp! / 1000) as UTCTimestamp,
              value: d[ind] as number,
              color: (d[ind] as number) >= 0 ? "#22c55e" : "#ef4444",
            }));
          if (histData.length > 0) series.setData(histData);
        } else {
          const series = paneChart.addSeries(LineSeries, {
            color: INDICATOR_COLORS[ind] || "#94a3b8",
            lineWidth: 1,
            priceLineVisible: false,
          });
          const lineData = indicatorData
            .filter((d) => d[ind] != null && d.timestamp != null)
            .map((d) => ({
              time: (d.timestamp! / 1000) as UTCTimestamp,
              value: d[ind] as number,
            }));
          if (lineData.length > 0) series.setData(lineData);
        }
      }

      paneChart.timeScale().fitContent();
      paneChartRef.current = paneChart;
    }

    return () => {
      chart.remove();
      chartRef.current = null;
      if (paneChart) {
        paneChart.remove();
        paneChartRef.current = null;
      }
    };
  }, [data, height, indicatorData, overlayIndicators, paneIndicators, assetClass, theme]);

  return (
    <div>
      <div ref={containerRef} className="w-full rounded-lg" />
      {paneIndicators.length > 0 && (
        <div ref={paneContainerRef} className="mt-1 w-full rounded-lg" />
      )}
    </div>
  );
}
