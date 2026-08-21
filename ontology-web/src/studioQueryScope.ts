import type { StudioPageId, StudioSubpageId } from "./StudioNavigation";

export type StudioQueryScope = {
  constructionRuns: boolean;
  constructionJobs: boolean;
  reviewDraft: boolean;
  sourceLibrary: boolean;
  runtime: boolean;
  llmStatus: boolean;
};

export function studioQueryScope(
  page: StudioPageId,
  subpage: StudioSubpageId,
): StudioQueryScope {
  const constructionRuns = (
    (page === "inputs" && subpage === "runs")
    || page === "semantic"
    || (page === "quality" && subpage === "review")
  );
  const constructionJobs = page === "inputs" && subpage === "runs";
  const reviewDraft = page === "quality" && subpage === "review";
  const sourceLibrary = page === "overview"
    || (page === "inputs" && ["sources", "runs"].includes(subpage));
  const runtime = page === "overview" || page === "release";
  const llmStatus = page === "overview" || constructionJobs;

  return {
    constructionRuns,
    constructionJobs,
    reviewDraft,
    sourceLibrary,
    runtime,
    llmStatus,
  };
}
