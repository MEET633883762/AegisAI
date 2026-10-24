export type Severity = "low" | "medium" | "high" | "critical";
export type FindingStatus = "open" | "acknowledged" | "closed";
export type TelemetryFinding = {
  finding_id: string;
  rule_id: string;
  rule_version: string;
  severity: Severity;
  confidence: number;
  first_seen_utc: string;
  last_seen_utc: string;
  asset_ref: string;
  evidence_refs: string[];
  event_ids: string[];
  explanation: string;
  confidence_factors: string[];
  status: FindingStatus;
};
export type FindingsResponse = { data_classification: "synthetic"; label: string; findings: TelemetryFinding[] };
export type ProcessingRun = {
  run_id: string;
  source_id: string;
  status: "started" | "completed" | "skipped" | "failed";
  started_at_utc: string;
  completed_at_utc: string | null;
  attempt: number;
  input_event_count: number;
  accepted_event_count: number;
  duplicate_event_count: number;
  finding_count: number;
  error_code: string | null;
};
export type ProcessingResponse = { scheduler_state: string; interval_seconds: number; latest_run: ProcessingRun | null };
export type SourceResponse = {
  status: "running" | "healthy" | "failed" | "unavailable";
  last_attempt_at_utc: string | null;
  last_success_at_utc: string | null;
  input_event_count: number | null;
  accepted_event_count: number | null;
  duplicate_event_count: number | null;
  rejected_record_count: number | null;
  position_bytes: number | null;
  error_code: string | null;
};
export type EvidenceItem = {
  evidence_ref: string;
  event_id: string;
  event_type: string;
  occurred_at_utc: string;
  asset_ref: string;
  actor_ref: string;
  source_ref: string;
};
export type EvidenceResponse = { evidence: EvidenceItem[] };
export type InvestigationCaseSummary = {
  case_id: string; title: string; status: "open" | "under_review" | "closed";
  created_at_utc: string; updated_at_utc: string; finding_count: number; evidence_count: number;
};
export type InvestigationCase = InvestigationCaseSummary & {
  findings: { finding_id: string; relationship: "inferred_relationship" | "analyst_conclusion"; rationale: string; linked_at_utc: string }[];
  evidence: { finding_id: string; evidence_ref: string; rationale: string; linked_at_utc: string }[];
  notes: { classification: "analyst_conclusion" | "unresolved_hypothesis"; text: string; created_at_utc: string }[];
  context: { source_type: "assessment_report" | "evaluation_run"; source_id: string; generated_at_utc: string; label: string }[];
  timeline: { occurred_at_utc: string; category: string; reference_id: string; description: string; classification: string }[];
  recommendations: { category: "investigation" | "remediation"; text: string; supporting_finding_ids: string[] }[];
};
export type InvestigationCasesResponse = { data_classification: "synthetic"; tenant_id: string; cases: InvestigationCaseSummary[] };
export type InvestigationCaseResponse = { data_classification: "synthetic"; tenant_id: string; case: InvestigationCase };
export type HealthResponse = { status: "ok"; mode: "local_synthetic" };
export type AssessmentCheckId = "health_status_v1" | "security_headers_v1" | "cookie_attributes_v1";
export type AssessmentDecision = { check_id: AssessmentCheckId; target_origin: string; allowed: boolean; reason_code: string };
export type AssessmentEvidence = {
  evidence_ref: string; source: string; observed_at_utc: string; request_method: string;
  request_path: "/" | "/health"; response_status: number; response_bytes: number; response_sha256: string;
};
export type AssessmentOutcome = "PASS" | "FAIL" | "ERROR" | "NOT_APPLICABLE";
export type AssessmentObservation = {
  check_id: AssessmentCheckId; decision: AssessmentDecision; outcome: string; duration_ms: number;
  category: "availability" | "response_security" | "cookie_configuration" | "legacy";
  description: string; severity: "informational" | "low" | "medium";
  check_version: string; configuration_version: string; expected_result: string; observed_result: string;
  outcome_status: AssessmentOutcome | null; observed_at_utc: string | null;
  error_category: "policy_denied" | "deadline_exceeded" | "request_failed" | "response_limit_exceeded" | null;
  facts: Record<string, string | number | boolean | null>; evidence: AssessmentEvidence | null;
};
export type AssessmentIssue = {
  issue_id: string; check_id: AssessmentCheckId; classification: "inferred_risk" | "confirmed_finding";
  title: string; rationale: string; severity: "informational" | "low" | "medium";
  recommendation: string; evidence_refs: string[];
};
export type AssessmentFindingChange = {
  finding_key: string; issue_id: string; check_id: AssessmentCheckId; title: string; evidence_refs: string[];
};
export type AssessmentRunComparison = {
  status: "baseline" | "compared"; previous_report_id: string | null;
  newly_introduced: AssessmentFindingChange[]; resolved: AssessmentFindingChange[]; unchanged: AssessmentFindingChange[];
};
export type AssessmentReport = {
  schema_version: "1.0" | "2.0"; report_id: string; generated_at_utc: string;
  run_id: string | null; started_at_utc: string | null; configuration_version: string;
  check_catalog_version: string; provenance: "fixed_loopback_synthetic_website" | "legacy";
  comparison: AssessmentRunComparison | null;
  data_classification: "synthetic"; label: "LOCAL SYNTHETIC WEBSITE ASSESSMENT";
  raw_observations: AssessmentObservation[]; inferred_risks: AssessmentIssue[];
  confirmed_findings: AssessmentIssue[]; duplicate_observation_count: number; limitations: string[];
};
export type AssessmentResponse = {
  data_classification: "synthetic"; label: "LOCAL SYNTHETIC WEBSITE ASSESSMENT";
  tenant_id: string; report: AssessmentReport | null; history: AssessmentHistoryEntry[];
};
export type AssessmentHistoryEntry = {
  report_id: string; generated_at_utc: string; inferred_risk_count: number; confirmed_finding_count: number;
  comparison_status: "baseline" | "compared" | null; previous_report_id: string | null;
  newly_introduced_count: number; resolved_count: number;
};
export type PurpleScenarioRun = {
  schema_version: "1.0"; catalog_version: "aegisai-purple-scenarios-v1";
  run_id: string; scenario_id: string; scenario_version: string;
  status: "NOT_RUN" | "PASSED" | "FAILED" | "ERROR" | "NOT_APPLICABLE";
  data_classification: "synthetic"; label: "SYNTHETIC LOCAL SCENARIO - NOT A REAL-WORLD CONTROL TEST";
  target_origin: "http://127.0.0.1:8767"; execution_scope: "fixed_loopback_synthetic_website";
  started_at_utc: string; completed_at_utc: string; expected_telemetry_type: string; expected_route_code: string;
  policy_decision: { scenario_id: string; target_origin: string; allowed: boolean; reason_code: string; maximum_requests: number };
  expected_status: number; expected_count: number; observed_http_statuses: number[];
  observed_telemetry: { event_id: string; evidence_ref: string; event_type: string; route_code: string; status_code: number; occurred_at_utc: string }[];
  expected_detection_rule_ids: string[]; observed_findings: { finding_id: string; rule_id: string; evidence_refs: string[] }[];
  assessment_check_ids: string[]; error_category: string | null;
  telemetry_report_id: string | null; telemetry_run_id: string | null;
  comparison: { previous_run_id: string | null; previous_status: PurpleScenarioRun["status"] | null; outcome_changed: boolean | null };
  limitations: string[];
};
export type PurpleScenarioRunsResponse = {
  data_classification: "synthetic"; label: "SYNTHETIC LOCAL SCENARIO HISTORY - NOT A REAL-WORLD CONTROL TEST";
  tenant_id: string; runs: PurpleScenarioRun[];
};
export type ConfusionCounts = { true_positives: number; true_negatives: number; false_positives: number; false_negatives: number };
export type EvaluationMetric = { value: number | null; denominator: number; status: "defined" | "undefined_zero_denominator" };
export type EvaluationMetrics = { precision: EvaluationMetric; recall: EvaluationMetric; f1: EvaluationMetric; specificity: EvaluationMetric; false_positive_rate: EvaluationMetric; false_negative_rate: EvaluationMetric };
export type EvaluationComparison = { previous_run_id: string; newly_failing_scenario_ids: string[]; resolved_scenario_ids: string[] } | null;
export type EvaluationRunSummary = {
  run_id: string; generated_at_utc: string; report_sha256: string; dataset_sha256: string;
  detector_config_sha256: string; counts: ConfusionCounts; metrics: EvaluationMetrics; total_evaluated_pairs: number;
  comparison: EvaluationComparison;
};
export type DetectionEvaluationReport = {
  schema_version: "1.0" | "1.1"; report_type: "aegisai_synthetic_detection_evaluation_report";
  dataset_id: string; dataset_version: string; dataset_sha256: string; detector_config_sha256: string;
  rule_catalog_version: string; detector_rule_version: string; scenario_rule_mapping_version: string; attack_mapping_catalog_version: string;
  counting_unit: string; counts: ConfusionCounts; metrics: EvaluationMetrics; total_evaluated_pairs: number;
  per_rule: { rule_id: string; counts: ConfusionCounts; metrics: EvaluationMetrics }[];
  rule_event_mapping: { rule_id: string; event_types: string[] }[];
  scenario_rule_mapping: { scenario_id: string; expected_rule_ids: string[]; evaluated_rule_ids: string[]; observed_rule_ids: string[]; technique_ids: string[]; status: "pass" | "fail" | "rejected" }[];
  technique_coverage: { technique_id: string; name: string; scenario_ids: string[]; rule_ids: string[]; status: "covered"; scope_note: string }[];
  untested_techniques: { technique_id: string; name: string; status: "not_tested" | "candidate_not_mapped"; rationale: string }[];
  coverage_status: "complete" | "partial" | "legacy_unavailable"; warnings: string[]; history: EvaluationRunSummary[];
  valid_scenario_count: number; rejected_scenario_count: number; limitations: string[];
};
export type DetectionEvaluationResponse = {
  data_classification: "synthetic";
  label: "SYNTHETIC EVALUATION - NOT REAL SECURITY PERFORMANCE";
  tenant_id: string; report: DetectionEvaluationReport;
};
export type ExecutiveReportObservation = {
  evidence_ref: string; event_id: string; event_type: string; occurred_at_utc: string; related_finding_ids: string[];
};
export type ExecutiveRisk = {
  classification: "inferred_risk"; finding_id: string; rule_id: string; severity: Severity;
  confidence: number; status: FindingStatus; first_seen_utc: string; last_seen_utc: string;
  asset_ref: string; explanation: string; confidence_factors: string[]; evidence_refs: string[];
};
export type ExecutiveReport = {
  schema_version: "1.0"; report_type: "aegisai_executive_incident_report"; report_id: string;
  tenant_id: string; generated_at_utc: string; data_classification: "synthetic";
  label: "SYNTHETIC - NOT REAL CLIENT DATA"; executive_summary: string;
  finding_counts: { by_severity: Record<Severity, number>; by_status: Record<FindingStatus, number> };
  observations: ExecutiveReportObservation[]; inferred_risks: ExecutiveRisk[]; confirmed_findings: never[];
  timeline: { occurred_at_utc: string; evidence_ref: string; event_id: string; event_type: string; finding_ids: string[] }[];
  recommendations: { category: "investigation" | "remediation"; finding_id: string; text: string }[];
  limitations: string[];
};
export type ExecutiveReportResponse = {
  data_classification: "synthetic"; label: "SYNTHETIC - NOT REAL CLIENT DATA"; tenant_id: string; report: ExecutiveReport;
};
