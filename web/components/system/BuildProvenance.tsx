import { buildInfo, commitUrl, formatBuiltAt } from "@/lib/build-info";

/**
 * Renders the exact commit and build time behind the deployed reviewer
 * surfaces, so a published page can be tied back to a reviewable source tree.
 * This is provenance, not evidence: it says which code was built, never that a
 * model, metric, or deployment was verified.
 */
export function BuildProvenance({ repository }: { repository: string }) {
  if (!buildInfo.isVerifiable) {
    return (
      <p className="font-mono text-xs text-slate-500">
        build provenance unavailable — commit not recorded at build time
      </p>
    );
  }

  const href = commitUrl(repository);

  return (
    <p className="font-mono text-xs text-slate-500">
      <span className="sr-only">Built from commit </span>
      build{" "}
      {href ? (
        <a className="ss-text-link" href={href} target="_blank" rel="noreferrer">
          {buildInfo.shortSha}
        </a>
      ) : (
        <span className="text-slate-400">{buildInfo.shortSha}</span>
      )}
      {buildInfo.builtAt ? ` · ${formatBuiltAt(buildInfo.builtAt)}` : null}
    </p>
  );
}
