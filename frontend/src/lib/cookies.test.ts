import { describe, expect, it } from "vitest";
import { getCookie, setCookie } from "./cookies";

describe("cookies", () => {
  it("round-trips a value", () => {
    setCookie("lang", "en");
    expect(getCookie("lang")).toBe("en");
  });

  it("returns null for a missing cookie", () => {
    expect(getCookie("missing")).toBeNull();
  });
});

describe("malformed cookies", () => {
  it("returns null when decoding fails", () => {
    document.cookie = "bad=%E0%A4%A; Path=/";
    expect(getCookie("bad")).toBeNull();
  });
});
