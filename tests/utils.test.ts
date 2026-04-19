import { describe, expect, it } from "vitest";
import { formatArticleBodyParagraphs } from "@/lib/utils";

describe("formatArticleBodyParagraphs", () => {
  it("preserves explicit paragraph breaks", () => {
    expect(
      formatArticleBodyParagraphs("First paragraph line one.\nStill first paragraph.\n\nSecond paragraph."),
    ).toEqual(["First paragraph line one.\nStill first paragraph.".replace(/\n/g, " "), "Second paragraph."]);
  });

  it("converts flat multi-sentence text into readable paragraphs", () => {
    const paragraphs = formatArticleBodyParagraphs(
      "Sentence one explains the setup. Sentence two adds supporting detail. Sentence three introduces the turn. Sentence four closes the point with a concrete outcome. Sentence five starts the next thread. Sentence six finishes it cleanly.",
    );

    expect(paragraphs.length).toBeGreaterThan(1);
    expect(paragraphs.join(" ")).toContain("Sentence one explains the setup.");
    expect(paragraphs.join(" ")).toContain("Sentence six finishes it cleanly.");
  });

  it("leaves short text as one paragraph", () => {
    expect(formatArticleBodyParagraphs("Short body. Another short sentence.")).toEqual([
      "Short body. Another short sentence.",
    ]);
  });

  it("normalizes extra whitespace safely", () => {
    expect(formatArticleBodyParagraphs("  First line with spaces. \n\n  Second line too.  ")).toEqual([
      "First line with spaces.",
      "Second line too.",
    ]);
  });
});
