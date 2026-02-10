import { useQuery } from "@tanstack/react-query";

export function useApi<T>(key: string[], fetcher: () => Promise<T>) {
  return useQuery({ queryKey: key, queryFn: fetcher });
}
