import { describe, expect, it } from "vitest";

import { studioQueryScope } from "./studioQueryScope";

describe("studioQueryScope", () => {
  it("does not load heavyweight construction history on unrelated pages", () => {
    for (const [page, subpage] of [
      ["overview", "summary"],
      ["inputs", "requirements"],
      ["data", "schemas"],
      ["quality", "validation"],
      ["quality", "versions"],
    ] as const) {
      const scope = studioQueryScope(page, subpage);
      expect(scope.constructionRuns).toBe(false);
      expect(scope.constructionJobs).toBe(false);
      expect(scope.reviewDraft).toBe(false);
    }
  });

  it("loads each construction dataset only where the page consumes it", () => {
    expect(studioQueryScope("construction", "runs")).toMatchObject({
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
    expect(studioQueryScope("construction", "review")).toMatchObject({
      constructionRuns: true,
      constructionJobs: false,
      reviewDraft: true,
    });
  });

  it("scopes source, runtime, and model-capability reads to their consuming views", () => {
    expect(studioQueryScope("overview", "summary")).toMatchObject({
      sourceLibrary: true,
      runtime: true,
    });
    expect(studioQueryScope("inputs", "sources")).toMatchObject({ sourceLibrary: true });
    expect(studioQueryScope("construction", "runs")).toMatchObject({
      sourceLibrary: true,
    });
    expect(studioQueryScope("quality", "delivery")).toMatchObject({ runtime: true });
    expect(studioQueryScope("data", "mappings")).toMatchObject({
      sourceLibrary: false,
      runtime: false,
    });
  });
});
