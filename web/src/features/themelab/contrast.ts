/**
 * WCAG contrast ratios, computed from whatever the browser actually resolved.
 *
 * The point of measuring rather than eyeballing: a token pair that fails AA in
 * one theme is invisible to inspection but obvious as a number, and it is much
 * cheaper to catch here than from a user who cannot read their own balance.
 */

/** Parse any colour the browser reports - rgb(), rgba() or a hex string. */
function parseColour(value: string): [number, number, number] | null {
  const rgb = value.match(/rgba?\(([^)]+)\)/);
  if (rgb) {
    const parts = rgb[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    if (parts.length >= 3) return [parts[0], parts[1], parts[2]];
    return null;
  }

  const hex = value.trim().replace("#", "");
  if (hex.length === 3) {
    return [
      parseInt(hex[0] + hex[0], 16),
      parseInt(hex[1] + hex[1], 16),
      parseInt(hex[2] + hex[2], 16),
    ];
  }
  if (hex.length === 6) {
    return [
      parseInt(hex.slice(0, 2), 16),
      parseInt(hex.slice(2, 4), 16),
      parseInt(hex.slice(4, 6), 16),
    ];
  }
  return null;
}

/** Relative luminance, per the WCAG 2.1 definition. */
function luminance([r, g, b]: [number, number, number]): number {
  const channel = (raw: number) => {
    const c = raw / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** Contrast ratio between two colour strings, from 1 to 21. */
export function contrastRatio(foreground: string, background: string): number | null {
  const fg = parseColour(foreground);
  const bg = parseColour(background);
  if (!fg || !bg) return null;

  const lighter = Math.max(luminance(fg), luminance(bg));
  const darker = Math.min(luminance(fg), luminance(bg));
  return (lighter + 0.05) / (darker + 0.05);
}

/** Resolve a CSS custom property as the browser sees it inside `element`. */
export function resolveToken(element: Element, token: string): string {
  return getComputedStyle(element).getPropertyValue(token).trim();
}

/** AA needs 4.5:1 for body text, 3:1 for large text and UI boundaries. */
export function gradeContrast(ratio: number | null, large = false): "pass" | "fail" | "unknown" {
  if (ratio === null) return "unknown";
  return ratio >= (large ? 3 : 4.5) ? "pass" : "fail";
}
