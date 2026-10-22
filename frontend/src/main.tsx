import { createRoot } from "react-dom/client";
import { App } from "./App";
import "../landing.css";
import "../styles.css";
import "../website_assessment.css";

const mount = document.getElementById("app-root");
if (!mount) throw new Error("The AegisAI application mount point is missing.");
createRoot(mount).render(<App page={document.body.dataset.page ?? "unknown"} />);
