import type { StudioPageId, StudioSubpageId } from "./StudioNavigation";

export type StudioQueryScope = {
  constructionRuns: boolean;
  constructionJobs: boolean;
  reviewDraft: boolean;
  sourceLibrary: boolean;
  runtime: boolean;
};

export function studioQueryScope(
  page: StudioPageId,
  subpage: StudioSubpageId,
): StudioQueryScope {
  const constructionRuns = (
    page === "construction"
    || page === "semantic"
  );
  const constructionJobs = page === "construction" && subpage === "runs";
  const reviewDraft = page === "construction" && subpage === "review";
  const sourceLibrary = page === "overview"
    || (page === "inputs" && subpage === "sources")
    || constructionJobs;
  const runtime = page === "overview"
    || (page === "quality" && ["versions", "delivery"].includes(subpage));

  return {
    constructionRuns,
    constructionJobs,
    reviewDraft,
    sourceLibrary,
    runtime,
  };
}
