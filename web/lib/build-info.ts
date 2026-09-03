/**
 * Build provenance for the static reviewer surfaces.
 *
 * Values are injected at build time by `next.config.ts` from the hosting or CI
 * environment (Vercel, GitHub Actions) or, failing that, from the local git
 * checkout. Nothing is inferred at runtime, and nothing is guessed: when a
 * commit cannot be established the surface says so rather than rendering a
 * placeholder a reviewer could mistake for a verified build.
 */

const COMMIT_SHA = /^[0-9a-f]{40}$/;

function readSha(): string | null {
  const raw = process.env.NEXT_PUBLIC_BUILD_SHA?.trim().toLowerCase();
  return raw && COMMIT_SHA.test(raw) ? raw : null;
}

function readBuiltAt(): string | null {
  const raw = process.env.NEXT_PUBLIC_BUILD_TIME?.trim();
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
}

const sha = readSha();

export const buildInfo = {
  sha,
  shortSha: sha ? sha.slice(0, 7) : null,
  builtAt: readBuiltAt(),
  /** True only when the build can name the exact commit it was produced from. */
  isVerifiable: sha !== null,
} as const;

/**
 * Fixed UTC rendering. The footer must read identically for every reviewer
 * regardless of locale or timezone, so this deliberately avoids `toLocaleString`.
 */
export function formatBuiltAt(iso: string): string {
  return `${iso.slice(0, 10)} ${iso.slice(11, 16)} UTC`;
}

/** Only build a commit link for an https GitHub repository URL. */
export function commitUrl(repository: string): string | null {
  if (!sha) return null;
  let parsed: URL;
  try {
    parsed = new URL(repository);
  } catch {
    return null;
  }
  if (parsed.protocol !== "https:" || parsed.hostname !== "github.com") return null;
  return `https://github.com${parsed.pathname.replace(/\/+$/, "")}/commit/${sha}`;
}
