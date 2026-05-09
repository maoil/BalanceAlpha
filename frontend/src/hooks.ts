import { useCallback, useEffect, useRef, useState, type DependencyList } from "react";

export type LoadState<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
};

export function useAsyncData<T>(
  loader: () => Promise<T>,
  deps: DependencyList = []
) {
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  const depsKey = JSON.stringify(deps);
  const [state, setState] = useState<LoadState<T>>({
    data: null,
    loading: true,
    error: null,
  });

  const reload = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await loaderRef.current();
      setState({ data, loading: false, error: null });
    } catch (error) {
      setState({
        data: null,
        loading: false,
        error: error instanceof Error ? error.message : "请求失败",
      });
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload, depsKey]);

  return { ...state, reload };
}

export function useMutationStatus() {
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>, successMessage: string) {
    setBusy(true);
    setMessage(null);
    setError(null);
    try {
      await action();
      setMessage(successMessage);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "操作失败");
    } finally {
      setBusy(false);
    }
  }

  return { busy, message, error, run, clear: () => setMessage(null) };
}
