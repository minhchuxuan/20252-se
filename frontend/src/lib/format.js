// Formatting helpers + the Okabe–Ito series palette (colourblind-safe).

export const OKABE_ITO = {
  black: "#1a1a1a",
  orange: "#e69f00",
  sky: "#56b4e9",
  green: "#009e73",
  yellow: "#f0e442",
  blue: "#0072b2",
  vermillion: "#d55e00",
  purple: "#cc79a7",
};

// Stable colour order for chart series.
export const SERIES_COLORS = [
  OKABE_ITO.blue,
  OKABE_ITO.green,
  OKABE_ITO.orange,
  OKABE_ITO.vermillion,
  OKABE_ITO.sky,
  OKABE_ITO.purple,
];

const TYPE_COLOR = {
  plug: OKABE_ITO.blue,
  bulb: OKABE_ITO.orange,
  fan: OKABE_ITO.sky,
  ac: OKABE_ITO.vermillion,
  sensor: OKABE_ITO.purple,
};
export const deviceColor = (type) => TYPE_COLOR[type] || OKABE_ITO.black;

const TYPE_ICON = { plug: "🔌", bulb: "💡", fan: "🌀", ac: "❄️", sensor: "📟" };
export const deviceIcon = (type) => TYPE_ICON[type] || "⚡";

export const vnd = (n) =>
  new Intl.NumberFormat("vi-VN", { maximumFractionDigits: 0 }).format(Math.round(n || 0)) + " ₫";

export const vndShort = (n) => {
  n = n || 0;
  if (Math.abs(n) >= 1_000_000) return (n / 1_000_000).toFixed(1).replace(/\.0$/, "") + "M ₫";
  if (Math.abs(n) >= 1_000) return Math.round(n / 1000) + "k ₫";
  return Math.round(n) + " ₫";
};

export const kwh = (n, d = 1) => (n || 0).toFixed(d) + " kWh";
export const watts = (n) => Math.round(n || 0) + " W";

export const fmtDateTime = (iso) =>
  new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
export const fmtTime = (iso) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
