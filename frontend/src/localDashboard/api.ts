export const LOCAL_API_ORIGIN = "http://127.0.0.1:8766";
export const API_TIMEOUT_MS = 5000;
export const API_RESPONSE_LIMIT = 2 * 1024 * 1024;

export type ApiRoute =
  | "/health"
  | "/api/telemetry/findings"
  | "/api/processing"
  | "/api/telemetry/sources/live-website/status"
  | "/api/telemetry/reports/latest"
  | "/api/assessment/reports/latest"
  | "/api/purple-team/scenarios/runs"
  | "/api/evaluation/reports/latest"
  | "/api/reports/executive/latest"
  | "/api/investigations/cases"
  | `/api/investigations/cases/${string}`
  | `/api/investigations/cases/${string}/${"findings" | "evidence" | "notes" | "status" | "context"}`
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
const isCount = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
const isCounts = (value: unknown): boolean => isRecord(value) && isCount(value.true_positives)
  && isCount(value.true_negatives) && isCount(value.false_positives) && isCount(value.false_negatives);
const isMetric = (value: unknown): boolean => isRecord(value) && isCount(value.denominator)
  && (value.status === "defined" ? typeof value.value === "number" && Number.isFinite(value.value)
    : value.status === "undefined_zero_denominator" && value.value === null && value.denominator === 0);
const isMetrics = (value: unknown): boolean => isRecord(value)
  && [value.precision, value.recall, value.f1, value.specificity, value.false_positive_rate, value.false_negative_rate].every(isMetric);
