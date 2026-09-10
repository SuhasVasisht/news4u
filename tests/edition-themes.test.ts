import { expect, test } from "vitest";
import { editionThemes, validTheme } from "../src/lib/edition-themes";

function luminance(hex: string) {
  const channels = hex.slice(1).match(/../g)!.map(value => parseInt(value, 16) / 255).map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4);
  return channels[0] * .2126 + channels[1] * .7152 + channels[2] * .0722;
}
test("five valid themes preserve readable text and accent contrast", () => {
  expect(new Set(editionThemes.map(theme => theme.id)).size).toBe(5);
  for (const theme of editionThemes) {
    expect(validTheme(theme.id)).toBe(true);
    for (const foreground of [theme.ink, theme.accent, theme.secondary]) {
      const values = [luminance(foreground), luminance(theme.paper)].sort((a, b) => b - a);
      expect((values[0] + .05) / (values[1] + .05)).toBeGreaterThanOrEqual(4.5);
    }
  }
  expect(validTheme("invalid")).toBe(false);
  expect(validTheme(null)).toBe(false);
});
