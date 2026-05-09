import { readFileSync } from "node:fs";

import { afterEach, describe, expect, it } from "vitest";

describe("type badge styles", () => {
  afterEach(() => {
    document.head.innerHTML = "";
  });

  it("keeps Chinese fund labels on one horizontal line", () => {
    const style = document.createElement("style");
    style.textContent = readFileSync("src/styles.css", "utf8");
    document.head.appendChild(style);

    const typeBadgeRule = Array.from(style.sheet?.cssRules || []).find(
      (rule) =>
        "selectorText" in rule && (rule as CSSStyleRule).selectorText === ".type-badge"
    ) as CSSStyleRule | undefined;

    expect(typeBadgeRule?.style.whiteSpace).toBe("nowrap");
  });
});
