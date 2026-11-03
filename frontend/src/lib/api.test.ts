import { describe, expect, it, vi } from "vitest";
import { apiFetch } from "./api";

function stubFetch() {
  const fetchMock = vi
    .fn()
    .mockResolvedValue(new Response("{}", { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("apiFetch", () => {
  it("sends a FormData body without a JSON content type", async () => {
    const fetchMock = stubFetch();
    const body = new FormData();
    body.append("file", new Blob(["x"]), "a.png");

    await apiFetch("/api/v1/me/avatar", { method: "PUT", body });

    const init = fetchMock.mock.calls[0][1];
    expect(init.body).toBe(body);
    expect(init.headers).not.toHaveProperty("Content-Type");
  });

  it("sends other bodies as JSON", async () => {
    const fetchMock = stubFetch();

    await apiFetch("/x", { method: "POST", body: { a: 1 } });

    const init = fetchMock.mock.calls[0][1];
    expect(init.body).toBe('{"a":1}');
    expect(init.headers["Content-Type"]).toBe("application/json");
  });
});
