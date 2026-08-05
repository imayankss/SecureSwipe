import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "SecureSwipe | Fraud Detection & Risk Analytics",
  description:
    "Explore verified XGBoost fraud-detection results, threshold trade-offs, confusion matrices, and SHAP explainability from the SecureSwipe ML pipeline.",
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
      "A deployment-safe view of verified fraud-model evaluation, threshold analysis, and explainability artifacts.",
    siteName: "SecureSwipe",
  },
  twitter: {
    card: "summary",
    title: "SecureSwipe | Fraud Detection & Risk Analytics",
    description:
      "Verified fraud-model evaluation, threshold analysis, and explainability artifacts.",
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
