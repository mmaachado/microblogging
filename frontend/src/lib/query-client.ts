import { MutationCache, QueryCache, QueryClient } from "@tanstack/react-query";
import { ME_KEY } from "@/features/auth/use-auth";
import { ApiError } from "@/lib/api";

export function createQueryClient(): QueryClient {
  const onError = (error: unknown) => {
    if (error instanceof ApiError && error.status === 401) {
      client.setQueryData(ME_KEY, null);
    }
  };
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({ onError }),
    mutationCache: new MutationCache({ onError }),
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return client;
}
