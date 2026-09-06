/**
 * Server-side fetch helper for the FastAPI backend.
 *
 * The API routes under app/api are thin proxies: they verify the session and
 * forward to the backend. When `fetch` itself rejects, no request ever reached
 * the backend - in practice that is the backend not listening yet (both
 * processes come up together under one dev command, and the frontend is ready
 * first) or a dropped socket. The Jobs page turns any non-ok response into a
 * visible "failed to load your matches", so an unretried blip during startup
 * shows the user an error for a backend that is seconds from being healthy.
 *
 * Only connection-level rejections are retried, and only for idempotent reads.
 * A rejection means the request was never delivered, so replaying it cannot
 * double-apply anything. Responses are returned untouched however they look -
 * a backend that answered 500 has an opinion, and repeating the call would
 * just multiply the work behind a real error. Timeouts are likewise left
 * alone: /jobs/recommended legitimately runs several seconds on a cold cache.
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

// A refused connection fails in ~30ms, so these add no meaningful latency to
// the failing case while covering a backend still binding its port.
const CONNECT_RETRIES = 2;
const RETRY_DELAY_MS = 250;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path}`;
}

/**
 * Fetches `path` on the backend, retrying only when the connection itself
 * fails. Throws the last error if every attempt fails to connect.
 */
export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  let lastError: unknown;

  for (let attempt = 0; attempt <= CONNECT_RETRIES; attempt++) {
    try {
      return await fetch(backendUrl(path), init);
    } catch (err) {
      // An aborted request is the caller's decision, not a transient fault.
      if (err instanceof DOMException && err.name === "AbortError") throw err;
      lastError = err;
      if (attempt < CONNECT_RETRIES) await sleep(RETRY_DELAY_MS * (attempt + 1));
    }
  }

  throw lastError;
}

/** Headers that authenticate this server to the backend's internal guard. */
export function internalHeaders(): Record<string, string> {
  return { "X-Internal-Secret": process.env.INTERNAL_API_SECRET || "" };
}

/**
 * The message shown when the backend could not be reached at all. Distinct
 * from a backend error so the user can tell "still starting up" from "broken".
 */
export const BACKEND_UNREACHABLE =
  "Could not reach the jobs service. It may still be starting up - try again in a moment.";
