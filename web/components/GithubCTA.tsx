import { ArrowUpRight, FileText, GitBranch, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Section } from "@/components/Section";
import { dashboardData } from "@/data/metrics";

export function GithubCTA() {
  return (
    <Section
      id="github"
      eyebrow="Project"
      title="Explore the full ML system"
      description="The dashboard is a presentation layer on top of a complete Python fraud detection pipeline."
    >
      <Card>
        {/* This card has no CardHeader, so the top padding CardContent normally
            drops (pt-0) has to be restored or the row sits flush to the top. */}
        <CardContent className="flex flex-col flex-wrap items-stretch gap-3 pt-5 sm:flex-row sm:items-center sm:pt-6">
          <Button href={dashboardData.project.repository} target="_blank" rel="noreferrer">
            <GitBranch className="h-4 w-4" />
            View GitHub Repository
          </Button>
          <Button href="#pipeline" variant="secondary">
            <Workflow className="h-4 w-4" />
            View ML Pipeline
          </Button>
          <Button
            href={`${dashboardData.project.repository}/blob/main/reports/final/final_project_report.md`}
            target="_blank"
            rel="noreferrer"
            variant="secondary"
          >
            <FileText className="h-4 w-4" />
            View Final Report
            <ArrowUpRight className="h-4 w-4" />
          </Button>
        </CardContent>
      </Card>
    </Section>
  );
}
