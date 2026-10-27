import { Icon } from "./icons";

export function Brand() {
  return <a className="brand" href="index.html" aria-label="AegisAI home"><span className="brand-mark"><Icon name="shield" /></span><span>Aegis<span className="brand-accent">AI</span></span></a>;
}

export function Footer({ dashboard = false }: { dashboard?: boolean }) {
  return <footer className={dashboard ? "footer site-footer" : "site-footer"}>
    <div className="page-width footer-inner"><Brand /><p>Research prototype · Synthetic examples · Read-only</p>
      <a href="privacy.html">Privacy</a><a href={dashboard ? "index.html" : "dashboard.html"}>{dashboard ? "Home" : "Explore dashboard"}</a>
    </div>
  </footer>;
}

