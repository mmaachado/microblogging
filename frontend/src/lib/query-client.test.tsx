import { useMutation } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { ME_KEY, useLogout } from "@/features/auth/use-auth";
import { ApiError, apiFetch } from "./api";
import { createQueryClient } from "./query-client";

const wrapper = (client: ReturnType<typeof createQueryClient>) =>
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };

describe("query client", () => {
  it("clears the user on a 401 from any mutation", async () => {
    const client = createQueryClient();
    client.setQueryData(ME_KEY, { id: "1" });
    const { result } = renderHook(
      () =>
        useMutation({
          mutationFn: async () => {
            throw new ApiError(401, "not_authenticated");
          },
        }),
      { wrapper: wrapper(client) },
    );
    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    expect(client.getQueryData(ME_KEY)).toBeNull();
  });

  it("keeps the user on other errors", async () => {
    const client = createQueryClient();
    client.setQueryData(ME_KEY, { id: "1" });
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 500 })),
    );
    await client
      .fetchQuery({ queryKey: ["x"], queryFn: () => apiFetch("/x") })
      .catch(() => undefined);
    expect(client.getQueryData(ME_KEY)).toEqual({ id: "1" });
  });
});

describe("useLogout", () => {
  it("clears cached data even when the request fails", async () => {
    const client = createQueryClient();
    client.setQueryData(ME_KEY, { id: "1" });
    client.setQueryData(["other"], "secret");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("{}", { status: 500 })),
    );
    const { result } = renderHook(() => useLogout(), {
      wrapper: wrapper(client),
    });
    await act(async () => {
      await result.current.mutateAsync().catch(() => undefined);
    });
    await waitFor(() => expect(client.getQueryData(ME_KEY)).toBeNull());
    expect(client.getQueryData(["other"])).toBeUndefined();
  });
});
