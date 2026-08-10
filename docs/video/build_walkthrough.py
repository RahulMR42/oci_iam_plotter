#!/usr/bin/env python3
"""Render a caption-led OCI IAM Plotter product-tour video.

Requires Pillow and FFmpeg. The result is deliberately free of credentials,
tenant data, and screenshots from protected workspaces.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"
W, H = 1920, 1080
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
FONT_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

SLIDES = [
    (
        "OCI IAM Plotter",
        "A guided tour of read-only IAM collection, investigation, reporting, and collaboration.",
        "Welcome to OCI IAM Plotter. This walkthrough follows a typical security and audit journey: collect a tenancy snapshot, investigate identities and policy relationships, compare change, export evidence, and ask focused questions.",
    ),
    (
        "1. Start in a protected workspace",
        "Sign in, choose the tenancy, and begin from its newest retained snapshot.",
        "After sign in, the workspace opens with a professional Redwood-inspired interface. Choose the tenancy you want to review. Each tenancy keeps its own history, and the newest snapshot is selected by default, keeping separate environments safely isolated.",
    ),
    (
        "2. Collect a read-only snapshot",
        "Collect  •  API-signing or security-token authentication  •  no write operations",
        "Use the compact Collect action when you need current evidence. Paste the OCI config and select API-signing authentication with its private key, or security-token authentication with the token and its matching signing key. Credentials are deleted when collection ends, and successful snapshots are archived to Object Storage.",
    ),
    (
        "3. Review collection coverage",
        "Tenancy metadata  •  compartments  •  users  •  groups  •  policies  •  domains  •  dynamic groups",
        "The collector gathers classic IAM and Identity Domains data through read-only OCI APIs. It includes compartments and subcompartments, users, groups and memberships, policies and statements, dynamic group rules, domains, applications and grants where access allows. Any inaccessible optional source is shown as a collection warning rather than hidden.",
    ),
    (
        "4. Access Map with multiple subjects",
        "Searchable multi-select lists for entries, categories, and matching subjects.",
        "Open Access Map to select one or more users, groups, policies, domains, or other subjects. Type to search each multi-select list, then choose evidence categories and matching subjects. The default depth is one hop for a fast focused answer, while deeper analysis remains available when needed.",
    ),
    (
        "5. Read the connection map",
        "Evidence clusters  •  hierarchy  •  expandable tree  •  pan and zoom",
        "The map is built for evidence, not decoration. Solid links show direct or parsed relationships. Dashed links indicate cautious rule-derived possibilities. Switch between clustered, hierarchical, and expandable tree views. Drag the canvas, zoom in or out, fit the view, and click tree branches to collapse or expand connected detail.",
    ),
    (
        "6. Maximize and export the map",
        "Open map alone in a new tab  •  download PNG, PDF, or JSON evidence.",
        "For a larger investigation, choose Maximize map. The new tab contains the map alone rather than the full application, so it works well in a review meeting. Export the current filtered view as an image or PDF for presentation, or JSON for downstream evidence handling.",
    ),
    (
        "7. Inventory and active users",
        "Click a metric to apply a filter  •  remove filters  •  export filtered results to Excel.",
        "Use Inventory for a structured view of collected entities. The overview includes an active-user count. Click a count to turn it into a filter, refine it, or remove it when finished. Every applicable inventory and filtered report can be downloaded as a formatted Excel workbook for audit or operational follow-up.",
    ),
    (
        "8. Analyze users and policies",
        "Groups, parsed policy statements, inferred permissions, ambiguity, confidence, and limitations.",
        "Select one or multiple users to see their group memberships and the policy statements associated with those groups. OCI IAM Plotter makes the evidence explicit: parsed statements, inferred permissions, ambiguity, confidence, and limitations stay visible. It is an audit aid, not a claim of runtime authorization.",
    ),
    (
        "9. Detect duplicate candidates",
        "Name and similarity score  •  View details  •  OCIDs, statements, and supporting evidence.",
        "The Duplicates view finds candidates with exact names, normalized policy text, or cautious near-name similarity. The table shows the name and similarity. Select the view icon to inspect OCIDs, policy statements, and the evidence behind the candidate. Findings are never merged or deleted by the application.",
    ),
    (
        "10. Compare IAM drift",
        "Compare two saved snapshots from the same tenancy and export change evidence.",
        "IAM drift compares two saved collections without querying OCI again. Select two snapshots from the same tenancy to identify added, removed, and changed entities, relationships, memberships, and policy statements. Export the full review so change evidence can be shared with control owners.",
    ),
    (
        "11. Produce audit-ready reports",
        "Inventory or multi-user comparison  •  Markdown, PDF, JSON, CSV, and Excel  •  OCI GenAI summaries.",
        "The Reports workspace accepts no users for an inventory report, or multiple users for an access comparison. Download in Markdown, PDF, JSON, CSV, or formatted multi-sheet Excel. OCI Generative AI summaries are enabled by default for selected users and safely fall back to deterministic local summaries if the model is unavailable.",
    ),
    (
        "12. Review collection logs",
        "Collection progress, coverage, warnings, and failures are visible in one place.",
        "Open Collection logs to review each collection run. Logs provide a transparent record of progress, completed sources, coverage warnings, and failures. This makes it easier to distinguish an incomplete data source from an application issue and to plan a targeted recollection.",
    ),
    (
        "13. Ask IAM",
        "Multi-turn assistant at the bottom right  •  retrieved evidence shown with every answer.",
        "Ask IAM is the multi-turn chat window in the lower right. Ask focused questions about identities, memberships, policies, relationships, duplicates, or changes. It retrieves relevant cached evidence first, then uses OCI Generative AI for a concise narrative when configured. Each answer keeps its evidence available for verification.",
    ),
    (
        "A complete, evidence-first IAM journey",
        "Collect → select tenancy → investigate → compare → export → collaborate.",
        "That is the OCI IAM Plotter journey. Use read-only collection for trustworthy snapshots, follow relationships in focused maps, review change and duplicate candidates, export the exact filtered evidence you need, and use Ask IAM to accelerate informed conversations.",
    ),
]


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def wrapped(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, width: int, face: ImageFont.FreeTypeFont, fill: str, leading: int) -> int:
    words, lines, line = text.split(), [], ""
    for word in words:
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=face) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    for item in lines:
        draw.text((x, y), item, font=face, fill=fill)
        y += leading
    return y


def render_card(index: int, title: str, subtitle: str, narration: str) -> Path:
    image = Image.new("RGB", (W, H), "#15110f")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, W, 18), fill="#d94b35")
    draw.ellipse((1370, 120, 1890, 640), fill="#35231f")
    draw.ellipse((1510, 260, 1770, 520), fill="#d94b35")
    draw.rounded_rectangle((115, 135, 255, 195), radius=30, fill="#d94b35")
    draw.text((146, 148), "OCI", font=font(FONT_BOLD, 30), fill="#ffffff")
    draw.text((115, 260), title, font=font(FONT_BOLD, 72), fill="#fff8f3")
    wrapped(draw, subtitle, 122, 405, 1080, font(FONT, 38), "#ead9d2", 58)
    draw.line((122, 620, 1110, 620), fill="#6e4940", width=2)
    draw.text((122, 665), "What this means for the user", font=font(FONT_BOLD, 28), fill="#d94b35")
    wrapped(draw, narration, 122, 715, 1040, font(FONT, 29), "#f1e4de", 42)
    draw.text((122, 955), f"{index:02d} / {len(SLIDES):02d}", font=font(FONT_BOLD, 27), fill="#d94b35")
    target = OUT / f"slide-{index:02d}.png"
    image.save(target)
    return target


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cards: list[tuple[Path, float]] = []
    script = ["# OCI IAM Plotter walkthrough narration", ""]
    for index, (title, subtitle, narration) in enumerate(SLIDES, 1):
        card = render_card(index, title, subtitle, narration)
        cards.append((card, max(14.0, min(30.0, len(narration.split()) / 2.35 + 3.0))))
        script.extend([f"## {index}. {title}", narration, ""])
    concat = OUT / "concat.txt"
    lines = []
    for card, duration in cards:
        lines.extend((f"file '{card.name}'", f"duration {duration:.2f}"))
    lines.append(f"file '{cards[-1][0].name}'")
    concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-f", "lavfi", "-i", "anullsrc=channel_layout=stereo:sample_rate=48000", "-c:v", "libx264", "-tune", "stillimage", "-pix_fmt", "yuv420p", "-r", "12", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(ROOT / "oci-iam-plotter-user-journey.mp4"))
    (ROOT / "narration.md").write_text("\n".join(script), encoding="utf-8")


if __name__ == "__main__":
    main()
