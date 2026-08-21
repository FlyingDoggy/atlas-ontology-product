import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StudioWorkbench } from "./api";
import { PackageContractEditor } from "./PackageContractEditor";

const relationship = {
  id: "relationship.trade.market",
  version: "1.0.0",
  status: "confirmed",
  name: { en: "Trade market", zh: "成交市场" },
  definition: "Trade belongs to a market",
  owner: "actor.owner",
  sources: ["source.requirements"],
  decisions: [], tags: [],
  from_entity: "entity.trade", to_entity: "entity.market",
  predicate: "belongsTo", cardinality: "N:1",
};
const ontologyPackage = {
  package_id: "ontology.demo", version: "1.0.0", status: "confirmed",
  scenario: { owner: "actor.owner" },
  actors: [], processes: [], sources: [{ id: "source.requirements", title: "Requirements" }],
  decisions: [], entities: [], properties: [], relationships: [relationship], dimensions: [],
  rules: [], metrics: [], data_sources: [], bindings: [], joins: [], analysis_patterns: [], policies: [], questions: [],
} as unknown as StudioWorkbench["package"];

afterEach(cleanup);

describe("PackageContractEditor", () => {
  it("submits one closed collection-specific UPSERT operation", () => {
    const onSubmit = vi.fn();
    render(<PackageContractEditor ontologyPackage={ontologyPackage} busy={false} error={null} onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Contract collection"), { target: { value: "relationships" } });
    fireEvent.change(screen.getByLabelText("Contract object"), { target: { value: relationship.id } });
    const edited = { ...relationship, predicate: "tradesOn" };
    fireEvent.change(screen.getByLabelText("Typed contract JSON"), { target: { value: JSON.stringify(edited) } });
    fireEvent.click(screen.getByRole("button", { name: "保存 typed contract" }));

    expect(onSubmit).toHaveBeenCalledWith({
      action: "UPSERT", collection: "relationships", object_id: relationship.id, payload: edited,
    });
  });

  it("does not send malformed JSON to the backend", () => {
    const onSubmit = vi.fn();
    render(<PackageContractEditor ontologyPackage={ontologyPackage} busy={false} error={null} onSubmit={onSubmit} onClose={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Typed contract JSON"), { target: { value: "{" } });
    fireEvent.click(screen.getByRole("button", { name: "保存 typed contract" }));
    expect(screen.getByRole("alert").textContent).toContain("JSON");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
