import type { EpisodeRecord, PublicEpisode } from "./types";

export const MAX_ARTIFACT_BYTES = 1024 * 1024;
const MAX_RECORDS = 120;

const isObject = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const isText = (value: unknown, maximum = 4096): value is string =>
  typeof value === "string" && value.length <= maximum;
const isInteger = (value: unknown): value is number =>
  Number.isInteger(value) && Number(value) >= 0;
const exactKeys = (value: unknown, expected: string[]): value is Record<string, unknown> =>
  isObject(value) && Object.keys(value).length === expected.length
  && expected.every((key) => Object.prototype.hasOwnProperty.call(value, key));

export async function readBoundedResponseText(response: Response): Promise<string> {
  const declaredSize = Number(response.headers.get("content-length"));
  if (Number.isFinite(declaredSize) && declaredSize > MAX_ARTIFACT_BYTES) {
    throw new Error("Sample artifact exceeds the 1 MB size limit.");
  }
  if (!response.body || typeof response.body.getReader !== "function") {
    throw new Error("Sample artifact response does not support bounded streaming.");
  }
  const reader = response.body.getReader();
  const chunks: Uint8Array[] = [];
  let totalBytes = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      totalBytes += value.byteLength;
      if (totalBytes > MAX_ARTIFACT_BYTES) {
        await reader.cancel();
        throw new Error("Sample artifact exceeds the 1 MB size limit.");
      }
      chunks.push(value);
    }
  } finally {
    reader.releaseLock();
  }
  const bytes = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  try {
    return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    throw new Error("Sample artifact is not valid UTF-8 text.");
  }
}

export function parseEpisodeArtifact(jsonText: string): PublicEpisode {
  if (typeof jsonText !== "string") throw new Error("Sample artifact must be text.");
  if (new TextEncoder().encode(jsonText).byteLength > MAX_ARTIFACT_BYTES) {
    throw new Error("Sample artifact exceeds the 1 MB size limit.");
  }
  let artifact: unknown;
  try {
    artifact = JSON.parse(jsonText);
  } catch {
    throw new Error("Sample artifact is not valid JSON.");
  }
  validateEpisodeArtifact(artifact);
  return artifact as PublicEpisode;
}

