import { useEffect, useState } from "react";
import type { EpisodeRecord, PublicEpisode } from "./types";
import { parseEpisodeArtifact, readBoundedResponseText } from "./researchArtifact";
import { EpisodeWalkthrough, EpisodeOutcome } from "./EpisodeWalkthrough";
import { EpisodeEvidence } from "./EpisodeEvidence";
import { Icon } from "./icons";
import episodeUrl from "../data/public_demo_episode.json?url&no-inline";

export function ResearchDemo() {
  const [artifact, setArtifact] = useState<PublicEpisode | null>(null);
  const [selected, setSelected] = useState<EpisodeRecord | null>(null);
  const [status, setStatus] = useState("Loading the precomputed sample…");
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setFailed(false);
      setStatus("Loading the precomputed sample…");
      try {
        const response = await fetch(episodeUrl, { cache: "no-cache", credentials: "same-origin" });
        if (!response.ok) throw new Error(`Sample artifact request failed (${response.status}).`);
        const nextArtifact = parseEpisodeArtifact(await readBoundedResponseText(response));
        if (!active) return;
        setArtifact(nextArtifact);
        setSelected(nextArtifact.records[0] ?? null);
        setStatus(`Loaded ${nextArtifact.records.length} precomputed action records. No actions were executed.`);
      } catch (error) {
        if (active) {
          setStatus(`Could not load the sample: ${error instanceof Error ? error.message : "unexpected error"}`);
          setFailed(true);
        }
      }
    };
    void load();
    return () => { active = false; };
  }, [attempt]);

  useEffect(() => {
    if (!artifact) return;
    const revealSection = () => {
      const target = window.location.hash.slice(1);
      if (target !== "episode-evidence" && target !== "episode-outcome") return;
      const element = document.getElementById(target);
      if (target === "episode-evidence") element?.setAttribute("open", "");
      element?.scrollIntoView?.({ block: "start" });
    };
    revealSection();
    window.addEventListener("hashchange", revealSection);
    return () => window.removeEventListener("hashchange", revealSection);
  }, [artifact]);

  return <section className="research-demo" id="research-demo" aria-labelledby="research-demo-title">
    <div className="section-head research-demo-head"><div><p className="eyebrow">01 / FOLLOW THE EXERCISE</p><h2 id="research-demo-title">One attack. Every decision visible.</h2><p className="muted">Explore six key moments. The map and explanation follow the record you select.</p></div><span className="badge replay-badge"><span className="dot" />Recorded, not live</span></div>
    <p className="load-status" role="status" aria-live="polite">{status}</p>
    {!artifact && !failed && <div className="replay-loading" aria-hidden="true"><div><span /><span /><span /></div><div><Icon name="shield" /><p>Preparing the recorded exercise</p></div></div>}
    {failed && <div className="replay-error"><Icon name="server" /><div><strong>The replay is temporarily unavailable.</strong><p>Check that the local demo server is running, then try loading the sample again.</p></div><button type="button" onClick={() => setAttempt((value) => value + 1)}>Retry sample</button></div>}
    {artifact && selected && <>
      <EpisodeWalkthrough artifact={artifact} selected={selected} onSelect={setSelected} />
      <EpisodeOutcome artifact={artifact} />
      <div className="takeaway"><span className="takeaway-icon"><Icon name="eye" /></span><p><strong>The lesson: noticing a threat is not the same as stopping it.</strong> In this scripted sample, the defender keeps investigating while the attacker advances. The trace makes that response gap visible.</p></div>
      <EpisodeEvidence artifact={artifact} selected={selected} onSelect={setSelected} />
    </>}
    <div className="research-download-row"><p className="muted">Synthetic data · Scripted agents · One reproducible episode · No real-world accuracy claim</p><a className="download-sample" href={episodeUrl} download="aegisai-synthetic-episode-v1.json">Download sample report <span aria-hidden="true">↓</span></a></div>
  </section>;
}

