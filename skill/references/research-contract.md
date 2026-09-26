# Story and visual evidence

Use this compact record for each selected or rejected story. Only `id` and `title` are needed for pipeline readiness. Other fields are optional notes for asset discovery, dates, and attribution; they are never a claim-accuracy or supporting-evidence gate for Brandon's scripts and reels.

For an optional resource-stack format, one story can describe the shared viewer outcome and ordered collection. Use the fields below when useful. Keep a reference reel's authorship and source distinct from Brandon's own work.

```json
{
  "id": "short-stable-id",
  "title": "Specific event or tool",
  "status": "selected",
  "primary_url": "https://...",
  "event_date": "YYYY-MM-DD",
  "event_basis": "Official dated release entry",
  "publication_date": "YYYY-MM-DD",
  "retrieved_at": "ISO UTC timestamp",
  "freshness": "in_window",
  "claims": [{"claim": "Paraphrased supported fact", "source_url": "https://...", "evidence": "Brief support/location", "qualification": "Limits that change the claim"}],
  "visuals": [{"url": "https://...", "source_url": "https://...", "kind": "demo", "status": "linked_not_captured", "capture_note": "What the editor should show"}],
  "angle": "Viewer problem and visible payoff",
  "keyword": "WORD",
  "resource": "assets/WORD.md",
  "test_status": "source_verified_not_run",
  "decision_reason": "Why this is a reel or why rejected"
}
```

When dates are used in an asset record, distinguish the event, publication, retrieval and repository activity dates. Do not convert a push date into an announcement date. This metadata is for accurate attribution and selection of visuals, not a precondition for the script or edit.

Capture visual provenance: the real source page, exact image/demo link, what it shows, whether opened or captured, and any known usage terms. Repository code licensing does not automatically license every logo, screenshot, or third-party demo. Do not call a link a downloaded asset or call a recreated graphic an original screenshot. Use source material as filming references; resolve reuse rights for the intended publication if needed.

Preserve request failures and rejected stories. Silence is not evidence that a source had zero results. Keep source excerpts short, quote sparingly, and paraphrase facts in the scripts.

For filmed reels, Brandon's recorded account is the script input. Do not maintain a required claim map, ask for corroboration, or block an edit when the supplied captures do not show a step. Authored purchase confirmation or sent-email screens may communicate his stated account; retain the design source in production notes and animate the screens. Do not add disclaimer, proof-status or production-caveat text to the rendered video. Keep actual distribution and delivery status distinct in operational records.
