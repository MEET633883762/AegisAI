export const LOCAL_API_ORIGIN = "http://127.0.0.1:8766";
export const API_TIMEOUT_MS = 5000;
export const API_RESPONSE_LIMIT = 2 * 1024 * 1024;

export type ApiRoute =
  | "/health"
  | "/api/telemetry/findings"
  | "/api/processing"
  | "/api/telemetry/sources/live-website/status"
  | "/api/telemetry/reports/latest"
  | `/api/telemetry/findings/${string}/evidence`;

export class LocalApiError extends Error {
  constructor(readonly status: number | null, message: string) {
    super(message);
    this.name = "LocalApiError";
  }
}

const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value) && typeof value === "object" && !Array.isArray(value);
const isText = (value: unknown): value is string => typeof value === "string" && value.length <= 4096;
const isTextList = (value: unknown): value is string[] => Array.isArray(value) && value.length <= 500 && value.every(isText);

function validatePayload(route: ApiRoute, value: unknown): boolean {
  if (!isRecord(value)) return false;
  if (route === "/health") return value.status === "ok" && value.mode === "local_synthetic";
  if (route === "/api/telemetry/findings") {
    return value.data_classification === "synthetic" && value.label === "SYNTHETIC - NOT REAL CLIENT DATA"
      && Array.isArray(value.findings) && value.findings.length <= 10_000 && value.findings.every((item) => {
        if (!isRecord(item)) return false;
        return isText(item.finding_id) && isText(item.rule_id) && isText(item.rule_version)
          && ["low", "medium", "high", "critical"].includes(String(item.severity))
          && typeof item.confidence === "number" && Number.isFinite(item.confidence) && item.confidence >= 0 && item.confidence <= 1
          && isText(item.first_seen_utc) && isText(item.last_seen_utc) && isText(item.asset_ref)
          && isTextList(item.evidence_refs) && isTextList(item.event_ids) && isText(item.explanation)
          && isTextList(item.confidence_factors) && ["open", "acknowledged", "closed"].includes(String(item.status));
      });
  }
  if (route === "/api/processing") {
    if (!["running", "unavailable", "stopped", "disabled"].includes(String(value.scheduler_state)) || value.interval_seconds !== 600) return false;
    const run = value.latest_run;
    if (run === null) return true;
    return isRecord(run) && isText(run.run_id) && isText(run.status) && isText(run.started_at_utc)
      && Number.isSafeInteger(run.input_event_count) && Number.isSafeInteger(run.accepted_event_count)
      && Number.isSafeInteger(run.duplicate_event_count) && Number.isSafeInteger(run.finding_count);
  }
  if (route === "/api/telemetry/sources/live-website/status") {
    return ["running", "healthy", "failed"].includes(String(value.status)) && isText(value.last_attempt_at_utc)
      && (value.last_success_at_utc === null || isText(value.last_success_at_utc))
      && [value.input_event_count, value.accepted_event_count, value.duplicate_event_count, value.rejected_record_count, value.position_bytes].every(Number.isSafeInteger);
  }
  if (route === "/api/telemetry/reports/latest") return isRecord(value.report);
  return Array.isArray(value.evidence) && value.evidence.length <= 500 && value.evidence.every((item) =>
    isRecord(item) && isText(item.evidence_ref) && isText(item.event_id) && isText(item.event_type)
      && isText(item.occurred_at_utc) && isText(item.asset_ref) && isText(item.actor_ref) && isText(item.source_ref));
}

async function readBounded(response: Response): Promise<string> {
  const length = Number(response.headers.get("content-length"));
  if (Number.isFinite(length) && length > API_RESPONSE_LIMIT) {
    await response.body?.cancel();
    throw new LocalApiError(null, "The local API response exceeded the dashboard limit.");
  }
  if (!response.body) return "";
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > API_RESPONSE_LIMIT) {
        await reader.cancel();
        throw new LocalApiError(null, "The local API response exceeded the dashboard limit.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const joined = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { joined.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder("utf-8", { fatal: true }).decode(joined);
}

export async function getLocalApi<T>(route: ApiRoute, token: string): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    let response: Response;
    try {
      response = await fetch(`${LOCAL_API_ORIGIN}${route}`, {
        method: "GET",
        headers: { Authorization: `Bearer ${token}` },
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
    } catch {
      throw new LocalApiError(null, controller.signal.aborted
        ? "The local API request timed out."
        : "The loopback API is unavailable. Start it on this computer and try again.");
    }
    if (!response.ok) {
      const message = response.status === 401
        ? "Authentication failed. Check the current local API startup token."
        : response.status === 403
          ? "This token does not have permission to read this view."
          : response.status === 404
            ? "No data is available for this view yet."
            : `The local API returned status ${response.status}.`;
      throw new LocalApiError(response.status, message);
    }
    try {
      const payload: unknown = JSON.parse(await readBounded(response));
      if (!validatePayload(route, payload)) throw new LocalApiError(null, "The local API response did not match its expected schema.");
      return payload as T;
    } catch (error) {
      if (error instanceof LocalApiError) throw error;
      if (controller.signal.aborted) throw new LocalApiError(null, "The local API request timed out.");
      throw new LocalApiError(null, "The local API returned an unreadable response.");
    }
  } finally {
    window.clearTimeout(timer);
  }
}
