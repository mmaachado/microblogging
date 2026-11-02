import { describe, expect, it } from "vitest";
import { getCookie } from "@/lib/cookies";
import { setLanguage } from ".";

describe("language", () => {
  it("sets the html lang on initial load", () => {
    expect(document.documentElement.lang).toBe("pt-BR");
  });

  it("updates html lang and cookie when switching", () => {
    setLanguage("en");
    expect(document.documentElement.lang).toBe("en");
    expect(getCookie("lang")).toBe("en");
    setLanguage("pt-BR");
  });
});
