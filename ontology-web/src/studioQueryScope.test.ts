import { describe, expect, it } from "vitest";

import { studioQueryScope } from "./studioQueryScope";

describe("studioQueryScope", () => {
  it("does not load heavyweight construction history on unrelated pages", () => {
    for (const [page, subpage] of [
      ["overview", "summary"],
      ["inputs", "requirements"],
      ["data", "schemas"],
      ["quality", "validation"],
      ["release", "versions"],
    ] as const) {
      const scope = studioQueryScope(page, subpage);
      expect(scope.constructionRuns).toBe(false);
      expect(scope.constructionJobs).toBe(false);
      expect(scope.reviewDraft).toBe(false);
    }
  });

  it("loads each construction dataset only where the page consumes it", () => {
    expect(studioQueryScope("inputs", "runs")).toMatchObject({
      constructionRuns: true,
      constructionJobs: true,
      reviewDraft: false,
    });
    expect(studioQueryScope("semantic", "graph")).toMatchObject({
      constructionRuns: true,
      constructionJobs: false,
      reviewDraft: false,
    });
    expect(studioQueryScope("semantic", "metrics")).toMatchObject({
      constructionRuns: true,
      constructionJobs: false,
      reviewDraft: false,
    });
    expect(studioQueryScope("quality", "review")).toMatchObject({
      constructionRuns: true,
      constructionJobs: false,
      reviewDraft: true,
    });
  });

  it("scopes source, runtime, and LLM reads to their consuming views", () => {
    expect(studioQueryScope("overview", "summary")).toMatchObject({
      sourceLibrary: true,
      runtime: true,
      llmStatus: true,
      llmObservations: false,
    });
    expect(studioQueryScope("inputs", "sources")).toMatchObject({ sourceLibrary: true });
    expect(studioQueryScope("inputs", "runs")).toMatchObject({
      llmStatus: true,
      llmObservations: true,
      sourceLibrary: true,
    });
    expect(studioQueryScope("release", "delivery")).toMatchObject({ runtime: true });
    expect(studioQueryScope("data", "mappings")).toMatchObject({
      sourceLibrary: false,
      runtime: false,
      llmStatus: false,
      llmObservations: false,
    });
  });
});
