import type { EpisodeRecord } from "./types";

export const hostNames: Record<string, string> = {
  host_a: "Public website", host_b: "Sample database", host_c: "Workstation", host_d: "Internal service",
};

const descriptions: Record<string, { title: string; explanation: string }> = {
  ENUMERATE_PORT: { title: "Looking for a way in", explanation: "The attacker checks which digital doors are open on this simulated computer." },
  DISCOVER_SERVICE: { title: "Learning what is running", explanation: "The attacker identifies the software behind an open door to plan its next move." },
  EXPLOIT_SIMULATED_VULNERABILITY: { title: "A weakness becomes a foothold", explanation: "The attacker tries a deliberately simulated software weakness to gain access to the website." },
  OBTAIN_CREDENTIAL: { title: "Looking for the next key", explanation: "The attacker looks for simulated login credentials that could unlock another computer." },
  DISCOVER_HOST: { title: "Finding another computer", explanation: "The attacker discovers another target inside the fictional network." },
  LATERAL_MOVE: { title: "Trying the next door", explanation: "The attacker attempts to use a captured login to reach another simulated computer." },
  ACCESS_SENSITIVE_ASSET: { title: "Reaching the sample records", explanation: "The attacker attempts to access the fictional customer records in the sample database." },
  COLLECT_DATA: { title: "Gathering the sample data", explanation: "The attacker attempts to collect synthetic records inside the simulator." },
  EXFILTRATE_SIMULATED_DATA: { title: "The attacker attempts its final goal", explanation: "The attacker tries to take the synthetic records out of the simulated network. No real data is involved." },
  INVESTIGATE_ALERT: { title: "The defender checks a warning", explanation: "The defender reviews the evidence behind an alert. Investigating a warning does not itself block an attacker." },
  ISOLATE_HOST: { title: "Separating a computer from the network", explanation: "The defender tries to contain the threat by isolating a simulated computer." },
  PATCH_SERVICE: { title: "Closing a known weakness", explanation: "The defender attempts to patch a vulnerable simulated service." },
};

export function describeRecord(record: EpisodeRecord) {
  return descriptions[record.action.type] ?? {
    title: "A recorded security decision", explanation: `The ${record.role === "red" ? "attacker" : "defender"} proposes an action. Inspect its technical evidence below.`,
  };
}

export function explainResult(record: EpisodeRecord): string {
  if (!record.result.success) {
    return record.action.type === "LATERAL_MOVE" ? "The login was rejected. This move failed." : "This attempt did not succeed.";
  }
  const results: Record<string, string> = {
    ENUMERATE_PORT: "Open digital doors were found.",
    DISCOVER_SERVICE: "The running software was identified.",
    EXPLOIT_SIMULATED_VULNERABILITY: "The attacker gained a foothold on the website.",
    OBTAIN_CREDENTIAL: "A simulated login was captured.",
    DISCOVER_HOST: "Another computer was discovered.",
    LATERAL_MOVE: "The attacker gained access to another computer.",
    ACCESS_SENSITIVE_ASSET: "The fictional customer records were accessed.",
    COLLECT_DATA: "The synthetic records were collected.",
    EXFILTRATE_SIMULATED_DATA: "The synthetic data left the practice network.",
    INVESTIGATE_ALERT: "The defender reviewed the alert evidence.",
  };
  return results[record.action.type] ?? record.result.message;
}

/** Select actual records, never invent intermediate events or outcomes. */
export function keyMoments(records: EpisodeRecord[]): EpisodeRecord[] {
  const first = records[0];
  const foothold = records.find((r) => r.action.type === "EXPLOIT_SIMULATED_VULNERABILITY");
  const investigation = records.find((r) => r.role === "blue" && r.sequence > (foothold?.sequence ?? 0));
  const rejected = records.find((r) => !r.result.success);
  const database = records.find((r) => r.action.type === "ACCESS_SENSITIVE_ASSET");
  const last = records.at(-1);
  return [...new Map([first, foothold, investigation, rejected, database, last]
    .filter((r): r is EpisodeRecord => Boolean(r)).map((r) => [r.id, r])).values()]
    .sort((a, b) => a.sequence - b.sequence);
}
