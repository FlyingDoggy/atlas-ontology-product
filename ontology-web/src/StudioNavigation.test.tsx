import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";

import {
  StudioNavigation,
  StudioSubnavigation,
  studioBuildResultHref,
  studioBuildReviewHref,
  studioBuildRouteFromPath,
  studioPageFromPath,
  studioPageHref,
  studioSubpageFromPath,
  studioSolutionIdFromPath,
} from "./StudioNavigation";

afterEach(cleanup);

describe("StudioNavigation", () => {
  it("maps independent Studio URLs to one bounded page", () => {
    expect(studioPageFromPath("/ontology-studio/")).toBe("solutions");
    expect(studioPageFromPath("/ontology-studio/solutions")).toBe("solutions");
    expect(studioPageFromPath("/ontology-studio/solutions/ontology.exchange_analytics.adt/semantic/graph/")).toBe("semantic");
    expect(studioPageFromPath("/ontology-studio/ontology")).toBe("semantic");
    expect(studioPageFromPath("/ontology-studio/release/")).toBe("quality");
    expect(studioPageFromPath("/ontology-studio/not-a-page")).toBe("overview");
    expect(studioSubpageFromPath("/ontology-studio/solutions/ontology.exchange_analytics.adt/semantic/graph/", "semantic")).toBe("graph");
    expect(studioSubpageFromPath("/ontology-studio/assistant/", "construction")).toBe("review");
    expect(studioSubpageFromPath("/ontology-studio/solutions/ontology.exchange_analytics.adt/release/delivery/", "quality")).toBe("delivery");
    expect(studioSubpageFromPath("/ontology-studio/sources/", "quality")).toBe("changes");
    expect(studioSolutionIdFromPath("/ontology-studio/solutions/ontology.exchange_analytics.adt/semantic/graph/")).toBe("ontology.exchange_analytics.adt");
    expect(studioSolutionIdFromPath("/ontology-studio/solutions/")).toBeNull();
  });

  it("preserves the selected solution in page links", () => {
    expect(studioPageHref("quality", "ontology.exchange_analytics.cash_trading"))
      .toBe("/ontology-studio/solutions/ontology.exchange_analytics.cash_trading/quality/validation/");
    expect(studioPageHref("quality", "ontology.exchange_analytics.adt", "validation"))
      .toBe("/ontology-studio/solutions/ontology.exchange_analytics.adt/quality/validation/");
  });

  it("uses stable deep links for one exact build review and result", () => {
    const runId = `construction-run.${"a".repeat(32)}`;
    const decisionId = `construction-decision.${"b".repeat(32)}`;
    const reviewHref = studioBuildReviewHref("ontology.exchange_analytics.cash_trading", runId);
    const resultHref = studioBuildResultHref("ontology.exchange_analytics.cash_trading", runId, decisionId);

    expect(studioPageFromPath(reviewHref)).toBe("construction");
    expect(studioSubpageFromPath(reviewHref, "construction")).toBe("review");
    expect(studioBuildRouteFromPath(reviewHref)).toEqual({ runId, decisionId: null });
    expect(studioBuildRouteFromPath(resultHref)).toEqual({ runId, decisionId });
  });

  it("renders a hierarchical application navigation without PoC branding", () => {
    render(
      <MemoryRouter>
        <StudioNavigation
          activePage="data"
          solutionName="ADT参考分析"
          solutionVersion="1.4.0"
          activeRuntimeVersion="1.2.1"
          solutionId="ontology.exchange_analytics.adt"
        />
      </MemoryRouter>,
    );

    expect(screen.getByRole("navigation", { name: "Ontology Studio" })).toBeTruthy();
    const directoryLink = screen.getByRole("link", { name: /解决方案目录/ });
    expect(directoryLink.getAttribute("href")).toBe("/ontology-studio/solutions/");
    expect(screen.getByRole("navigation", { name: "当前解决方案工作区" })).toBeTruthy();
    expect(screen.getByText("解决方案工作区")).toBeTruthy();
    expect(screen.getByRole("link", { name: /概览/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /输入与证据/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /构建与复核/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /语义模型/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /^数据/ }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: /质量与发布/ })).toBeTruthy();
    expect(screen.getByText("方案定义")).toBeTruthy();
    expect(screen.getByText("运行语义")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /解决方案目录/ })).toHaveLength(1);
    expect(screen.queryByText(/PoC|Demo|synthetic/i)).toBeNull();
  });

  it("renders second-level navigation inside one primary module", () => {
    render(
      <MemoryRouter>
        <StudioSubnavigation
          page="construction"
          activeSubpage="review"
          solutionId="ontology.exchange_analytics.adt"
        />
      </MemoryRouter>,
    );
    expect(screen.getByRole("navigation", { name: "构建与复核子页面" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /复核队列/ }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: /构建任务/ })).toBeTruthy();
  });
});
