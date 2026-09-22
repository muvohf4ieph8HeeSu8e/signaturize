"""Generate a PRINTING.md describing how to print, fold, and gather an
imposed PDF -- replacing the hand-written HOW-TO-PRINT.md files the
original beatrix-potter scripts produced."""
from __future__ import annotations

from .planner import SignaturePlan


def render_printing_guide(title: str, signature_plan: SignaturePlan, imposed_pdf_name: str) -> str:
    scheme = signature_plan.scheme
    sig_count = signature_plan.signature_count
    total_sheets = signature_plan.total_sheets()
    orientation = "landscape" if scheme.sheet_width_in > scheme.sheet_height_in else "portrait"
    duplex_line = (
        "Double-sided (duplex): **on** -- flip on the long edge (page order below is already "
        "duplex-ready: page 1 is sheet 1's front, page 2 is sheet 1's back, and so on)."
        if scheme.duplex
        else "Single-sided (simplex): print **only the front** pages; the back of each sheet stays blank."
    )

    lines = [
        f"# How to print: {title}",
        "",
        f"File: `{imposed_pdf_name}` "
        f"({total_sheets} sheet(s) across {sig_count} signature(s), "
        f"{signature_plan.content_pages} content page(s)"
        + (f", {signature_plan.padding_pages} blank padding page(s)" if signature_plan.padding_pages else "")
        + ")",
        "",
        "## Print settings",
        "",
        f"- Paper: {scheme.sheet_width_in:g}in x {scheme.sheet_height_in:g}in, {orientation}",
        f"- {duplex_line}",
        "- Do not use \"fit to page\" / \"shrink oversized pages\" -- this should already match "
        "the sheet size exactly at 100%.",
        "",
        "## Assemble",
        "",
    ]

    if scheme.folds == 1:
        lines += [
            f"For each of the {sig_count} signature(s), in order:",
            "",
        ]
        for sig in range(1, sig_count + 1):
            n_sheets = signature_plan.sheets_in_signature(sig)
            lines.append(
                f"{sig}. Signature {sig}: stack its {n_sheets} sheet(s) in order (sheet 1 on top), "
                "fold the whole stack in half down the vertical center, and check the staggered "
                "collation mark on the spine matches this signature's position before moving on."
            )
        lines += [
            "",
            "Gather the folded signatures in order (signature 1 first) and staple or sew along "
            "the common spine fold." if sig_count > 1 else
            "Staple or sew along the spine fold (2-3 staples for a pamphlet).",
        ]
    elif scheme.folds == 0:
        lines += [
            "This scheme uses loose, unfolded single leaves -- no folding.",
            f"Stack the {total_sheets} sheet(s) in order and bind (perfect-bind, side-sew, or "
            "punch/ring-bind) along the marked edge.",
        ]
    else:
        lines.append(f"(folds={scheme.folds} guide text not implemented yet.)")

    lines += [
        "",
        "## Check before committing to a full run",
        "",
        "Print just the first signature's test sheet(s), fold by hand, and confirm the pages "
        "read in the right order and right-side-up before printing the rest -- fold geometry for "
        "anything beyond a single center fold has not been physically verified yet.",
        "",
    ]
    return "\n".join(lines)
