const CHUNK_RELOAD_KEY = "ltc_chunk_reload_once";

export function installChunkRecovery(target: Window = window): () => void {
  const onPreloadError = (event: Event) => {
    event.preventDefault();
    if (target.sessionStorage.getItem(CHUNK_RELOAD_KEY) === target.location.href) return;
    target.sessionStorage.setItem(CHUNK_RELOAD_KEY, target.location.href);
    target.location.reload();
  };
  const onPageShow = () => target.sessionStorage.removeItem(CHUNK_RELOAD_KEY);
  target.addEventListener("vite:preloadError", onPreloadError);
  target.addEventListener("pageshow", onPageShow, { once: true });
  return () => {
    target.removeEventListener("vite:preloadError", onPreloadError);
    target.removeEventListener("pageshow", onPageShow);
  };
}

