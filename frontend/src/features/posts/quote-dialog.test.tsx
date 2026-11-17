import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { ME, json, makePost } from "./fixtures";
import { QuoteDialog } from "./quote-dialog";

function mockApi() {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/v1/auth/me") return json(ME);
    if (path === "/api/v1/posts" && init?.method === "POST") {
      return json(makePost({ id: "n1" }), 201);
    }
    return json({ detail: "post_not_found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function postedForm(fetchMock: ReturnType<typeof mockApi>) {
  const call = fetchMock.mock.calls.find(([p]) => p === "/api/v1/posts");
  return call?.[1]?.body as FormData;
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

describe("QuoteDialog", () => {
  it("previews the quoted post and sends quote_of_id", async () => {
    const fetchMock = mockApi();
    const onOpenChange = vi.fn();
    renderWithProviders(
      <QuoteDialog
        post={makePost({ id: "orig", body: "quote me" })}
        open
        onOpenChange={onOpenChange}
      />,
    );
    expect(await screen.findByText("quote me")).toBeInTheDocument();
    await userEvent.type(screen.getByRole("textbox"), "my take");
    await userEvent.click(screen.getByRole("button", { name: "Publicar" }));

    await waitFor(() => expect(postedForm(fetchMock)).toBeDefined());
    const form = postedForm(fetchMock);
    expect(form.get("quote_of_id")).toBe("orig");
    expect(form.get("body")).toBe("my take");
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it("allows an empty body", async () => {
    const fetchMock = mockApi();
    renderWithProviders(
      <QuoteDialog post={makePost({ id: "orig" })} open onOpenChange={vi.fn()} />,
    );
    const submit = await screen.findByRole("button", { name: "Publicar" });
    expect(submit).toBeEnabled();
    await userEvent.click(submit);
    await waitFor(() => expect(postedForm(fetchMock)).toBeDefined());
    expect(postedForm(fetchMock).get("quote_of_id")).toBe("orig");
    expect(postedForm(fetchMock).get("body")).toBe("");
  });

  it("marks the preview when quoting a quote", async () => {
    mockApi();
    renderWithProviders(
      <QuoteDialog
        post={makePost({ id: "orig", quote_unavailable: true })}
        open
        onOpenChange={vi.fn()}
      />,
    );
    expect(await screen.findByText("Citando outro post")).toBeInTheDocument();
  });
});
