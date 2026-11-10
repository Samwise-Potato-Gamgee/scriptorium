// Theme and accent handling; the last choice is cached locally to avoid a flash.
const root = document.documentElement;
const media = window.matchMedia("(prefers-color-scheme: dark)");
const current = { mode: "system", accent: "#e0a13a" };

function parseHex(hex) {
  const value = String(hex || "").replace("#", "").trim();
  if (!/^[0-9a-fA-F]{6}$/.test(value)) return { r: 224, g: 161, b: 58 };
  return {
    r: parseInt(value.slice(0, 2), 16),
    g: parseInt(value.slice(2, 4), 16),
    b: parseInt(value.slice(4, 6), 16),
  };
}

function toHex({ r, g, b }) {
  const part = (value) => Math.max(0, Math.min(255, Math.round(value))).toString(16).padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

function mix(hex, target, amount) {
  const source = parseHex(hex);
  const other = parseHex(target);
  return toHex({
    r: source.r + (other.r - source.r) * amount,
    g: source.g + (other.g - source.g) * amount,
    b: source.b + (other.b - source.b) * amount,
  });
}

function luminance(hex) {
  const { r, g, b } = parseHex(hex);
  const channel = (value) => {
    const part = value / 255;
    return part <= 0.03928 ? part / 12.92 : Math.pow((part + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrast(first, second) {
  const a = luminance(first);
  const b = luminance(second);
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
}

function readableText(accent, background, target) {
  let value = accent;
  for (let step = 0; step < 40 && contrast(value, background) < 4.5; step += 1) {
    value = mix(value, target, 0.08);
  }
  return value;
}

function applyAccent(accent, resolved) {
  const background = resolved === "dark" ? "#0d0d0f" : "#f3f3f4";
  const target = resolved === "dark" ? "#ffffff" : "#000000";
  const onAccent = contrast(accent, "#ffffff") >= contrast(accent, "#111111") ? "#ffffff" : "#151515";
  const { r, g, b } = parseHex(accent);
  root.style.setProperty("--accent", accent);
  root.style.setProperty("--accent-hover", mix(accent, resolved === "dark" ? "#ffffff" : "#000000", 0.12));
  root.style.setProperty("--accent-contrast", onAccent);
  root.style.setProperty("--accent-text", readableText(accent, background, target));
  root.style.setProperty("--accent-soft", `rgba(${r}, ${g}, ${b}, ${resolved === "dark" ? 0.2 : 0.16})`);
  root.style.setProperty("--accent-ring", `rgba(${r}, ${g}, ${b}, 0.38)`);
}

function paint() {
  const resolved = current.mode === "system" ? (media.matches ? "dark" : "light") : current.mode;
  root.dataset.theme = resolved;
  applyAccent(current.accent, resolved);
  try {
    localStorage.setItem("scriptorium-theme", resolved);
    localStorage.setItem("scriptorium-accent", current.accent);
  } catch (error) {}
  window.dispatchEvent(new Event("scriptorium-theme"));
}

media.addEventListener("change", () => {
  if (current.mode === "system") paint();
});

export function applyTheme(mode, accent) {
  current.mode = ["light", "dark", "system"].includes(mode) ? mode : "system";
  if (accent) current.accent = accent;
  paint();
}

export function resolvedTheme() {
  return root.dataset.theme === "dark" ? "dark" : "light";
}

export function toggleTheme() {
  const next = resolvedTheme() === "dark" ? "light" : "dark";
  applyTheme(next, current.accent);
  return next;
}

export function currentAccent() {
  return current.accent;
}
