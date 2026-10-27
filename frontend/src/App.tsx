import { LandingPage } from "./LandingPage";
import { DashboardPage } from "./DashboardPage";
import { PrivacyPage } from "./PrivacyPage";

export function App({ page }: { page: string }) {
  if (page === "landing") return <LandingPage />;
  if (page === "dashboard") return <DashboardPage />;
  if (page === "privacy") return <PrivacyPage />;
  return <main className="page-width"><h1>Page unavailable</h1><p>Choose Home or Research demo from the navigation.</p><a href="index.html">Home</a></main>;
}
