import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithProviders } from "@/test/render";
import { Composer } from "./composer";
import { ME, json, makePost } from "./fixtures";

const PLACEHOLDER = "O que está acontecendo?";

function mockApi() {
  const fetchMock = vi.fn(async (path: string, init?: RequestInit) => {
    if (path === "/api/v1/auth/me") return json(ME);
    if (path === "/api/v1/posts" && init?.method === "POST") {
      return json(makePost(), 201);
    }
    return json({ detail: "post_not_found" }, 404);
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

function file(name: string, type: string) {
  return new File(["x"], name, { type });
}

function attach(files: File[], user: Pick<ReturnType<typeof userEvent.setup>, "upload"> = userEvent) {
  const input = document.querySelector<HTMLInputElement>("input[type=file]");
  if (!input) throw new Error("no file input");
  return user.upload(input, files);
}

function sized(name: string, type: string, size: number) {
  const f = file(name, type);
  Object.defineProperty(f, "size", { value: size });
  return f;
}

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:preview");
  URL.revokeObjectURL = vi.fn();
});

describe("Composer", () => {
  it("counts code points", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await userEvent.type(screen.getByPlaceholderText(PLACEHOLDER), "a😀b");
    expect(screen.getByText("3/120")).toBeInTheDocument();
  });

  it("enables submit only with valid text", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    const submit = screen.getByRole("button", { name: "Publicar" });
    const box = screen.getByPlaceholderText(PLACEHOLDER);
    expect(submit).toBeDisabled();
    await userEvent.type(box, "hi");
    expect(submit).toBeEnabled();
    await userEvent.clear(box);
    await userEvent.click(box);
    await userEvent.paste("a".repeat(121));
    expect(submit).toBeDisabled();
  });

  it("counts and validates the trimmed text", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    const box = screen.getByPlaceholderText(PLACEHOLDER);
    await userEvent.click(box);
    await userEvent.paste("😀".repeat(120) + " ".repeat(5));
    expect(screen.getByText("120/120")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Publicar" })).toBeEnabled();
  });

  it("rejects five images", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await attach(
      Array.from({ length: 5 }, (_, i) => file(`${i}.png`, "image/png")),
    );
    expect(
      await screen.findByText("Use até 4 imagens ou 1 vídeo."),
    ).toBeInTheDocument();
  });

  it("rejects an image over 5 MB", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await attach([sized("a.png", "image/png", 5 * 1024 * 1024 + 1)]);
    expect(
      await screen.findByText(
        "O arquivo é grande demais (imagens até 5 MB, vídeos até 50 MB).",
      ),
    ).toBeInTheDocument();
  });

  it("rejects a video over 50 MB", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await attach([sized("a.mp4", "video/mp4", 50 * 1024 * 1024 + 1)]);
    expect(
      await screen.findByText(
        "O arquivo é grande demais (imagens até 5 MB, vídeos até 50 MB).",
      ),
    ).toBeInTheDocument();
  });

  it("rejects a text file", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await attach(
      [file("a.txt", "text/plain")],
      userEvent.setup({ applyAccept: false }),
    );
    expect(
      await screen.findByText(
        "Escolha imagens JPEG, PNG, WebP ou GIF, ou um vídeo MP4, WebM ou MOV válido.",
      ),
    ).toBeInTheDocument();
  });

  it("rejects mixing an image and a video", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await attach([file("a.png", "image/png"), file("b.mp4", "video/mp4")]);
    expect(
      await screen.findByText(
        "Não é possível misturar imagens e vídeo no mesmo post.",
      ),
    ).toBeInTheDocument();
  });

  it("revokes the preview when the attachment is removed", async () => {
    mockApi();
    renderWithProviders(<Composer />);
    await attach([file("a.png", "image/png")]);
    await userEvent.click(
      await screen.findByRole("button", { name: "Remover anexo" }),
    );
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });

  it("submits FormData and clears the form", async () => {
    const fetchMock = mockApi();
    renderWithProviders(<Composer />);
    const box = screen.getByPlaceholderText(PLACEHOLDER);
    await userEvent.type(box, "hello");
    await attach([file("a.png", "image/png")]);
    await userEvent.click(screen.getByRole("button", { name: "Publicar" }));

    await waitFor(() => expect(box).toHaveValue(""));
    const call = fetchMock.mock.calls.find(([p]) => p === "/api/v1/posts");
    const body = call?.[1]?.body as FormData;
    expect(body).toBeInstanceOf(FormData);
    expect(body.get("body")).toBe("hello");
    expect(body.getAll("files")).toHaveLength(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:preview");
  });
});
