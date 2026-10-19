import datetime as dt
import re
from io import StringIO

import pandas as pd
import streamlit as st

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

st.set_page_config(
    page_title="Australian Business Acquisition Monitor",
    page_icon="🏢",
    layout="wide",
)

st.title("🇦🇺 Australian Business Acquisition Monitor")
st.caption(
    "Document-assisted preliminary screening. Extracted values are suggestions only; "
    "they are not verified financial claims or investment advice."
)

st.warning(
    "Privacy note: this version does not write deal records to SQLite or another application database. "
    "Uploaded files are processed during the session, but your hosting provider may still retain technical logs. "
    "Only upload documents you are authorised to use."
)


def extract_text(uploaded_file) -> str:
    """Extract text from a PDF or text file, returning an empty string on failure."""
    name = uploaded_file.name.lower()
    try:
        if name.endswith(".pdf"):
            if PdfReader is None:
                st.error("PDF support is unavailable. Install pypdf using: pip install pypdf")
                return ""
            reader = PdfReader(uploaded_file)
            if reader.is_encrypted:
                try:
                    result = reader.decrypt("")
                    if not result:
                        st.warning(f"'{uploaded_file.name}' is password-protected; text could not be read.")
                        return ""
                except Exception:
                    st.warning(f"'{uploaded_file.name}' is encrypted; text could not be read.")
                    return ""
            pages = []
            for page in reader.pages:
                pages.append(page.extract_text() or "")
            return "\n".join(pages)
        return uploaded_file.getvalue().decode("utf-8", errors="replace")
    except Exception as exc:
        st.error(f"Could not read '{uploaded_file.name}': {exc}")
        return ""


def trend_and_risk(text: str):
    lower = text.lower()
    positive = ["growth", "expanding", "record revenue", "upward", "scalable", "surplus"]
    negative = ["decline", "contraction", "headwinds", "stagnant", "fatality", "disruption", "loss"]
    positive_count = sum(lower.count(word) for word in positive)
    negative_count = sum(lower.count(word) for word in negative)
    if positive_count > negative_count:
        trend = "Positive keywords found (heuristic only)"
    elif negative_count > positive_count:
        trend = "Negative keywords found (heuristic only)"
    else:
        trend = "No clear keyword direction"

    risk_terms = ["key person", "litigation", "dispute", "investigation", "concentration", "regulatory", "fatality"]
    found = [term for term in risk_terms if term in lower]
    risk = ", ".join(found) if found else "No configured risk keywords found"
    return trend, risk


def candidate_numbers(text: str):
    """Return candidate numbers next to financial labels; never silently treats them as verified."""
    candidates = []
    patterns = [
        ("EBITDA", r"(?:underlying\s+)?ebitda\s*[:=\-]?\s*(?:AUD\s*)?\$?\s*([\d,]+(?:\.\d+)?)\s*(million|m|billion|bn|thousand|k)?"),
        ("Net profit", r"net\s+profit\s*[:=\-]?\s*(?:AUD\s*)?\$?\s*([\d,]+(?:\.\d+)?)\s*(million|m|billion|bn|thousand|k)?"),
        ("Share price", r"(?:share\s+price|closing\s+price|close)\s*[:=\-]?\s*(?:AUD\s*)?\$?\s*([\d,]+(?:\.\d+)?)"),
        ("Shares outstanding", r"(?:shares\s+outstanding|ordinary\s+shares|number\s+of\s+shares)\s*[:=\-]?\s*([\d,]+(?:\.\d+)?)\s*(million|m|billion|bn|thousand|k)?"),
    ]
    multipliers = {"million": 1_000_000, "m": 1_000_000, "billion": 1_000_000_000, "bn": 1_000_000_000, "thousand": 1_000, "k": 1_000}
    for label, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            raw = match.group(1).replace(",", "")
            suffix = (match.group(2) or "").lower() if match.lastindex and match.lastindex >= 2 else ""
            try:
                value = float(raw) * multipliers.get(suffix, 1)
                context_start = max(0, match.start() - 70)
                context_end = min(len(text), match.end() + 70)
                candidates.append({
                    "Metric": label,
                    "Candidate value": value,
                    "Nearby source text": re.sub(r"\s+", " ", text[context_start:context_end]).strip(),
                    "Status": "Unverified — check original document",
                })
            except ValueError:
                continue
    return candidates


