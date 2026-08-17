import { describe, expect, it } from "vitest";

import { summarizeRunMetadata } from "./SettingsPage";

describe("summarizeRunMetadata", () => {
  it("leads with the headline counts", () => {
    expect(
      summarizeRunMetadata({
        generated: 5,
        stored: 5,
        batch_date: "2026-08-16",
      }),
    ).toContain("stored=5, generated=5");
  });

  it("surfaces the reason a batch stored nothing", () => {
    // The exact 2026-08-16 run that read as a hang: the table showed
    // "stored=0, generated=5, batch_date=..." and hid the four dead links.
    const summary = summarizeRunMetadata({
      stored: 0,
      generated: 5,
      batch_date: "2026-08-16",
      skipped_disliked: 0,
      skipped_already_liked: 1,
      skipped_bad_link: [
        { url: "a", reason: "HTTP 404" },
        { url: "b", reason: "HTTP 404" },
        { url: "c", reason: "HTTP 404" },
        { url: "d", reason: "title mismatch" },
      ],
    });
    expect(summary).toContain("skipped_bad_link=4");
    expect(summary).toContain("skipped_already_liked=1");
  });

  it("omits zero skip counters so the non-zero one stands out", () => {
    const summary = summarizeRunMetadata({
      stored: 5,
      generated: 5,
      skipped_disliked: 0,
      skipped_off_allowlist: 0,
      skipped_bad_link: [],
    });
    expect(summary).not.toContain("skipped_disliked");
    expect(summary).not.toContain("skipped_bad_link");
  });

  it("flags a run that fell back to model recall", () => {
    expect(
      summarizeRunMetadata({
        stored: 0,
        generated: 0,
        source_mode: "recall",
        candidate_pool_size: 0,
      }),
    ).toContain("source=recall");
  });

  it("reports the candidate pool size so an empty pool is distinguishable", () => {
    const summary = summarizeRunMetadata({
      stored: 5,
      generated: 5,
      source_mode: "candidates",
      candidate_pool_size: 200,
    });
    expect(summary).toContain("pool=200");
    expect(summary).not.toContain("source=recall");
  });

  it("falls back to the first few keys for pipelines with no known shape", () => {
    expect(summarizeRunMetadata({ topics_extracted: 3, entries_seen: 9 })).toBe(
      "topics_extracted=3, entries_seen=9",
    );
  });

  it("renders nothing for a run with no metadata", () => {
    expect(summarizeRunMetadata(null)).toBe("");
    expect(summarizeRunMetadata(undefined)).toBe("");
  });
});
