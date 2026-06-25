"""
HUMAN LAYER: the review screen.

Run:  streamlit run app.py
The agent owns the review; the human gates the payment (Approve / Reject on flags).
"""
import os
import tempfile
import streamlit as st
import fitz
from extract import extract_invoice
from validate import load_context, run_checks, CHECK_LABELS
from decide import decide
import audit
import config

# Formal palette — navy primary, teal accent, semantic status colors
PALETTE = {
    "primary": "#1B2A4A",
    "primary_light": "#2D4A7A",
    "accent": "#0D9488",
    "accent_soft": "#CCFBF1",
    "surface": "#F8FAFC",
    "border": "#E2E8F0",
    "text": "#1E293B",
    "muted": "#64748B",
    "success": "#059669",
    "success_bg": "#ECFDF5",
    "warning": "#D97706",
    "warning_bg": "#FFFBEB",
    "error": "#DC2626",
    "error_bg": "#FEF2F2",
    "skip": "#94A3B8",
    "skip_bg": "#F1F5F9",
    "stage_extract": "#2563EB",
    "stage_validate": "#059669",
    "stage_decide": "#D97706",
    "stage_human": "#7C3AED",
}

st.set_page_config(
    page_title="Verity - AP Agent",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="collapsed",
)
ctx = load_context(config.CONTEXT_DIR)

BANNER = {
    "AUTO-CLEAR": ("Auto-cleared", "success", PALETTE["success"]),
    "FLAG": ("Flagged for review", "error", PALETTE["error"]),
    "ESCALATE": ("Escalated — low read confidence", "warning", PALETTE["warning"]),
}

STAGE_META = {
    "extract": ("📄", "Extract", "Agent reads invoice fields"),
    "validate": ("🔍", "Validate", "Business rules and fraud checks"),
    "decide": ("⚖️", "Decide", "Auto-clear, flag, or escalate"),
    "human": ("👤", "Human review", "Payment gate decision"),
}


