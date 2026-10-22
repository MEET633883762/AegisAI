export type Role = "red" | "blue";

export interface PublicEpisode {
  schema_version: "1.0";
  artifact_type: "aegisai_public_research_episode";
  labels: {
    display: string;
    synthetic: true;
    precomputed: true;
    public_execution: false;
  };
  provenance: {
    episode_id: string;
    scenario_id: string;
    scenario_template: string;
    seed: number;
    research_split: string;
    red_policy: string;
    blue_policy: string;
    generator: string;
    generation_mode: string;
    recorded_steps: number;
  };
  objective_result: { achieved: boolean; definition: string; episode_count: 1 };
  metrics: EpisodeMetric[];
  records: EpisodeRecord[];
  limitations: string[];
}

export interface EpisodeMetric {
  id: string;
  label: string;
  value: number;
  numerator: number;
  denominator: number;
  unit: string;
  definition: string;
}

export interface EpisodeEvidence {
  source: string;
  reference: string;
  value: string;
}

export interface EpisodeRecord {
  id: string;
  sequence: number;
  step: number;
  role: Role;
  visibility_scope: Role;
  validation: { accepted: boolean; reason: string };
  authorization: { authorized: boolean; policy_reason: string };
  action: {
    type: string;
    target: string;
    parameters: Record<string, string>;
    reason_category: string;
    expected_outcome: string;
  };
  result: { outcome: string; success: boolean; message: string };
  evidence: EpisodeEvidence[];
}

export interface AssessmentFinding {
  id: string;
  severity: string;
  title: string;
  description: string;
  evidence: string;
  remediation: string;
}

export interface AssessmentHeaderResult {
  header: string;
  expected_value: string;
  observed_value: string | null;
  present: boolean;
}

export interface AssessmentReport {
  schema_version: "1.0";
  assessment_type: "http_security_header_check";
  checked_at_utc: string;
  status: "passed" | "findings";
  ok: boolean;
  url: "http://127.0.0.1:8765/";
  http_status: number;
  profile: "baseline" | "hardened";
  checked_headers: string[];
  header_results: AssessmentHeaderResult[];
  missing_or_incorrect_headers: string[];
  finding_count: number;
  findings: AssessmentFinding[];
  limitations: string[];
  publication?: {
    synthetic: true;
    precomputed: true;
    public_execution: false;
    source: string;
  };
}
