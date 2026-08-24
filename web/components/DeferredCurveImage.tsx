"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";

export function DeferredCurveImage({
  src,
  alt,
}: {
  src: string;
  alt: string;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const observer = new IntersectionObserver(([entry]) => {
      if (!entry.isIntersecting) return;
      setIsVisible(true);
      observer.disconnect();
    });

    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef}>
      {isVisible ? (
        <Image
          src={src}
          alt={alt}
          width={1200}
          height={900}
          unoptimized
          sizes="(max-width: 1024px) 100vw, 50vw"
          className="w-full rounded-lg border border-white/10 bg-white"
        />
      ) : (
        <div
          role="img"
          aria-label={alt}
          className="aspect-[4/3] w-full rounded-lg border border-white/10 bg-white"
        />
      )}
    </div>
  );
}
