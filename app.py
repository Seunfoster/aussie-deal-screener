import os
import re
import hashlib
import datetime as dt
import xml.etree.ElementTree as ET
from urllib.parse import urlencode, urlparse

import pandas as pd
import requests
import streamlit as st

st.set_page_config(
    page_title="Australian Business Acquisition Monitor",
    page_icon="🏢",
    layout="wide",
)

TIMEOUT = 15
RSS_LIMIT = 50
USER_AGENT = "AustralianBusinessAcquisitionMonitor/2.0"
STATES = {
    "VIC": "Victoria", "NSW": "New South Wales", "QLD": "Queensland",
    "WA": "Western Australia", "SA": "South Australia", "TAS": "Tasmania",
    "NT": "Northern Territory", "ACT": "Australian Capital Territory",
}

st.title("🇦🇺 Australian Business Acquisition Monitor")
st.write(
    "Discover potential acquisition leads, inspect source evidence, and apply "
    "a transparent preliminary screen. This tool does not recommend that you buy "
    "a business or independently verify seller claims."
)
st.warning(
    "Important: search results are leads, not proof that a business is currently for sale. "
    "A listing is not investment-ready until sale status, price, earnings, and supporting "
    "documents have been checked. Never treat a score as a substitute for due diligence."
)

def parse_number(value):
    """Parse a non-negative number; return None if missing or ambiguous."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    cleaned = re.sub(r"[$,\s]", "", str(value).strip())
    if not cleaned or cleaned.lower() in {"n/a", "na", "not disclosed", "unknown", "-"}:
        return None
    try:
        number = float(cleaned)
        return number if number >= 0 else None
    except ValueError:
        return None

def infer_state(text):
    text = (text or "").lower()
    patterns = [
        ("VIC", r"\b(victoria|vic|melbourne|geelong)\b"),
        ("NSW", r"\b(new south wales|nsw|sydney)\b"),
        ("QLD", r"\b(queensland|qld|brisbane|gold coast|townsville)\b"),
        ("WA", r"\b(western australia|wa|perth)\b"),
        ("SA", r"\b(south australia|sa|adelaide)\b"),
        ("TAS", r"\b(tasmania|tas|hobart)\b"),
        ("NT", r"\b(northern territory|nt|darwin)\b"),
        ("ACT", r"\b(australian capital territory|act|canberra)\b"),
    ]
    for code, pattern in patterns:
        if re.search(pattern, text):
            return code
    return None

def normalise_url(url):
    if not url:
        return None
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in ("https", "http") or not parsed.netloc:
            return None
        return url.strip().split("#")[0]
    except Exception:
        return None

def make_lead(title, url, source, published_at=None, state=None, suburb=None,
              postcode=None, industry=None, asking_price=None, reported_ebitda=None,
              sale_status="Unverified", listing_evidence="Not checked",
              financial_evidence="Not checked", notes=""):
    clean_url = normalise_url(url)
    if not title or not clean_url:
        return None
    state = state if state in STATES else infer_state(f"{title} {suburb or ''} {postcode or ''}")
    postcode_match = re.search(r"\b(\d{4})\b", str(postcode or ""))
    price = parse_number(asking_price)
    ebitda = parse_number(reported_ebitda)
    key = hashlib.sha256(clean_url.encode("utf-8")).hexdigest()
    return {
        "lead_key": key,
        "title": str(title).strip(),
        "url": clean_url,
        "source": source or urlparse(clean_url).netloc,
        "state": state or "Unknown",
        "suburb": (suburb or "").strip(),
        "postcode": postcode_match.group(1) if postcode_match else "",
        "industry": (industry or "").strip(),
        "asking_price": price,
        "reported_ebitda": ebitda,
        "published_at": published_at or "",
        "sale_status": sale_status,
        "listing_evidence": listing_evidence,
        "financial_evidence": financial_evidence,
        "verification_notes": (notes or "").strip(),
        "discovery_type": "Structured listing" if sale_status == "Confirmed active listing" else "Search lead",
    }

def fetch_rss(query):
    """Search-news RSS is used for discovery only, never treated as proof of a listing."""
    endpoint = "https://news.google.com/rss/search?" + urlencode({
        "q": query,
        "hl": "en-AU",
        "gl": "AU",
        "ceid": "AU:en",
    })
    response = requests.get(
        endpoint,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"},
        timeout=TIMEOUT,
    )
    response.raise_for_status()
    root = ET.fromstring(response.content)
    leads = []
    for item in root.findall("./channel/item")[:RSS_LIMIT]:
        title = item.findtext("title", default="").strip()
        url = item.findtext("link", default="").strip()
        published = item.findtext("pubDate", default="")
        source_node = item.find("source")
        source = source_node.text.strip() if source_node is not None and source_node.text else "Google News RSS"
        lead = make_lead(
            title=title,
            url=url,
            source=source,
            published_at=published,
            sale_status="Unverified",
            listing_evidence="Search result only — open original source",
            financial_evidence="No financial evidence extracted",
            notes="Automatically discovered via public news/search RSS. Not confirmed to be an active sale listing.",
        )
        if lead:
            leads.append(lead)
    return leads

def calculate_screen(lead, capital, minimum_ebitda, max_multiple,
                     debt_fraction, interest_rate, loan_term, ebitda_verified):
    price = lead.get("asking_price")
    ebitda = lead.get("reported_ebitda")
    result = {
        "multiple": None, "indicative_dscr": None, "simple_payback_years": None,
        "screen_score": None, "screen_status": "", "screen_reasons": [],
    }

    if lead.get("sale_status") != "Confirmed active listing":
        result["screen_status"] = "Not scoreable — sale status unconfirmed"
        result["screen_reasons"].append("Confirm directly with seller or authorised broker that the business is actively for sale.")
        return result
    if price is None or price <= 0:
        result["screen_status"] = "Not scoreable — asking price missing"
        result["screen_reasons"].append("Obtain a current written asking price or documented price guidance.")
        return result
    if ebitda is None or ebitda <= 0:
        result["screen_status"] = "Not scoreable — earnings missing"
        result["screen_reasons"].append("Obtain earnings evidence; do not infer profit from an advert or headline.")
        return result
    if not ebitda_verified:
        result["screen_status"] = "Indicative only — EBITDA not independently verified"
        result["screen_reasons"].append("EBITDA is entered as seller-advertised or unverified; no investment score is issued.")
        result["multiple"] = round(price / ebitda, 2)
        result["simple_payback_years"] = round(price / ebitda, 2)
        return result

    multiple = price / ebitda
    loan = price * debt_fraction
    months = loan_term * 12
    monthly_rate = interest_rate / 12
    if loan <= 0:
        annual_debt_service = 0
    elif monthly_rate == 0:
        annual_debt_service = loan / loan_term
    else:
        monthly_payment = loan * monthly_rate / (1 - (1 + monthly_rate) ** (-months))
        annual_debt_service = monthly_payment * 12

    # EBITDA is not cash available for debt service. This ratio is only a rough proxy.
    dscr_proxy = ebitda / annual_debt_service if annual_debt_service > 0 else None
    reasons = []
    if price > capital:
        reasons.append("Asking price exceeds configured available capital.")
    if ebitda < minimum_ebitda:
        reasons.append("EBITDA is below the configured minimum.")
    if multiple > max_multiple:
        reasons.append("Price / EBITDA exceeds the configured maximum multiple.")
    if dscr_proxy is None or dscr_proxy < 1.25:
        reasons.append("Indicative EBITDA-to-debt-service proxy is below 1.25x.")

    # Score only ranks configured screening metrics; it is not an investment recommendation.
    valuation_points = max(0, min(60, (max_multiple - multiple) / max_multiple * 60))
    debt_points = max(0, min(40, ((dscr_proxy or 0) - 1) * 20))
    result.update({
        "multiple": round(multiple, 2),
        "indicative_dscr": round(dscr_proxy, 2) if dscr_proxy is not None else None,
        "simple_payback_years": round(price / ebitda, 2),
        "screen_score": round(valuation_points + debt_points, 1),
        "screen_status": "Passes configured preliminary screen" if not reasons else "Fails configured preliminary screen",
        "screen_reasons": reasons or ["Passes the configured numeric rules only; this is not a buy recommendation."],
    })
    return result

with st.sidebar:
    st.header("Investment parameters")
    capital = st.number_input("Available capital (AUD)", min_value=0, value=1_500_000, step=50_000)
    min_ebitda = st.number_input("Minimum annual EBITDA (AUD)", min_value=0, value=150_000, step=10_000)
    max_multiple = st.slider("Maximum price / EBITDA multiple", 1.0, 10.0, 6.0, 0.1)
    st.subheader("Indicative financing")
    debt_fraction = st.slider("Debt funding (%)", 0, 90, 70) / 100
    interest_rate = st.slider("Annual interest rate (%)", 0.0, 20.0, 8.0, 0.25) / 100
    loan_term = st.slider("Loan term (years)", 1, 30, 7)
    st.subheader("Location")
    state_choice = st.selectbox("State or territory", ["All"] + list(STATES.keys()))
    suburb_filter = st.text_input("Suburb / city").strip().lower()
    postcode_filter = st.text_input("Postcode").strip()

st.header("A. Discover potential opportunities")
query = st.text_input("Search phrase", "business for sale Australia")
if st.button("Discover public search leads", type="primary"):
    if not query.strip():
        st.error("Enter a search phrase.")
    else:
        try:
            with st.spinner("Searching public RSS results..."):
                found = fetch_rss(query.strip())
            # Session-only storage: refresh/restart clears the list; no application DB is used.
            st.session_state["leads"] = found
            st.session_state["discovery_message"] = f"Retrieved {len(found)} public search results. None are automatically treated as confirmed listings."
        except Exception as exc:
            st.error(f"Search failed ({type(exc).__name__}). Try again later.")
            st.caption("Technical details are omitted from the page to reduce accidental disclosure of request or server information.")

if st.session_state.get("discovery_message"):
    st.info(st.session_state["discovery_message"])

st.header("B. Add or verify a specific listing")
st.write("Use this form for a real listing found on a broker or marketplace website. Only mark a listing as confirmed after checking the original listing and, ideally, contacting the broker or seller.")
with st.form("manual_listing_form", clear_on_submit=True):
    title = st.text_input("Business / listing title")
    url = st.text_input("Direct URL to the original listing")
    source = st.text_input("Broker / marketplace name")
    c1, c2, c3 = st.columns(3)
    with c1:
        state = st.selectbox("State", ["Unknown"] + list(STATES.keys()))
        suburb = st.text_input("Suburb / city")
        postcode = st.text_input("Postcode")
    with c2:
        industry = st.selectbox("Industry", [
            "", "Transport & Logistics", "Commercial Services", "Manufacturing",
            "Supply Chain & Distribution", "Healthcare", "Hospitality", "Retail",
            "Construction & Trades", "Technology", "Other"
        ])
        asking_price_text = st.text_input("Asking price (AUD; leave blank if unknown)")
        ebitda_text = st.text_input("Advertised annual EBITDA (AUD; leave blank if unknown)")
    with c3:
        sale_status = st.selectbox("Sale status", [
            "Unverified", "Advertised for sale — not independently confirmed",
            "Confirmed active listing"
        ])
        listing_evidence = st.selectbox("Listing evidence checked", [
            "Not checked", "Original page viewed", "Broker/seller contacted",
            "Written confirmation of active sale"
        ])
        financial_evidence = st.selectbox("Financial evidence available", [
            "Not checked", "Advertised figures only", "Management accounts received",
            "Three years of financial statements received",
            "Independent accountant review completed"
        ])
    ebitda_verified = st.checkbox(
        "I have independently reconciled EBITDA against supporting documents",
        value=False,
        help="Only tick this after reviewing appropriate evidence. A seller's advert alone is not independent verification."
    )
    notes = st.text_area("Evidence notes (do not enter personal or confidential information)")
    submitted = st.form_submit_button("Add listing to this session")
    if submitted:
        clean_url = normalise_url(url)
        if not title.strip() or not clean_url:
            st.error("Enter a listing title and a valid http/https URL.")
        else:
            lead = make_lead(
                title=title, url=clean_url, source=source, state=state,
                suburb=suburb, postcode=postcode, industry=industry,
                asking_price=asking_price_text, reported_ebitda=ebitda_text,
                sale_status=sale_status, listing_evidence=listing_evidence,
                financial_evidence=financial_evidence, notes=notes,
            )
            lead["ebitda_verified"] = ebitda_verified
            leads = st.session_state.get("leads", [])
            # Replace duplicate URL in this session rather than create duplicate rows.
            leads = [x for x in leads if x["lead_key"] != lead["lead_key"]]
            leads.append(lead)
            st.session_state["leads"] = leads
            st.success("Listing added to this browser session only. It has not been saved to an application database.")

st.header("C. Screen and review leads")
leads = st.session_state.get("leads", [])
if not leads:
    st.info("No leads in this session yet. Run discovery or add a specific listing above.")
else:
    filtered = []
    for lead in leads:
        if state_choice != "All" and lead.get("state") != state_choice:
            continue
        if postcode_filter and lead.get("postcode") != postcode_filter:
            continue
        if suburb_filter and suburb_filter not in (lead.get("suburb", "") + " " + STATES.get(lead.get("state"), "")).lower():
            continue
        ebitda_verified = bool(lead.get("ebitda_verified", False))
        screening = calculate_screen(
            lead, capital, min_ebitda, max_multiple, debt_fraction,
            interest_rate, loan_term, ebitda_verified
        )
        filtered.append({**lead, **screening})

    if not filtered:
        st.info("No leads match the current filters.")
    else:
        display = pd.DataFrame([{
            "Business / listing": x["title"],
            "Source": x["source"],
            "State": x["state"],
            "Industry": x["industry"] or "Not specified",
            "Asking price (AUD)": x["asking_price"],
            "Advertised EBITDA (AUD)": x["reported_ebitda"],
            "Price / EBITDA": x["multiple"],
            "Indicative DSCR proxy": x["indicative_dscr"],
            "Screen score (not a recommendation)": x["screen_score"],
            "Sale status": x["sale_status"],
            "Screen outcome": x["screen_status"],
            "Original listing": x["url"],
        } for x in filtered])
        st.dataframe(
            display, use_container_width=True, hide_index=True,
            column_config={"Original listing": st.column_config.LinkColumn("Original listing")}
        )
        st.download_button(
            "Download session results as CSV",
            data=display.to_csv(index=False).encode("utf-8"),
            file_name=f"acquisition_leads_{dt.date.today().isoformat()}.csv",
            mime="text/csv",
        )

        for idx, item in enumerate(filtered, 1):
            with st.expander(f"{idx}. {item['title']} — {item['screen_status']}"):
                st.markdown(f"**Original source:** [{item['source']}]({item['url']})")
                st.write(f"**Listing evidence:** {item['listing_evidence']}")
                st.write(f"**Financial evidence:** {item['financial_evidence']}")
                st.write(f"**Advertised financial status:** figures are not independently verified unless the evidence and verification steps above have been completed.")
                st.write(f"**Notes:** {item['verification_notes'] or 'No evidence notes supplied.'}")
                st.write("**Screen reasons / next steps:**")
                for reason in item["screen_reasons"]:
                    st.write(f"- {reason}")
                st.markdown("**Due-diligence checklist**")
                base_checks = [
                    "Confirm the business is still for sale and that the seller/broker is authorised.",
                    "Obtain three years of financial statements, tax returns and BAS; reconcile to bank records.",
                    "Reconcile EBITDA to owner add-backs, market-rate owner wages, one-off expenses and recurring costs.",
                    "Review working capital, capital expenditure, debt, tax liabilities and cash conversion.",
                    "Check PPSR registrations, asset ownership, leases, licences and change-of-control clauses.",
                    "Review customer concentration, supplier dependency, staff entitlements and key-person risk.",
                    "Obtain independent legal, accounting, tax and commercial advice before making an offer.",
                ]
                industry = (item.get("industry") or "").lower()
                if "transport" in industry or "logistics" in industry:
                    base_checks += [
                        "Inspect fleet condition, finance/lease encumbrances, registrations and maintenance records.",
                        "Review driver employment/contractor classification and relevant safety obligations.",
                    ]
                elif "manufactur" in industry:
                    base_checks += [
                        "Inspect plant condition, maintenance logs, safety compliance and environmental obligations.",
                        "Verify ownership and transferability of intellectual property and key equipment.",
                    ]
                elif "service" in industry or "health" in industry:
                    base_checks += [
                        "Check recurring contract renewal rates, customer retention and transferability of contracts.",
                        "Review professional licences, accreditations and dependence on the current owner.",
                    ]
                for check in base_checks:
                    st.checkbox(check, key=f"dd_{item['lead_key']}_{idx}_{hashlib.md5(check.encode()).hexdigest()[:8]}")

st.divider()
st.caption(
    "Privacy: this version does not use SQLite or intentionally persist listing data in an application database. "
    "Session data may be lost on refresh/restart. The hosting provider can still process IP addresses, access logs, "
    "request metadata and diagnostics. Do not enter personal, commercially confidential, or seller-identifying "
    "information without a reviewed privacy and security arrangement."
)
st.caption(
    "Data quality: public RSS is discovery-only and may return news, duplicates, redirects, or stale results. "
    "A production-grade listing service needs an authorised broker/marketplace API or a vetted manual ingestion process. "
    "This app does not automatically verify active sale status, ownership, financial claims, or legal compliance."
)
