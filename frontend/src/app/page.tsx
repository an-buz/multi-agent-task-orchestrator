import DashboardContent from "./dashboard-content";
import { Suspense } from "react";

export default function DashboardPage() {
  return <Suspense fallback={<p>Loading dashboard…</p>}><DashboardContent /></Suspense>;
}