def _inject_theme():
    p = PALETTE
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;1,9..40,400&display=swap');
        html, body, [class*="css"] {{
            font-family: 'DM Sans', sans-serif;
            color: {p['text']};
        }}
        .block-container {{
            padding-top: 2rem;
            max-width: 960px;
        }}
        .verity-hero {{
            text-align: center;
            padding: 1.5rem 1rem 2rem;
            margin-bottom: 1.5rem;
            background: linear-gradient(135deg, {p['primary']} 0%, {p['primary_light']} 100%);
            border-radius: 16px;
            color: white;
            box-shadow: 0 4px 24px rgba(27, 42, 74, 0.18);
        }}
        .verity-hero h1 {{
            font-size: 3.25rem;
            font-weight: 700;
            letter-spacing: -0.03em;
            margin: 0 0 0.35rem 0;
            line-height: 1.1;
        }}
        .verity-hero p {{
            font-size: 1.05rem;
            opacity: 0.88;
            margin: 0;
            font-weight: 400;
        }}
        .verity-section {{
            font-size: 1.05rem;
            font-weight: 600;
            color: {p['primary']};
            margin: 1.75rem 0 0.75rem 0;
            padding-bottom: 0.35rem;
            border-bottom: 2px solid {p['accent']};
        }}
        .verity-card {{
            background: white;
            border: 1px solid {p['border']};
            border-radius: 12px;
            padding: 1rem 1.15rem;
            margin-bottom: 0.65rem;
        }}
        .check-row {{
            display: flex;
            align-items: flex-start;
            gap: 0.65rem;
            padding: 0.55rem 0.75rem;
            border-radius: 8px;
            margin-bottom: 0.4rem;
            font-size: 0.92rem;
        }}
        .check-pass {{ background: {p['success_bg']}; border-left: 3px solid {p['success']}; }}
        .check-fail {{ background: {p['error_bg']}; border-left: 3px solid {p['error']}; }}
        .check-skip {{ background: {p['skip_bg']}; border-left: 3px solid {p['skip']}; }}
        .check-badge {{
            font-weight: 600;
            font-size: 0.78rem;
            padding: 0.15rem 0.5rem;
            border-radius: 4px;
            white-space: nowrap;
            flex-shrink: 0;
        }}
        .badge-pass {{ background: {p['success']}; color: white; }}
        .badge-fail {{ background: {p['error']}; color: white; }}
        .badge-skip {{ background: {p['skip']}; color: white; }}
        .check-label {{ font-weight: 600; color: {p['text']}; }}
        .check-detail {{ color: {p['muted']}; font-size: 0.85rem; margin-top: 0.15rem; }}
        .fraud-tag {{
            display: inline-block;
            background: {p['error']};
            color: white;
            font-size: 0.7rem;
            font-weight: 600;
            padding: 0.1rem 0.4rem;
            border-radius: 3px;
            margin-left: 0.35rem;
        }}
        div[data-testid="stMetric"] {{
            background: {p['surface']};
            border: 1px solid {p['border']};
            border-radius: 10px;
            padding: 0.75rem 1rem;
        }}
        div[data-testid="stFileUploader"] {{
            background: {p['surface']};
            border: 1px dashed {p['border']};
            border-radius: 12px;
            padding: 0.5rem;
        }}
        .stButton > button[kind="primary"] {{
            background: {p['accent']} !important;
            border-color: {p['accent']} !important;
            font-weight: 600;
        }}
        .stButton > button[kind="primary"]:hover {{
            background: #0F766E !important;
            border-color: #0F766E !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _pdf_pages(file_bytes, dpi=72, max_pages=None):
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc):
        if max_pages is not None and i >= max_pages:
            break
        pix = page.get_pixmap(dpi=dpi)
        pages.append(pix.tobytes("png"))
    doc.close()
    return pages


def _is_pdf(filename):
    return os.path.splitext(filename)[1].lower() == ".pdf"


def _thumbnail_bytes(file_bytes, filename):
    if _is_pdf(filename):
        pages = _pdf_pages(file_bytes, dpi=48, max_pages=1)
        return pages[0] if pages else None
    return file_bytes


def _render_invoice_thumbnail(file_bytes, filename, width=120):
    thumb = _thumbnail_bytes(file_bytes, filename)
    if thumb is None:
        st.caption("Could not render preview")
        return

    col_thumb, col_action = st.columns([2, 1])
    with col_thumb:
        st.image(thumb, width=width, caption=os.path.basename(filename))
    with col_action:
        with st.popover("Preview", use_container_width=True):
            if _is_pdf(filename):
                for page_img in _pdf_pages(file_bytes, dpi=120):
                    st.image(page_img, use_container_width=True)
            else:
                st.image(file_bytes, use_container_width=True)


def _format_ts(ts):
    return ts.replace("T", " ").rstrip("Z")[:19] + " UTC"


def _legacy_check_label(check_id):
    return CHECK_LABELS.get(check_id, check_id.replace("_", " ").title() + " Check")


def _normalize_validate_payload(payload):
    """Support new full reports and older failure-only audit entries."""
    if not payload:
        return None
    if isinstance(payload, list) and payload and "label" in payload[0]:
        return payload
    if isinstance(payload, list):
        normalized = []
        for item in payload:
            check_id = item.get("check", "unknown")
            normalized.append({
                "check": check_id,
                "label": _legacy_check_label(check_id),
                "passed": not item.get("failed", True),
                "fraud": item.get("fraud", False),
                "reason": item.get("reason", ""),
                "skipped": False,
            })
        return normalized
    return None


def _render_validation_checks(checks):
    for c in checks:
        label = c.get("label", _legacy_check_label(c.get("check", "")))
        reason = c.get("reason", "")
        fraud = c.get("fraud", False)

        if c.get("skipped"):
            badge, row_cls, badge_cls = "Skipped", "check-skip", "badge-skip"
            status_text = reason
        elif c.get("passed"):
            badge, row_cls, badge_cls = "Passed", "check-pass", "badge-pass"
            status_text = reason or "Check passed"
        else:
            badge, row_cls, badge_cls = "Failed", "check-fail", "badge-fail"
            status_text = reason

        fraud_html = '<span class="fraud-tag">FRAUD</span>' if fraud and not c.get("passed") else ""
        st.markdown(
            f"""
            <div class="check-row {row_cls}">
                <span class="check-badge {badge_cls}">{badge}</span>
                <div>
                    <div class="check-label">{label}{fraud_html}</div>
                    <div class="check-detail">{status_text}</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def _render_stage_summary(stage, payload):
    if stage == "extract":
        vendor = payload.get("vendor_name") or "—"
        amount = payload.get("invoice_amount")
        amt_str = f"${amount:,.2f}" if amount is not None else "—"
        st.markdown(f"**{vendor}** · {amt_str}")
        po = payload.get("po_reference") or "none"
        st.caption(f"PO: {po} · Bank …{payload.get('bank_account_last4') or '—'}")
    elif stage == "validate":
        checks = _normalize_validate_payload(payload)
        if checks is None:
            st.success("All checks passed")
        else:
            passed = sum(1 for c in checks if c.get("passed") and not c.get("skipped"))
            failed = sum(1 for c in checks if not c.get("passed") and not c.get("skipped"))
            skipped = sum(1 for c in checks if c.get("skipped"))
            summary = f"{passed} passed"
            if failed:
                summary += f" · {failed} failed"
            if skipped:
                summary += f" · {skipped} skipped"
            st.caption(summary)
            _render_validation_checks(checks)
    elif stage == "decide":
        decision = payload.get("decision", "—")
        conf = payload.get("confidence")
        conf_str = f"{conf:.0%}" if conf is not None else "—"
        fraud = payload.get("fraud_flag", "—")
        st.markdown(f"**{decision}** · confidence {conf_str} · fraud risk: {fraud}")
        for reason in payload.get("reasons") or []:
            st.caption(f"• {reason}")
    elif stage == "human":
        action = payload.get("action", "—")
        if action == "approved":
            st.success(f"Payment **{action}**")
        elif action == "rejected":
            st.warning(f"Payment **{action}**")
        else:
            st.write(action)
    else:
        st.json(payload)


def _render_audit_trail(records):
    if not records:
        st.info("No audit records yet for this invoice.")
        return

    stage_colors = {
        "extract": PALETTE["stage_extract"],
        "validate": PALETTE["stage_validate"],
        "decide": PALETTE["stage_decide"],
        "human": PALETTE["stage_human"],
    }

    for i, rec in enumerate(records):
        stage = rec.get("stage", "unknown")
        icon, title, subtitle = STAGE_META.get(stage, ("•", stage.title(), ""))
        accent = stage_colors.get(stage, PALETTE["accent"])
        expand = stage in ("validate", "decide") and i == len(records) - 1
        if stage == "validate":
            expand = True

        with st.container(border=True):
            head_l, head_r = st.columns([3, 2])
            with head_l:
                st.markdown(
                    f'<span style="color:{accent};font-size:1.15rem;">●</span> '
                    f"**{icon} {title}** · step {i + 1}/{len(records)}",
                    unsafe_allow_html=True,
                )
                st.caption(subtitle)
            with head_r:
                st.caption(_format_ts(rec.get("ts", "")))

            with st.expander("Details", expanded=expand):
                _render_stage_summary(stage, rec.get("payload"))
                st.divider()
                st.json(rec, expanded=False)


def _section(title):
    st.markdown(f'<p class="verity-section">{title}</p>', unsafe_allow_html=True)


_inject_theme()

st.markdown(
    """
    <div class="verity-hero">
        <h1>Verity</h1>
        <p>AI employee for accounts payable — reviews every invoice, escalates only the exceptions.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

if not config.GEMINI_API_KEY:
    st.warning("Set GEMINI_API_KEY in your .env file to run extraction.")

_section("Upload invoice")
uploaded = st.file_uploader(
    "Drag and drop or browse (PDF / PNG / JPG)",
    type=["pdf", "png", "jpg", "jpeg"],
    label_visibility="collapsed",
)

if uploaded is not None:
    st.session_state["verity_invoice"] = {
        "bytes": uploaded.getvalue(),
        "name": uploaded.name,
    }

inv_state = st.session_state.get("verity_invoice")
if inv_state:
    _section("Uploaded invoice")
    _render_invoice_thumbnail(inv_state["bytes"], inv_state["name"])

_, btn_col, _ = st.columns([2, 1, 2])
with btn_col:
    process_clicked = st.button("Process invoice", type="primary", use_container_width=True)

if uploaded and process_clicked:
    suffix = os.path.splitext(uploaded.name)[1]
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(uploaded.getvalue())
        path = tmp.name
    inv_id = os.path.splitext(uploaded.name)[0]

    with st.spinner("Reading and validating..."):
        try:
            ext = extract_invoice(path)
        except Exception as e:
            st.error(str(e))
            st.stop()
        audit.log(inv_id, "extract", ext)
        findings, checks = run_checks(ext, ctx)
        audit.log(inv_id, "validate", checks)
        d = decide(ext, findings)
        audit.log(inv_id, "decide", d.__dict__)

    st.session_state["verity_result"] = {
        "inv_id": inv_id,
        "ext": ext,
        "d": d,
        "checks": checks,
    }

result = st.session_state.get("verity_result")
if result:
    inv_id = result["inv_id"]
    ext = result["ext"]
    d = result["d"]

    label, kind, _color = BANNER[d.decision]
    getattr(st, kind)(f"**{label}** — confidence {d.confidence:.0%} — fraud risk: {d.fraud_flag}")

    _section("What the agent read")
    c1, c2, c3 = st.columns(3)
    c1.metric("Vendor", ext.get("vendor_name") or "—")
    c2.metric("Amount", f"${ext.get('invoice_amount'):,.0f}" if ext.get("invoice_amount") else "—")
    c3.metric("PO reference", ext.get("po_reference") or "—")
    c1, c2 = st.columns(2)
    c1.metric("Invoice date", ext.get("invoice_date") or "—")
    c2.metric("Bank (last 4)", ext.get("bank_account_last4") or "—")

    if d.reasons:
        _section("Decision rationale")
        for r in d.reasons:
            st.markdown(f"- {r}")

    if d.decision in ("FLAG", "ESCALATE"):
        _section("Human decision")
        st.caption("Your approval gates the payment.")
        b1, b2, b3 = st.columns([1, 1, 2])
        if b1.button("Approve payment", use_container_width=True):
            audit.log(inv_id, "human", {"action": "approved"})
            st.success("Approved and logged.")
            st.rerun()
        if b2.button("Reject", use_container_width=True):
            audit.log(inv_id, "human", {"action": "rejected"})
            st.info("Rejected and logged.")
            st.rerun()

    _section("Audit trail")
    _render_audit_trail(audit.read_latest_run(inv_id))
