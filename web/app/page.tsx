import type { Metadata } from "next";

import { Footer } from "@/components/Footer";
import { Navigation } from "@/components/Navigation";
import { ProductHomepage } from "@/components/product/ProductHomepage";

export const metadata: Metadata = {
  title: "SecureSwipe | Human-review payment-risk decision support",
  description:
    "Inspect bounded payment-risk review signals, capacity trade-offs, and their evidence.",
};

export default function Home() {
  return (
    <>
      <Navigation activePage="product" />
      <main
        id="main-content"
        tabIndex={-1}
        className="ss-app-background min-h-screen overflow-x-clip"
      >
        <ProductHomepage />
        <Footer />
      </main>
    </>
  );
}
