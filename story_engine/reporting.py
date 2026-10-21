"""Portable inspection artifacts; all model/user strings are escaped in HTML."""

import html
import json
from pathlib import Path

from .config import DIMENSIONS, MODEL, THRESHOLDS


def escape(value):
    return html.escape(str(value), quote=True)


def arousal_svg(values):
    points = " ".join(
        f"{30 + i * 480 / max(1, len(values) - 1):.1f},{140 - v * 23}" for i, v in enumerate(values)
    )
    return (
        f'<svg viewBox="0 0 540 160" role="img" aria-label="Subjective arousal by paragraph">'
        '<path d="M30 15V135H520" fill="none" stroke="#64748b"/>'
        f'<polyline points="{points}" fill="none" stroke="#31b4a0" stroke-width="3"/>'
        '<text x="30" y="155" fill="#64748b" font-size="11">Paragraph order →</text></svg>'
    )


def write_inspector(result, path: Path):
    cards = []
    for draft in result.drafts:
        a = draft.assessment
        rows = "".join(
            f"<tr><td>{escape(k.replace('_', ' '))}</td><td>{getattr(a.quality, k).score}/5"
            f" (target {THRESHOLDS[k]})</td><td>{escape(getattr(a.quality, k).evidence.observation)}"
            f"<blockquote>{escape(getattr(a.quality, k).evidence.quote)}</blockquote></td></tr>"
            for k in DIMENSIONS
        )
        story = "".join(
            f"<p><small>{i + 1}</small> {escape(p)}</p>"
            for i, p in enumerate(draft.story.paragraphs)
        )
        craft = (
            "<details><summary>Resolution, specificity, and connected details</summary>"
            f"<pre>{escape(a.quality.craft.model_dump_json(indent=2))}</pre></details>"
            if a.quality.craft
            else ""
        )
        cards.append(
            f"<section><h2>Draft {draft.version} · {escape(draft.decision)}</h2>"
            f"<p>Safety review: {'pass' if a.safety.safe else 'fail'} · "
            f"{a.metrics.word_count} words · estimated FK grade {a.metrics.estimated_fk_grade}</p>"
            f"<p>{escape(a.safety.reason or '')}</p>"
            f"<p>{escape('; '.join(a.metrics.failures + a.safety.concerns + a.metrics.warnings))}</p>"
            f"<details><summary>Story text</summary><h3>{escape(draft.story.title)}</h3>{story}</details>"
            f"<table><tr><th>Dimension</th><th>Rating</th><th>Evidence</th></tr>{rows}</table>"
            f"{craft}"
            "<p>Editorial arousal estimate (1–5); not a sleep measurement.</p>"
            f"{arousal_svg(a.quality.arousal_by_paragraph) if a.quality.arousal_by_paragraph else '<p>Arousal chart unavailable.</p>'}</section>"
        )
    data = escape(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))
    path.write_text(
        f"""<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Story inspection · {escape(result.run_id)}</title>
<style>
body{{font:16px/1.65 system-ui,sans-serif;background:#f3f4f6;color:#17252d;margin:0}}
main{{max-width:1000px;margin:auto;padding:40px 24px}}h1{{font-size:36px;line-height:1.2}}
section{{background:white;padding:24px;border:1px solid #dbe3e8;border-radius:14px;margin:20px 0}}
table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;padding:12px;border-bottom:1px solid #e2e8f0;vertical-align:top}}
blockquote{{margin:8px 0;color:#526574;font-style:italic}}small{{color:#8192a0}}svg{{max-width:540px;width:100%}}
summary{{cursor:pointer;font-weight:600}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}}
.badge{{display:inline-block;background:#dceee9;padding:4px 12px;border-radius:20px}}
</style><main><span class="badge">{escape(result.provenance.upper())} · {MODEL}</span>
<h1>The story, and how it was reviewed.</h1>
<p>Status: <b>{escape(result.status)}</b> · selected draft: {escape(result.selected_version)}<br>
Stop reason: {escape(result.stop_reason)}</p>
<p>{escape(" ".join(result.warnings))}</p>
<p>{escape(result.brief.parent_note if result.brief else "")}</p>
<section><h2>Usage</h2><pre>{escape(json.dumps(result.usage, indent=2))}</pre></section>
{"".join(cards)}<details><summary>Complete structured run</summary><pre>{data}</pre></details>
<p>Passing these checks does not certify child safety. Synthetic examples demonstrate software behavior only.</p>
</main></html>""",
        encoding="utf-8",
    )


def save_run(result, recorder, output: Path) -> Path:
    folder = output / result.run_id
    folder.mkdir(parents=True, exist_ok=False)
    (folder / "run.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    recorder.save(folder / "trace.jsonl")
    write_inspector(result, folder / "inspect.html")
    chosen = result.selected()
    if chosen:
        (folder / "story.txt").write_text(
            chosen.story.title + "\n\n" + chosen.story.body(), encoding="utf-8"
        )
    return folder
