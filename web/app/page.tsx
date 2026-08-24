
import { Footer } from "@/components/Footer";
import { Navigation } from "@/components/Navigation";
import { CommandCenterDashboard } from "@/components/dashboard/CommandCenterDashboard";

export default function Home() {
  return (
    <>
      <Navigation />
      <main
        id="main-content"
        tabIndex={-1}
        className="min-h-screen overflow-hidden bg-slate-950 text-slate-100"
      >
        <div className="dashboard-grid fixed inset-0 -z-10 bg-[linear-gradient(135deg,#020617_0%,#07111f_48%,#061d1f_100%)]" />
        <CommandCenterDashboard />
        <Footer />
      </main>
    </>
  );
}
