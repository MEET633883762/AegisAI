import { createRoot } from "react-dom/client";
import { LocalDashboard } from "./localDashboard/LocalDashboard";
import "./localDashboard/localDashboard.css";

const mount = document.getElementById("local-dashboard-root");
if (!mount) throw new Error("Local dashboard mount point is missing.");
createRoot(mount).render(<LocalDashboard />);
