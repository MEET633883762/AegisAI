import { useEffect, useState } from "react";
import { Brand } from "./SiteChrome";
import { Icon } from "./icons";
import { ResearchDemo } from "./ResearchDemo";
import { WebsiteAssessment } from "./WebsiteAssessment";

export function DashboardPage() {
  const [presenting, setPresenting] = useState(false);
  const sectionFromHash = () => window.location.hash === "#assessment" ? "assessment" : window.location.hash === "#episode-outcome" ? "outcome" : "exercise";
  const [activeSection, setActiveSection] = useState(sectionFromHash);
  useEffect(() => {
    const exit = (event: KeyboardEvent) => {
      if (event.key === "Escape") setPresenting(false);
    };
    window.addEventListener("keydown", exit);
    const followHash = () => setActiveSection(sectionFromHash());
    window.addEventListener("hashchange", followHash);
    return () => {
      window.removeEventListener("keydown", exit);
      window.removeEventListener("hashchange", followHash);
    };
  }, []);

  const currentSection = presenting ? "exercise" : activeSection;

  return <div className={`demo-page${presenting ? " presentation-view" : ""}`}>
    <a className="skip-link" href="#dashboard-main">Skip to dashboard</a>
    <nav className="demo-nav" aria-label="Main navigation">
      <Brand />
      <div className="demo-nav-links">
        <a href="index.html">Overview</a>
        <a className={currentSection === "exercise" ? "current" : ""} href="#research-demo" aria-current={currentSection === "exercise" ? "location" : undefined}>The exercise</a>
        {!presenting && <a className={currentSection === "outcome" ? "current" : ""} href="#episode-outcome" aria-current={currentSection === "outcome" ? "location" : undefined}>Results</a>}
        <a className={currentSection === "assessment" ? "current" : ""} href="#assessment" aria-current={currentSection === "assessment" ? "location" : undefined}>Before & after</a>
      </div>
      <button className="presentation-toggle" type="button" aria-pressed={presenting} onClick={() => {
        setPresenting(!presenting);
        window.scrollTo?.({ top: 0, behavior: "instant" });
      }}><Icon name={presenting ? "monitor" : "play"} />{presenting ? "Exit presentation" : "Present demo"}</button>
    </nav>
    <main id="dashboard-main">
      <header className="demo-hero">
        <div><p className="eyebrow"><span className="session-dot" /> THE INTERACTIVE RESEARCH LAB</p>
          <h1>A cyberattack,<br /><span>explained.</span></h1>
          <p className="demo-lede">Follow the attack. Question the response.<br className="desktop-break" /> See the evidence behind every security decision.</p>
          <div className="demo-hero-actions"><a className="button button-primary" href="#research-demo">Start the walkthrough <Icon name="arrow" /></a><span>6 moments · At your own pace</span></div>
        </div>
        <div className="demo-hero-note">
          <div className="session-card-head"><Icon name="shield" /><span>EXERCISE BRIEF / 001</span><span className="session-tag">SYNTHETIC</span></div>
          <strong>Can detection become<br />effective defense?</strong>
          <p>A fictional network. Two competing roles. One Controller that checks every move.</p>
          <dl className="session-facts"><div><dt>Scenario</dt><dd>Credential reuse</dd></div><div><dt>Evidence</dt><dd>39 recorded actions</dd></div><div><dt>Execution</dt><dd>Read-only replay</dd></div></dl>
        </div>
      </header>

      <section className="actor-cards" aria-label="Meet the three roles">
        <article className="actor-card actor-card-red"><span className="actor-card-icon"><Icon name="target" /></span><div><p>01 / THE ATTACKER <span>RED TEAM</span></p><h2>Finds a way in.</h2><span>Tries to reach the fictional records.</span></div></article>
        <article className="actor-card actor-card-gate"><span className="actor-card-icon"><Icon name="lock" /></span><div><p>02 / THE SAFETY GATE <span>CONTROLLER</span></p><h2>Checks every move.</h2><span>Enforces the simulation's permissions.</span></div></article>
        <article className="actor-card actor-card-blue"><span className="actor-card-icon"><Icon name="shield" /></span><div><p>03 / THE DEFENDER <span>BLUE TEAM</span></p><h2>Follows the clues.</h2><span>Investigates the warning signs.</span></div></article>
      </section>
      <aside className="demo-disclosure"><Icon name="eye" /><p><strong>You're watching a recorded, scripted exercise.</strong> All data is synthetic. Selecting a step changes the view; it does not execute an attack or call an AI model.</p><span>READ-ONLY DEMO</span></aside>
      {presenting && <p className="presentation-hint"><Icon name="monitor" /> Presentation view <span>Use the moment controls to explore · Esc to exit</span></p>}
      <ResearchDemo />
      <WebsiteAssessment />
      <section className="why-aegis"><span className="eyebrow">THE RESEARCH QUESTION</span><h2>Don't just count alerts.<br /><span>Understand the decision behind them.</span></h2><div><p><Icon name="eye" /><span><strong>Evidence you can inspect</strong>See what each role actually knew before it acted.</span></p><p><Icon name="lock" /><span><strong>Permissions you can verify</strong>The Controller owns execution and authorization.</span></p><p><Icon name="arrow" /><span><strong>A result you can reproduce</strong>Replay the same seeded scenario and compare outcomes.</span></p></div></section>
      <footer className="demo-footer"><Brand /><p>Built to question security decisions.<br />Research prototype · Synthetic results · Read-only</p><a href="privacy.html">Privacy & data handling <span aria-hidden="true">↗</span></a></footer>
    </main>
  </div>;
}