const isDateText = (value: unknown): value is string => isText(value) && Number.isFinite(Date.parse(value));
const isExecutiveCounts = (value: unknown, keys: readonly string[]): boolean => isRecord(value)
  && keys.every((key) => isCount(value[key]));

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
    if (value.status === "unavailable") {
      return value.last_attempt_at_utc === null && value.last_success_at_utc === null
        && [value.input_event_count, value.accepted_event_count, value.duplicate_event_count,
          value.rejected_record_count, value.position_bytes].every((item) => item === null)
        && value.position_sha256 === null && value.error_code === null;
    }
    return ["running", "healthy", "failed"].includes(String(value.status)) && isText(value.last_attempt_at_utc)
      && (value.last_success_at_utc === null || isText(value.last_success_at_utc))
      && [value.input_event_count, value.accepted_event_count, value.duplicate_event_count, value.rejected_record_count, value.position_bytes].every(Number.isSafeInteger);
  }
  if (route === "/api/telemetry/reports/latest") return isRecord(value.report);
  if (route === "/api/assessment/reports/latest") {
    const report = value.report;
    if (value.data_classification !== "synthetic" || value.label !== "LOCAL SYNTHETIC WEBSITE ASSESSMENT"
      || !isText(value.tenant_id)) return false;
    if (!Array.isArray(value.history) || value.history.length > 20 || !value.history.every((item) => isRecord(item)
      && typeof item.report_id === "string" && /^assessment-report-[a-f0-9]{16}$/.test(item.report_id)
      && isDateText(item.generated_at_utc) && isCount(item.inferred_risk_count)
      && isCount(item.confirmed_finding_count) && (item.comparison_status === null || ["baseline", "compared"].includes(String(item.comparison_status)))
      && (item.previous_report_id === null || (typeof item.previous_report_id === "string" && /^assessment-report-[a-f0-9]{16}$/.test(item.previous_report_id)))
      && isCount(item.newly_introduced_count) && isCount(item.resolved_count))) return false;
    if (report === null) return true;
    if (!isRecord(report) || !["1.0", "2.0"].includes(String(report.schema_version))
      || !isText(report.report_id) || !isText(report.generated_at_utc)
      || report.data_classification !== "synthetic" || report.label !== "LOCAL SYNTHETIC WEBSITE ASSESSMENT"
      || !Array.isArray(report.raw_observations) || report.raw_observations.length > 3
      || !Array.isArray(report.inferred_risks) || report.inferred_risks.length > 12
      || !Array.isArray(report.confirmed_findings) || report.confirmed_findings.length > 12
      || !Number.isSafeInteger(report.duplicate_observation_count) || !isTextList(report.limitations)) return false;
    const checkIds = ["health_status_v1", "security_headers_v1", "cookie_attributes_v1"];
    const validDecision = (item: unknown) => isRecord(item) && checkIds.includes(String(item.check_id))
      && item.target_origin === "http://127.0.0.1:8767" && typeof item.allowed === "boolean" && isText(item.reason_code);
    const validIssue = (item: unknown) => isRecord(item) && isText(item.issue_id)
      && checkIds.includes(String(item.check_id)) && ["inferred_risk", "confirmed_finding"].includes(String(item.classification))
      && isText(item.title) && isText(item.rationale) && isTextList(item.evidence_refs)
      && (report.schema_version === "1.0" || (["informational", "low", "medium"].includes(String(item.severity)) && isText(item.recommendation)));
    const validChanges = (items: unknown) => Array.isArray(items) && items.length <= 12 && items.every((item) => isRecord(item)
      && isText(item.finding_key) && isText(item.issue_id) && checkIds.includes(String(item.check_id))
      && isText(item.title) && isTextList(item.evidence_refs));
    const validObservation = (item: unknown) => isRecord(item) && checkIds.includes(String(item.check_id))
      && validDecision(item.decision) && isText(item.outcome) && Number.isSafeInteger(item.duration_ms)
      && (item.error_category === null || ["policy_denied", "deadline_exceeded", "request_failed", "response_limit_exceeded"].includes(String(item.error_category)))
      && (report.schema_version === "1.0" || (["availability", "response_security", "cookie_configuration"].includes(String(item.category))
        && isText(item.description) && ["informational", "low", "medium"].includes(String(item.severity))
        && isText(item.check_version) && isText(item.configuration_version) && isText(item.expected_result)
        && isText(item.observed_result) && ["PASS", "FAIL", "ERROR", "NOT_APPLICABLE"].includes(String(item.outcome_status))
        && isText(item.observed_at_utc)))
      && isRecord(item.facts) && Object.keys(item.facts).length <= 12
      && (item.evidence === null || (isRecord(item.evidence) && isText(item.evidence.evidence_ref)
        && isText(item.evidence.source) && isText(item.evidence.observed_at_utc)
        && item.evidence.request_method === "GET" && ["/", "/health"].includes(String(item.evidence.request_path))
        && Number.isSafeInteger(item.evidence.response_status) && Number.isSafeInteger(item.evidence.response_bytes)
        && isText(item.evidence.response_sha256)));
    if (!report.raw_observations.every(validObservation) || !report.inferred_risks.every(validIssue)
      || !report.confirmed_findings.every(validIssue)) return false;
    if (report.schema_version === "1.0") return true;
    return isText(report.run_id) && isText(report.started_at_utc) && isText(report.configuration_version)
      && isText(report.check_catalog_version) && report.provenance === "fixed_loopback_synthetic_website"
      && isRecord(report.comparison) && ["baseline", "compared"].includes(String(report.comparison.status))
      && (report.comparison.previous_report_id === null || isText(report.comparison.previous_report_id))
      && validChanges(report.comparison.newly_introduced) && validChanges(report.comparison.resolved)
      && validChanges(report.comparison.unchanged);
  }
  if (route === "/api/purple-team/scenarios/runs") {
    const validStatus = (status: unknown) => ["NOT_RUN", "PASSED", "FAILED", "ERROR", "NOT_APPLICABLE"].includes(String(status));
    const validList = (items: unknown, max = 20) => isTextList(items) && items.length <= max;
    return value.data_classification === "synthetic"
      && value.label === "SYNTHETIC LOCAL SCENARIO HISTORY - NOT A REAL-WORLD CONTROL TEST"
      && isText(value.tenant_id) && Array.isArray(value.runs) && value.runs.length <= 20
      && value.runs.every((run) => isRecord(run) && run.schema_version === "1.0"
        && run.catalog_version === "aegisai-purple-scenarios-v1"
        && isText(run.run_id) && /^[a-f0-9]{32}$/.test(run.run_id)
        && ["local-health-baseline", "synthetic-auth-rejection"].includes(String(run.scenario_id))
        && run.scenario_version === "1.0" && validStatus(run.status)
        && run.data_classification === "synthetic"
        && run.label === "SYNTHETIC LOCAL SCENARIO - NOT A REAL-WORLD CONTROL TEST"
        && run.target_origin === "http://127.0.0.1:8767" && run.execution_scope === "fixed_loopback_synthetic_website"
        && isDateText(run.started_at_utc) && isDateText(run.completed_at_utc)
        && isRecord(run.policy_decision) && run.policy_decision.scenario_id === run.scenario_id
        && run.policy_decision.target_origin === "http://127.0.0.1:8767" && typeof run.policy_decision.allowed === "boolean"
        && ["approved", "explicit_authorization_required", "scenario_not_allowlisted", "target_not_allowlisted"].includes(String(run.policy_decision.reason_code))
        && isCount(run.policy_decision.maximum_requests) && run.policy_decision.maximum_requests <= 3
        && isText(run.expected_telemetry_type) && isText(run.expected_route_code)
        && isCount(run.expected_status) && isCount(run.expected_count) && run.expected_count <= 3
        && Array.isArray(run.observed_http_statuses) && run.observed_http_statuses.length <= 3
        && run.observed_http_statuses.every((status) => isCount(status) && status >= 100 && status <= 599)
        && Array.isArray(run.observed_telemetry) && run.observed_telemetry.length <= 3
        && run.observed_telemetry.every((item) => isRecord(item) && isText(item.event_id) && isText(item.evidence_ref)
          && isText(item.event_type) && isText(item.route_code) && isCount(item.status_code) && isDateText(item.occurred_at_utc))
        && validList(run.expected_detection_rule_ids, 4) && Array.isArray(run.observed_findings) && run.observed_findings.length <= 20
        && run.observed_findings.every((item) => isRecord(item) && isText(item.finding_id)
          && isText(item.rule_id) && validList(item.evidence_refs, 3))
        && validList(run.assessment_check_ids, 4)
        && (run.error_category === null || ["policy_denied", "concurrency_limit", "deadline_exceeded", "request_timeout", "connection_failed", "request_failed", "incomplete_response", "response_limit_exceeded", "malformed_response", "unsupported_response_encoding", "redirect_not_followed", "unexpected_http_status", "ambiguous_source_activity", "telemetry_processing_error"].includes(String(run.error_category)))
        && (run.telemetry_report_id === null || (typeof run.telemetry_report_id === "string" && /^treport-[a-f0-9]{12}$/.test(run.telemetry_report_id)))
        && (run.telemetry_run_id === null || (typeof run.telemetry_run_id === "string" && /^trun-[a-f0-9]{16}$/.test(run.telemetry_run_id)))
        && isRecord(run.comparison) && (run.comparison.previous_run_id === null || isText(run.comparison.previous_run_id))
        && (run.comparison.previous_status === null || validStatus(run.comparison.previous_status))
        && (run.comparison.outcome_changed === null || typeof run.comparison.outcome_changed === "boolean")
        && validList(run.limitations, 6));
  }
  if (route === "/api/evaluation/reports/latest") {
    const report = value.report;
    if (value.data_classification !== "synthetic"
      || value.label !== "SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE"
      || !isText(value.tenant_id) || !isRecord(report)
      || !["1.0", "1.1"].includes(String(report.schema_version)) || report.report_type !== "aegisai_synthetic_detection_evaluation_report"
      || !isText(report.dataset_id) || !isText(report.dataset_version) || !isText(report.counting_unit)
      || !isText(report.rule_catalog_version) || !isText(report.detector_rule_version)
      || !isText(report.scenario_rule_mapping_version) || !isText(report.attack_mapping_catalog_version)
      || typeof report.dataset_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(report.dataset_sha256)
      || typeof report.detector_config_sha256 !== "string" || !/^[a-f0-9]{64}$/.test(report.detector_config_sha256)
      || !isCounts(report.counts) || !isMetrics(report.metrics) || !isCount(report.total_evaluated_pairs)
      || !isCount(report.valid_scenario_count) || !isCount(report.rejected_scenario_count)
      || !isTextList(report.limitations) || !Array.isArray(report.per_rule) || report.per_rule.length > 32) return false;
    const counts = report.counts as Record<string, number>;
    const countsTotal = counts.true_positives + counts.true_negatives
      + counts.false_positives + counts.false_negatives;
    const validComparison = (comparison: unknown) => comparison === null || (isRecord(comparison)
      && isText(comparison.previous_run_id) && isTextList(comparison.newly_failing_scenario_ids)
      && isTextList(comparison.resolved_scenario_ids));
    const validRun = (run: unknown) => isRecord(run) && isText(run.run_id) && isDateText(run.generated_at_utc)
      && typeof run.report_sha256 === "string" && /^[a-f0-9]{64}$/.test(run.report_sha256)
      && typeof run.dataset_sha256 === "string" && /^[a-f0-9]{64}$/.test(run.dataset_sha256)
      && typeof run.detector_config_sha256 === "string" && /^[a-f0-9]{64}$/.test(run.detector_config_sha256)
      && isCounts(run.counts) && isMetrics(run.metrics) && isCount(run.total_evaluated_pairs)
      && validComparison(run.comparison);
    if (countsTotal !== report.total_evaluated_pairs || !Array.isArray(report.history) || report.history.length > 20
      || !report.history.every(validRun) || !isTextList(report.warnings)
      || !["complete", "partial", "legacy_unavailable"].includes(String(report.coverage_status))
      || !Array.isArray(report.rule_event_mapping) || report.rule_event_mapping.length > 32
      || !Array.isArray(report.scenario_rule_mapping) || report.scenario_rule_mapping.length > 50
      || !Array.isArray(report.technique_coverage) || report.technique_coverage.length > 32
      || !Array.isArray(report.untested_techniques) || report.untested_techniques.length > 32
      || !report.per_rule.every((rule) => isRecord(rule) && isText(rule.rule_id) && isCounts(rule.counts) && isMetrics(rule.metrics))) return false;
    const validStrings = (items: unknown) => isTextList(items) && items.length <= 32;
    return report.rule_event_mapping.every((item) => isRecord(item) && isText(item.rule_id) && validStrings(item.event_types))
      && report.scenario_rule_mapping.every((item) => isRecord(item) && isText(item.scenario_id)
        && validStrings(item.expected_rule_ids) && validStrings(item.evaluated_rule_ids)
        && validStrings(item.observed_rule_ids) && validStrings(item.technique_ids)
        && ["pass", "fail", "rejected"].includes(String(item.status)))
      && report.technique_coverage.every((item) => isRecord(item) && isText(item.technique_id) && isText(item.name)
        && validStrings(item.scenario_ids) && validStrings(item.rule_ids) && item.status === "covered" && isText(item.scope_note))
      && report.untested_techniques.every((item) => isRecord(item) && isText(item.technique_id) && isText(item.name)
        && ["not_tested", "candidate_not_mapped"].includes(String(item.status)) && isText(item.rationale));
  }
  if (route === "/api/reports/executive/latest") {
    const report = value.report;
    if (value.data_classification !== "synthetic" || value.label !== "SYNTHETIC - NOT REAL CLIENT DATA"
      || !isText(value.tenant_id) || !isRecord(report) || report.schema_version !== "1.0"
      || report.report_type !== "aegisai_executive_incident_report" || !isText(report.report_id)
      || !/^executive-report-[a-f0-9]{16}$/.test(String(report.report_id))
      || report.tenant_id !== value.tenant_id || report.data_classification !== "synthetic"
      || report.label !== "SYNTHETIC - NOT REAL CLIENT DATA" || !isDateText(report.generated_at_utc)
      || !isText(report.executive_summary) || !isRecord(report.finding_counts)
      || !isRecord(report.finding_counts.by_severity) || !isRecord(report.finding_counts.by_status)
      || !isExecutiveCounts(report.finding_counts.by_severity, ["low", "medium", "high", "critical"])
      || !isExecutiveCounts(report.finding_counts.by_status, ["open", "acknowledged", "closed"])
      || !Array.isArray(report.observations) || report.observations.length > 10_000
      || !Array.isArray(report.inferred_risks) || report.inferred_risks.length > 10_000
      || !Array.isArray(report.confirmed_findings) || report.confirmed_findings.length !== 0
      || !Array.isArray(report.timeline) || report.timeline.length > 10_000
      || !Array.isArray(report.recommendations) || report.recommendations.length > 20_000
      || !isTextList(report.limitations)) return false;
    const observations = report.observations.every((item) => isRecord(item) && isText(item.evidence_ref)
      && isText(item.event_id) && isText(item.event_type) && isDateText(item.occurred_at_utc)
      && isTextList(item.related_finding_ids));
    const risks = report.inferred_risks.every((item) => isRecord(item) && item.classification === "inferred_risk"
      && isText(item.finding_id) && isText(item.rule_id) && ["low", "medium", "high", "critical"].includes(String(item.severity))
      && typeof item.confidence === "number" && Number.isFinite(item.confidence) && item.confidence >= 0 && item.confidence <= 1
      && ["open", "acknowledged", "closed"].includes(String(item.status))
      && isDateText(item.first_seen_utc) && isDateText(item.last_seen_utc) && isText(item.asset_ref)
      && isText(item.explanation) && isTextList(item.confidence_factors) && isTextList(item.evidence_refs));
    const timeline = report.timeline.every((item) => isRecord(item) && isDateText(item.occurred_at_utc)
      && isText(item.evidence_ref) && isText(item.event_id) && isText(item.event_type)
      && isTextList(item.finding_ids));
    const recommendations = report.recommendations.every((item) => isRecord(item)
      && ["investigation", "remediation"].includes(String(item.category))
      && isText(item.finding_id) && isText(item.text));
    const severityTotal = Number(report.finding_counts.by_severity.low) + Number(report.finding_counts.by_severity.medium)
      + Number(report.finding_counts.by_severity.high) + Number(report.finding_counts.by_severity.critical);
    const statusTotal = Number(report.finding_counts.by_status.open) + Number(report.finding_counts.by_status.acknowledged)
      + Number(report.finding_counts.by_status.closed);
    return observations && risks && timeline && recommendations
      && report.inferred_risks.length === severityTotal && report.inferred_risks.length === statusTotal;
  }
  if (route === "/api/investigations/cases") {
    return value.data_classification === "synthetic" && isText(value.tenant_id)
      && Array.isArray(value.cases) && value.cases.length <= 200 && value.cases.every((item) =>
        isRecord(item) && /^case-[a-f0-9]{16}$/.test(String(item.case_id)) && isText(item.title)
        && ["open", "under_review", "closed"].includes(String(item.status))
        && isDateText(item.created_at_utc) && isDateText(item.updated_at_utc)
        && isCount(item.finding_count) && isCount(item.evidence_count));
  }
  if (route.startsWith("/api/investigations/cases/case-")) {
    if (value.data_classification !== "synthetic" || !isText(value.tenant_id) || !isRecord(value.case)) return false;
    const item = value.case;
    const findings = Array.isArray(item.findings) ? item.findings : null;
    const evidence = Array.isArray(item.evidence) ? item.evidence : null;
    const notes = Array.isArray(item.notes) ? item.notes : null;
    const context = Array.isArray(item.context) ? item.context : null;
    const timelineItems = Array.isArray(item.timeline) ? item.timeline : null;
    const recommendations = Array.isArray(item.recommendations) ? item.recommendations : null;
    return /^case-[a-f0-9]{16}$/.test(String(item.case_id)) && isText(item.title)
      && ["open", "under_review", "closed"].includes(String(item.status))
      && isDateText(item.created_at_utc) && isDateText(item.updated_at_utc)
      && isCount(item.finding_count) && isCount(item.evidence_count)
      && findings !== null && findings.length <= 100 && evidence !== null && evidence.length <= 500
      && notes !== null && notes.length <= 500 && context !== null && context.length <= 40
      && timelineItems !== null && timelineItems.length <= 2000 && recommendations !== null && recommendations.length <= 200
      && findings.every((link: unknown) => isRecord(link) && isText(link.finding_id)
        && ["inferred_relationship", "analyst_conclusion"].includes(String(link.relationship)) && isText(link.rationale) && isDateText(link.linked_at_utc))
      && evidence.every((link: unknown) => isRecord(link) && isText(link.finding_id) && isText(link.evidence_ref)
        && isText(link.rationale) && isDateText(link.linked_at_utc))
      && notes.every((note: unknown) => isRecord(note) && ["analyst_conclusion", "unresolved_hypothesis"].includes(String(note.classification))
        && isText(note.text) && isDateText(note.created_at_utc))
      && context.every((context: unknown) => isRecord(context) && ["assessment_report", "evaluation_run"].includes(String(context.source_type))
        && isText(context.source_id) && isText(context.label) && isDateText(context.generated_at_utc))
      && timelineItems.every((event: unknown) => isRecord(event) && isDateText(event.occurred_at_utc)
        && isText(event.category) && isText(event.reference_id) && isText(event.description) && isText(event.classification))
      && recommendations.every((recommendation: unknown) => isRecord(recommendation)
        && ["investigation", "remediation"].includes(String(recommendation.category)) && isText(recommendation.text)
        && isTextList(recommendation.supporting_finding_ids));
  }
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

export async function postLocalApi<T>(route: ApiRoute, token: string, data: Record<string, unknown>): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    let response: Response;
    try {
      response = await fetch(`${LOCAL_API_ORIGIN}${route}`, {
        method: "POST", headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
        body: JSON.stringify(data), cache: "no-store", credentials: "omit", signal: controller.signal,
      });
    } catch {
      throw new LocalApiError(null, controller.signal.aborted ? "The local API request timed out." : "The loopback API is unavailable.");
    }
    if (!response.ok) {
      throw new LocalApiError(response.status, response.status === 403
        ? "This token lacks investigation write permission. Restart the local API with --enable-investigation-writes."
        : `The local API returned status ${response.status}.`);
    }
    const payload: unknown = JSON.parse(await readBounded(response));
    if (!isRecord(payload)) throw new LocalApiError(null, "The local API response did not match its expected schema.");
    return payload as T;
  } catch (error) {
    if (error instanceof LocalApiError) throw error;
    throw new LocalApiError(null, "The local API response could not be read safely.");
  } finally { window.clearTimeout(timer); }
}
