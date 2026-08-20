import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SecureSwipe | Fraud Detection & Risk Analytics",
  description:
    "Explore locked historical XGBoost artifacts, threshold trade-offs, confusion matrices, and non-causal SHAP summaries from the SecureSwipe ML pipeline.",
  applicationName: "SecureSwipe",
  keywords: [
    "fraud detection",
    "machine learning",
    "XGBoost",
    "risk analytics",
    "SHAP",
    "portfolio project",
  ],
  authors: [{ name: "Mayank Suryavanshi" }],
  openGraph: {
    type: "website",
    title: "SecureSwipe | Fraud Detection & Risk Analytics",
    description:
      "A deployment-safe view of tracked historical fraud-model artifacts and their explicit limitations.",
    siteName: "SecureSwipe",
  },
  twitter: {
    card: "summary",
    title: "SecureSwipe | Fraud Detection & Risk Analytics",
    description:
      "Tracked historical fraud-model artifacts, threshold analysis, and stated limitations.",
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
      <body className="min-h-full bg-slate-950">{children}</body>
    </html>
  );
}
