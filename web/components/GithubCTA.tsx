import { ArrowUpRight, FileText, GitBranch, Workflow } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Section } from "@/components/Section";

export function GithubCTA() {
  return (
    <Section
      id="github"
      eyebrow="Project"
      title="Explore the full ML system"
      description="The dashboard is a presentation layer on top of a complete Python fraud detection pipeline."
    >
      <Card>
        <CardContent className="flex flex-col gap-4 p-5 sm:flex-row">
          <Button href="https://github.com/imayankss/Credit-Card-Fraud-Detection" target="_blank" rel="noreferrer">
            <GitBranch className="h-4 w-4" />
            View GitHub Repository
          </Button>
          <Button href="#pipeline" variant="secondary">
            <Workflow className="h-4 w-4" />
            View ML Pipeline
          </Button>
          <Button
            href="https://github.com/imayankss/Credit-Card-Fraud-Detection/blob/main/reports/final/final_project_report.md"
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
