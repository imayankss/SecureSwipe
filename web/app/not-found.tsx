import { ArrowLeft, ShieldAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <main className="grid min-h-screen place-items-center bg-slate-950 px-4 text-slate-100">
      <div className="max-w-lg text-center">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl border border-cyan-200/20 bg-cyan-300/10">
          <ShieldAlert className="h-6 w-6 text-cyan-200" aria-hidden="true" />
        </span>
        <p className="mt-6 text-sm font-semibold uppercase tracking-[0.2em] text-cyan-200">404</p>
        <h1 className="mt-3 text-4xl font-semibold text-white">This route is not in the review queue.</h1>
        <p className="mt-4 leading-7 text-slate-300">
          The SecureSwipe dashboard is available from the main overview.
        </p>
        <Button href="/" className="mt-8">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Return to dashboard
        </Button>
      </div>
    </main>
  );
}
