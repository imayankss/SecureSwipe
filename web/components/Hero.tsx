"use client";

import { motion } from "framer-motion";
import { ArrowRight, GitBranch, ShieldCheck } from "lucide-react";
import { heroMetrics } from "@/data/metrics";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { MetricCard } from "@/components/MetricCard";

export function Hero() {
  return (
    <section className="relative overflow-hidden px-4 py-14 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[1.1fr_0.9fr] lg:items-center">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
        >
          <Badge>
            <ShieldCheck className="h-3.5 w-3.5" />
            Day 8 SecureSwipe Dashboard
          </Badge>
          <h1 className="mt-6 max-w-4xl text-5xl font-semibold text-white sm:text-7xl">
            SecureSwipe
          </h1>
          <p className="mt-4 max-w-3xl text-xl font-medium text-cyan-100">
            Credit Card Fraud Detection & Risk Scoring System
          </p>
          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-300">
            AI-powered fraud detection for highly imbalanced transaction data.
            Built with XGBoost, threshold tuning, PR-AUC focused evaluation, and
            SHAP explainability.
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row">
            <Button href="#performance">
              View Results <ArrowRight className="h-4 w-4" />
            </Button>
            <Button
              href="https://github.com/imayankss/Credit-Card-Fraud-Detection"
              target="_blank"
              rel="noreferrer"
              variant="secondary"
            >
              <GitBranch className="h-4 w-4" />
              GitHub Repository
            </Button>
          </div>
          <motion.div
            className="signal-strip mt-8 max-w-xl rounded-lg border border-white/10 bg-slate-950/45 p-4"
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5, delay: 0.18 }}
          >
            <div className="flex items-center justify-between gap-4 text-xs text-slate-400">
              <span>locked threshold</span>
              <span className="font-medium text-cyan-100">0.53</span>
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/10">
              <div className="h-full w-[83%] rounded-full bg-gradient-to-r from-cyan-200 via-emerald-200 to-cyan-200" />
            </div>
            <div className="mt-3 flex items-center gap-2 text-xs text-slate-300">
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-300 [animation:softPulse_1.8s_ease-in-out_infinite]" />
              model signal: high-recall fraud review mode
            </div>
          </motion.div>
        </motion.div>

        <motion.div
          className="grid grid-cols-1 gap-3 sm:grid-cols-2"
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55, delay: 0.1 }}
        >
          {heroMetrics.map((metric) => (
            <MetricCard key={metric.label} {...metric} />
          ))}
        </motion.div>
      </div>
    </section>
  );
}
