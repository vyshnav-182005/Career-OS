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
 * Responses are returned untouched however they look - a backend that answered
 * 500 has an opinion, and repeating the call would just multiply the work
 * behind a real error. Timeouts are likewise left alone: /jobs/recommended
 * legitimately runs several seconds on a cold cache.
 *
 * Two things here are easy to get wrong, so they are spelled out:
 *
 * 1. The budget has to match how long the backend actually takes to listen.
 *    This used to retry twice over ~750ms, on the assumption that a port bind
 *    is nearly instant. It isn't: the backend imports torch, sentence-
 *    transformers, supabase and apscheduler before uvicorn binds, measured at
 *    ~10.3s from process start on this machine. A 750ms window covered under a
 *    tenth of the gap, so `npm run dev` reliably put ECONNREFUSED on the
 *    dashboard's first load - the exact case the retry existed to prevent.
 *
 * 2. Only errors that prove nothing was delivered may be retried. Two of the
 *    four callers are a PUT and a POST. Retrying those on any failure is unsafe
 *    - undici also reports a socket dropped *mid-response* as a failed fetch,
 *    and replaying that could apply the write twice. So the retry is gated on
 *    the connection never having been established (see isPreDeliveryError):
 *    connection refused, or DNS not resolving. Anything else propagates on the
 *    first attempt, whatever the method.
 */

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000";

/**
 * How long to keep trying to establish a connection.
 *
 * Deliberately short. The backend's cold start is ~10.3s, but waiting that out
 * here would hold the request open and leave the user staring at a spinner
 * with no explanation. The Jobs board retries the 503 this produces on its own
 * backoff (STARTUP_RETRY_DELAYS_MS in JobsBoard.tsx) and says "starting the
 * jobs service" while it does, so the page stays responsive and the cards
 * arrive as soon as the backend answers. This budget only has to cover a blip
 * short enough that a round trip through the client would be wasted effort.
 */
const CONNECT_RETRY_BUDGET_MS = 2_000;
/** Backoff between connect attempts, doubling up to the cap. */
const INITIAL_RETRY_DELAY_MS = 250;
const MAX_RETRY_DELAY_MS = 2_000;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function backendUrl(path: string): string {
  return `${BACKEND_URL}${path}`;
}

/** Walks the `cause` chain, which is where undici puts the real syscall error. */
function errorCodes(err: unknown): string[] {
  const codes: string[] = [];
  let current: unknown = err;
  for (let depth = 0; current && depth < 5; depth++) {
    const code = (current as { code?: unknown }).code;
    if (typeof code === "string") codes.push(code);
    current = (current as { cause?: unknown }).cause;
  }
  return codes;
}

/**
 * True only when the failure happened before anything could be delivered, so
 * replaying the request cannot repeat a side effect.
 *
 * ECONNREFUSED: nothing listening on the port (the backend still starting).
 * ENOTFOUND / EAI_AGAIN: the host did not resolve, so no socket was opened.
 *
 * Deliberately excludes ECONNRESET, EPIPE and UND_ERR_SOCKET: those can all
 * occur after the request bytes were sent, and this helper is used for a PUT
 * and a POST as well as the two GETs.
 */
function isPreDeliveryError(err: unknown): boolean {
  const codes = errorCodes(err);
  return codes.some((code) => code === "ECONNREFUSED" || code === "ENOTFOUND" || code === "EAI_AGAIN");
}

function isAbort(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

/**
 * Fetches `path` on the backend, retrying only while the connection itself is
 * being refused. Throws the last error once the budget is spent.
 */
export async function backendFetch(path: string, init?: RequestInit): Promise<Response> {
  const deadline = Date.now() + CONNECT_RETRY_BUDGET_MS;
  let delay = INITIAL_RETRY_DELAY_MS;

  for (;;) {
    try {
      return await fetch(backendUrl(path), init);
    } catch (err) {
      // An aborted request is the caller's decision, not a transient fault.
      if (isAbort(err)) throw err;
      // Anything that might already have reached the backend propagates now,
      // so a write is never replayed on a guess.
      if (!isPreDeliveryError(err)) throw err;

      const remaining = deadline - Date.now();
      if (remaining <= 0) throw err;

      await sleep(Math.min(delay, remaining));
      delay = Math.min(delay * 2, MAX_RETRY_DELAY_MS);

      if (init?.signal?.aborted) throw err;
    }
  }
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