st.header("1. Review documents")
uploads = st.file_uploader(
    "Upload business reports (.pdf or .txt)",
    type=["pdf", "txt"],
    accept_multiple_files=True,
)

all_candidates = []
if uploads:
    for uploaded in uploads:
        with st.expander(f"Document: {uploaded.name}", expanded=False):
            raw_text = extract_text(uploaded)
            if not raw_text.strip():
                st.info("No readable text was extracted. Scanned PDFs may require OCR, which this app does not perform.")
                continue
            st.write(f"Extracted {len(raw_text):,} characters.")
            trend, risks = trend_and_risk(raw_text)
            st.write(f"**Keyword trend indicator:** {trend}")
            st.write(f"**Risk keywords detected:** {risks}")
            st.caption("These keyword indicators are not a substitute for reading the full document or conducting due diligence.")
            found = candidate_numbers(raw_text)
            for row in found:
                row["Source file"] = uploaded.name
            all_candidates.extend(found)
            with st.expander("View extracted text (may contain confidential information)"):
                st.text_area("Extracted text", raw_text, height=240, key=f"text_{uploaded.name}")

if all_candidates:
    st.subheader("Candidate financial figures — not verified")
    candidates_df = pd.DataFrame(all_candidates)
    st.dataframe(candidates_df, use_container_width=True, hide_index=True)
    st.caption("The parser may miss values or associate a number with the wrong period, currency, or financial metric. Verify each value against the original document.")
    csv_bytes = candidates_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download extracted candidates (CSV)",
        data=csv_bytes,
        file_name=f"financial_candidates_{dt.date.today().isoformat()}.csv",
        mime="text/csv",
    )

st.divider()
st.header("2. Optional manual valuation scenario")
st.info(
    "Enter values only after checking their source. This calculator produces an illustrative enterprise/equity value scenario; "
    "it does not determine a fair price or verify that a business is for sale."
)

with st.form("valuation_form"):
    col1, col2 = st.columns(2)
    with col1:
        company_name = st.text_input("Company / target name", placeholder="Enter a name or internal reference")
        ebitda = st.number_input("EBITDA (AUD)", min_value=0.0, value=0.0, step=10000.0, format="%.2f")
        ev_ebitda_multiple = st.number_input("Assumed EV / EBITDA multiple", min_value=0.0, value=0.0, step=0.5, format="%.2f")
    with col2:
        net_debt = st.number_input("Net debt (AUD; debt minus cash)", value=0.0, step=10000.0, format="%.2f", help="Enter a sourced value. Positive net debt reduces equity value; net cash can be entered as a negative number.")
        shares = st.number_input("Shares outstanding (optional, for listed-company analysis)", min_value=0.0, value=0.0, step=100000.0, format="%.0f")
        evidence_checked = st.checkbox("I have checked these inputs against source evidence")
    submitted = st.form_submit_button("Calculate illustrative scenario")

if submitted:
    if not company_name.strip():
        st.error("Enter a company name or internal reference.")
    elif ebitda <= 0 or ev_ebitda_multiple <= 0:
        st.error("Enter a positive EBITDA and a positive assumed EV / EBITDA multiple. No default financial figures are supplied.")
    elif not evidence_checked:
        st.error("Check the source evidence before calculating. The calculator will not proceed until you confirm that the inputs have been reviewed.")
    else:
        enterprise_value = ebitda * ev_ebitda_multiple
        equity_value = enterprise_value - net_debt
        st.subheader(f"Illustrative scenario: {company_name.strip()}")
        a, b = st.columns(2)
        a.metric("Illustrative enterprise value", f"A${enterprise_value:,.0f}")
        b.metric("Illustrative equity value", f"A${equity_value:,.0f}")
        st.write(f"**Assumed EV / EBITDA multiple:** {ev_ebitda_multiple:.2f}x")
        st.write(f"**Net debt input:** A${net_debt:,.0f}")
        if shares > 0:
            st.metric("Illustrative equity value per share", f"A${equity_value / shares:,.4f}")
        else:
            st.caption("Per-share value not calculated because shares outstanding were not supplied.")
        st.warning("This is a scenario calculation, not a verified valuation. It excludes other adjustments and requires professional review of earnings quality, working capital, debt-like items, taxes, transaction structure, and comparable-company assumptions.")

st.divider()
st.caption("No listings or financial claims are independently verified by this app. Public discovery, if added, should display unverified results separately and preserve source URLs and timestamps.")
