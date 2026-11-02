import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { getCookie } from "@/lib/cookies";
import { ThemeProvider, useTheme } from "./theme-provider";

function Probe() {
  const { theme, setTheme } = useTheme();
  return (
    <button onClick={() => setTheme("dark")}>
      {theme}
    </button>
  );
}

describe("ThemeProvider", () => {
  it("adds the dark class and writes the cookie", async () => {
    render(
      <ThemeProvider>
        <Probe />
      </ThemeProvider>,
    );
    expect(document.documentElement).not.toHaveClass("dark");
    await act(async () => {
      await userEvent.click(screen.getByRole("button"));
    });
    expect(document.documentElement).toHaveClass("dark");
    expect(getCookie("theme")).toBe("dark");
  });
});
