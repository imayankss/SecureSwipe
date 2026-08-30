import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SecureSwipe | Human-review payment-risk decision support",
  description:
    "A defense-only payment-risk decision aid with explicit evidence and review boundaries.",
  applicationName: "SecureSwipe",
  keywords: [
    "fraud detection",
    "machine learning",
    "risk analytics",
    "human review",
    "portfolio project",
  ],
  authors: [{ name: "Mayank Suryavanshi" }],
  openGraph: {
    type: "website",
    title: "SecureSwipe | Human-review payment-risk decision support",
    description:
      "Inspect bounded payment-risk review signals and their explicit evidence boundaries.",
    siteName: "SecureSwipe",
  },
  twitter: {
    card: "summary",
    title: "SecureSwipe | Human-review payment-risk decision support",
    description:
      "Bounded payment-risk review signals, evidence, and stated limitations.",
  },
  robots: { index: true, follow: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