export function validateEpisodeArtifact(artifact: unknown): artifact is PublicEpisode {
  if (!exactKeys(artifact, ["schema_version", "artifact_type", "labels", "provenance", "objective_result", "metrics", "records", "limitations"])
    || artifact.schema_version !== "1.0"
    || artifact.artifact_type !== "aegisai_public_research_episode") {
    throw new Error("Sample artifact has an unsupported type or schema version.");
  }
  if (!exactKeys(artifact.labels, ["display", "synthetic", "precomputed", "public_execution"])
    || artifact.labels.synthetic !== true || artifact.labels.precomputed !== true
    || artifact.labels.public_execution !== false || !isText(artifact.labels.display, 120)) {
    throw new Error("Sample artifact is missing its synthetic/read-only labels.");
  }
  const provenance = artifact.provenance;
  if (!exactKeys(provenance, ["episode_id", "scenario_id", "scenario_template", "seed", "research_split", "red_policy", "blue_policy", "generator", "generation_mode", "recorded_steps"])
    || !isText(provenance.episode_id, 160) || !isText(provenance.scenario_id, 160)
    || !isText(provenance.scenario_template, 120) || !isInteger(provenance.seed)
    || !isText(provenance.research_split, 240) || !isText(provenance.red_policy, 120)
    || !isText(provenance.blue_policy, 120) || !isText(provenance.generator, 160)
    || !isText(provenance.generation_mode, 240) || !isInteger(provenance.recorded_steps)
    || provenance.recorded_steps < 1 || provenance.recorded_steps > MAX_RECORDS) {
    throw new Error("Sample artifact is missing required provenance fields.");
  }
  if (!exactKeys(artifact.objective_result, ["achieved", "definition", "episode_count"])
    || typeof artifact.objective_result.achieved !== "boolean"
    || !isText(artifact.objective_result.definition, 500)
    || artifact.objective_result.episode_count !== 1) {
    throw new Error("Sample artifact has an invalid objective result.");
  }
  if (!Array.isArray(artifact.records) || artifact.records.length < 1 || artifact.records.length > MAX_RECORDS) {
    throw new Error("Sample artifact has an invalid or oversized action timeline.");
  }
  let previousSequence = 0;
  const observedRoleSteps = new Set<string>();
  for (const rawRecord of artifact.records) {
    if (!exactKeys(rawRecord, ["id", "sequence", "step", "role", "visibility_scope", "validation", "authorization", "action", "result", "evidence"])) {
      throw new Error("Sample artifact contains an invalid action timeline entry.");
    }
    const record = rawRecord as unknown as EpisodeRecord;
    if (!/^trace-[1-9][0-9]*$/.test(record.id)
      || !isInteger(record.sequence) || record.sequence <= previousSequence
      || record.id !== `trace-${record.sequence}` || !isInteger(record.step)
      || record.step >= provenance.recorded_steps
      || !["red", "blue"].includes(record.role) || record.visibility_scope !== record.role
      || observedRoleSteps.has(`${record.step}:${record.role}`)) {
      throw new Error("Sample artifact contains an invalid action timeline entry.");
    }
    previousSequence = record.sequence;
    observedRoleSteps.add(`${record.step}:${record.role}`);
    if (!exactKeys(record.validation, ["accepted", "reason"]) || typeof record.validation.accepted !== "boolean"
      || !isText(record.validation.reason, 240)
      || !exactKeys(record.authorization, ["authorized", "policy_reason"])
      || typeof record.authorization.authorized !== "boolean"
      || !isText(record.authorization.policy_reason, 240)) {
      throw new Error("Sample artifact is missing validation or Controller authorization data.");
    }
    if (!exactKeys(record.action, ["type", "target", "parameters", "reason_category", "expected_outcome"])
      || !isText(record.action.type, 120) || !isText(record.action.target, 160)
      || !isObject(record.action.parameters) || !isText(record.action.reason_category, 120)
      || !isText(record.action.expected_outcome, 500)
      || Object.keys(record.action.parameters).length > 8
      || Object.values(record.action.parameters).some((value) => !isText(value, 240))) {
      throw new Error("Sample artifact contains an invalid structured action.");
    }
    if (!exactKeys(record.result, ["outcome", "success", "message"])
      || !isText(record.result.outcome, 120) || typeof record.result.success !== "boolean"
      || !isText(record.result.message, 500)) {
      throw new Error("Sample artifact is missing its recorded action result.");
    }
    if (!Array.isArray(record.evidence) || record.evidence.length > 50
      || record.evidence.some((item) => !exactKeys(item, ["source", "reference", "value"])
        || item.source !== `${record.role}_observation`
        || !isText(item.reference, 240) || !isText(item.value, 2000))) {
      throw new Error("Sample artifact contains evidence outside its role-specific observation.");
    }
  }
  const metricIds = new Set<string>();
  if (!Array.isArray(artifact.metrics) || artifact.metrics.length > 20
    || artifact.metrics.some((metric) => !exactKeys(metric, ["id", "label", "value", "numerator", "denominator", "unit", "definition"])
      || !isText(metric.id, 64) || !/^[a-z][a-z0-9_]{0,63}$/.test(metric.id)
      || metricIds.has(metric.id) || !isText(metric.label, 160) || !isText(metric.definition, 1000)
      || !isText(metric.unit, 80) || typeof metric.value !== "number" || !Number.isFinite(metric.value) || metric.value < 0 || metric.value > 1
      || !isInteger(metric.numerator) || !isInteger(metric.denominator) || metric.denominator < 1
      || metric.numerator > metric.denominator
      || Math.abs(metric.value - metric.numerator / metric.denominator) > 1e-9
      || !metricIds.add(metric.id))) {
    throw new Error("Sample artifact contains an invalid metric or denominator.");
  }
  if (!Array.isArray(artifact.limitations) || artifact.limitations.length < 1
    || artifact.limitations.length > 20 || artifact.limitations.some((item) => !isText(item, 1000))) {
    throw new Error("Sample artifact is missing its limitations.");
  }
  return true;
}
