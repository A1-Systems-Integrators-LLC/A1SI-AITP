import type { AssetClass } from "../types";

export function formatPrice(price: number, assetClass: AssetClass): string {
  if (assetClass === "forex") return price.toFixed(5);
  if (price < 1) return price.toFixed(6);
  return `$${price.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export function formatVolume(volume: number): string {
  if (volume >= 1e9) return `${(volume / 1e9).toFixed(1)}B`;
  if (volume >= 1e6) return `${(volume / 1e6).toFixed(1)}M`;
  if (volume >= 1e3) return `${(volume / 1e3).toFixed(1)}K`;
  return volume.toFixed(0);
}
