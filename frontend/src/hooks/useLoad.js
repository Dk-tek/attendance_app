import { useEffect, useRef, useState } from "react";

export function useLoad(loader, deps = [], refreshMs = 30000) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;
  useEffect(() => {
    let alive = true;
    let busy = false;
    async function load(initial = false) {
      if (busy) return;
      busy = true;
      if (initial) { setLoading(true); setData(null); }
      try {
        const value = await loaderRef.current();
        if (alive) { setData(value); setError(""); }
      } catch (err) { if (alive) setError(err.message); }
      finally { busy = false; if (alive) setLoading(false); }
    }
    load(true);
    const timer = setInterval(() => { if (!document.hidden) load(); }, refreshMs);
    return () => { alive = false; clearInterval(timer); };
  }, [...deps, refreshMs]);
  return { data, setData, error, loading };
}
