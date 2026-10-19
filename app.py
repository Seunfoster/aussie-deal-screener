import streamlit as st
import sqlite3
import pandas as pd
import datetime
import re

# Optional PDF parsing support
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# ==========================================
# PAGE CONFIGURATION & BRANDING HIDE
# ==========================================
st.set_page_config(
    page_title="Australian Business Acquisition & Valuation Protocol",
    page_icon="🏢",
    layout="wide"
)

hide_streamlit_style = """
    <style>
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}
    .viewerBadge_container__1QSob {display: none !important;}
    </style>
"""
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

# ==========================================
# DATABASE INITIALIZATION & PERSISTENCE
# ==========================================
def init_db():
    try:
        with sqlite3.connect("acquisitions.db") as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS analyzed_leads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT,
                    source TEXT,
                    industry TEXT,
                    asking_price REAL,
                    reported_profit REAL,
                    share_price REAL,
                    shares_outstanding REAL,
                    market_cap REAL,
                    appropriate_share_price REAL,
                    multiple REAL,
                    dscr REAL,
                    payback_years REAL,
                    score REAL,
                    trend_status TEXT,
                    behavioral_risk TEXT,
                    analysis_date TEXT,
                    raw_text TEXT
                )
            ''')
            conn.commit()
    except Exception as e:
        st.error(f"Database initialization error: {e}")

init_db()

def save_analysis_to_db(lead):
    try:
        with sqlite3.connect("acquisitions.db") as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO analyzed_leads (
                    title, source, industry, asking_price, reported_profit, share_price, 
                    shares_outstanding, market_cap, appropriate_share_price, multiple, 
                    dscr, payback_years, score, trend_status, behavioral_risk, analysis_date, raw_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead['title'], lead['source'], lead['industry'], lead['asking_price'], lead['reported_profit'], 
                lead['share_price'], lead['shares_outstanding'], lead['market_cap'], lead['appropriate_share_price'],
                lead['multiple'], lead['dscr'], lead['payback_years'], lead['score'], 
                lead['trend_status'], lead['behavioral_risk'], datetime.date.today().isoformat(), lead['raw_text']
            ))
            conn.commit()
    except Exception as e:
        st.warning(f"Could not save analysis to database: {e}")

def recall_stored_deals(min_score, start_date, end_date):
    try:
        with sqlite3.connect("acquisitions.db") as conn:
            query = """
                SELECT title, source, industry, asking_price, reported_profit, appropriate_share_price, multiple, dscr, score, trend_status, analysis_date 
                FROM analyzed_leads 
                WHERE score >= ? AND analysis_date BETWEEN ? AND ?
                ORDER BY score DESC
            """
            df = pd.read_sql(query, conn, params=(min_score, start_date.isoformat(), end_date.isoformat()))
            if not df.empty:
                return df.to_dict(orient="records")
    except Exception:
        pass
    return []

# ==========================================
# ADVANCED TEXT SCRAPING & BEHAVIORAL ENGINE
# ==========================================
def extract_text_from_file(uploaded_file):
    text = ""
    if uploaded_file.name.endswith('.pdf') and PdfReader:
        try:
            reader = PdfReader(uploaded_file)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted:
                    text += extracted + "\n"
        except Exception as e:
            st.error(f"Error reading PDF file {uploaded_file.name}: {e}")
    else:
        try:
            text = uploaded_file.read().decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"Error reading text file {uploaded_file.name}: {e}")
    return text

def perform_trend_and_behavioral_analysis(text):
    """Analyzes text for operational trends, margin trajectory, and management behavioral risks."""
    text_lower = text.lower()
    
    # Trend detection
    positive_trend_keywords = ["growth", "expanding", "increasing revenue", "record sales", "upward", "scalable"]
    negative_trend_keywords = ["decline", "contraction", "headwinds", "stagnant", "recession", "churn"]
    
    pos_count = sum(text_lower.count(k) for k in positive_trend_keywords)
    neg_count = sum(text_lower.count(k) for k in negative_trend_keywords)
    
    if pos_count > neg_count + 1:
        trend_status = "Positive Expansion Trajectory"
    elif neg_count > pos_count:
        trend_status = "Downward Contraction Risk"
    else:
        trend_status = "Stable / Sideways Trend"

    # Behavioral & Management risk assessment
    risk_keywords = ["key person", "litigation", "dispute", "departure", "unverified", "concentration", "regulatory"]
    risk_found = [k for k in risk_keywords if k in text_lower]
    
    if len(risk_found) >= 2:
        behavioral_risk = f"Elevated Risk Factors Identified: {', '.join(risk_found)}"
    elif len(risk_found) == 1:
        behavioral_risk = f"Moderate Risk Factor Noted: {risk_found[0]}"
    else:
        behavioral_risk = "Low Behavioral Risk; Stable Management Indicators"

    return trend_status, behavioral_risk

def parse_financials_from_text(text, filename=""):
    lines = text.split('\n')
    
    title = f"Target from {filename}" if filename else "Extracted Acquisition Target"
    asking_price = 1000000.0
    ebitda = 250000.0
    share_price = 0.0
    shares_outstanding = 0.0
    industry = "General"
    
    for line in lines:
        line_lower = line.lower()
        if "business" in line_lower or "company" in line_lower or "title" in line_lower:
            if len(line.strip()) < 50 and ":" in line:
                title = line.split(":")[-1].strip()
        
        if "asking price" in line_lower or "valuation" in line_lower or "market cap" in line_lower:
            numbers = re.findall(r'[\d,]+', line)
            if numbers:
                clean_num = float(numbers[0].replace(',', ''))
                if clean_num > 10000:
                    asking_price = clean_num
                    
        if "ebitda" in line_lower or "net profit" in line_lower or "profit" in line_lower:
            numbers = re.findall(r'[\d,]+', line)
            if numbers:
                clean_num = float(numbers[0].replace(',', ''))
                if clean_num > 5000:
                    ebitda = clean_num

        if "share price" in line_lower or "stock price" in line_lower:
            numbers = re.findall(r'[\d\.]+', line)
            if numbers:
                share_price = float(numbers[0])

        if "shares outstanding" in line_lower or "total shares" in line_lower:
            numbers = re.findall(r'[\d,]+', line)
            if numbers:
                shares_outstanding = float(numbers[0].replace(',', ''))

        if "transport" in line_lower or "logistics" in line_lower:
            industry = "Transport & Logistics"
        elif "manufacturing" in line_lower:
            industry = "Manufacturing"
        elif "supply chain" in line_lower or "distribution" in line_lower:
            industry = "Supply Chain"
        elif "service" in line_lower:
            industry = "Commercial Services"

    return title, asking_price, ebitda, share_price, shares_outstanding, industry

# ==========================================
# INSTITUTIONAL VALUATION & SHARE PRICE ENGINE
# ==========================================
def calculate_appropriate_share_price(ebitda, shares_outstanding, industry, management_score_multiplier):
    """
    Calculates intrinsic appropriate share price using discounted cash flow proxy,
    industry median EBITDA multiples, and management quality weighting.
    """
    if shares_outstanding <= 0:
        return 0.0
        
    # Industry Median EV/EBITDA Benchmarks (Australian Market standards)
    industry_multiples = {
        "Transport & Logistics": 6.5,
        "Manufacturing": 7.0,
        "Supply Chain": 6.8,
        "Commercial Services": 7.5,
        "General": 6.0
    }
    
    base_multiple = industry_multiples.get(industry, 6.0)
    
    # Adjust enterprise value based on management quality track record (multiplier between 0.85 and 1.25)
    adjusted_multiple = base_multiple * management_score_multiplier
    
    implied_enterprise_value = ebitda * adjusted_multiple
    implied_equity_value = implied_enterprise_value * 0.75  # Accounting for net debt adjustments (~25%)
    
    appropriate_price = implied_equity_value / shares_outstanding
    return round(appropriate_price, 2)

# ==========================================
# DYNAMIC DUE DILIGENCE QUESTION BANK
# ==========================================
def get_due_diligence_questions(industry):
    base_questions = [
        "1. Financials: Request past 3 years of complete tax returns, P&L statements, balance sheets, and BAS statements.",
        "2. Compliance: Verify all ATO, GST, PAYG, and superannuation guarantee obligations are fully paid up-to-date.",
        "3. Legal & Encumbrances: Conduct a PPSR search to ensure no hidden security interests or debts are tied to business assets."
    ]
    
    industry_specific = {
        "Transport & Logistics": [
            "4. Fleet & Equipment: What is the age, maintenance history, and encumbrance status of vehicles/trailers?",
            "5. Customer Concentration: Do top 3 clients account for more than 20% of total freight revenue?",
            "6. Driver Contracts: Are drivers classified as employees or independent contractors?"
        ],
        "Commercial Services": [
            "4. Recurring Revenue: What percentage of revenue is bound by long-term service contracts?",
            "5. Key Person Risk: Can the business operate successfully without the owner's day-to-day involvement?"
        ],
        "Supply Chain": [
            "4. Warehouse Lease: What are the remaining terms, option periods, and rent escalation clauses?",
            "5. Inventory Valuation: What is the exact methodology and aging breakdown for stock-in-trade?"
        ],
        "Manufacturing": [
            "4. Plant & Machinery: Have independent valuations and safety audits been conducted on heavy machinery?",
            "5. Environmental & Safety: Are there any pending EPA or WorkSafe compliance orders?"
        ]
    }
    
    return base_questions + industry_specific.get(industry, [
        "4. Operational Contracts: Review key supplier and customer agreements for change-of-control clauses.",
        "5. Staff Entitlements: Review employee schedules, accrued leave, and redundancy liabilities."
    ])

# ==========================================
# STREAMLIT USER INTERFACE (GUI)
# ==========================================
st.title("🇦🇺 Enterprise Business Acquisition Protocol")
st.markdown("Advanced Document Ingestion, Trend & Behavioral Analytics, and Intrinsic Share Price Modeling.")

# Sidebar Configuration for Financing & Valuation Factors
st.sidebar.header("⚙️ Financing & Valuation Parameters")
debt_fraction = st.sidebar.slider("Debt Funding (%)", 0, 90, 70) / 100
interest_rate = st.sidebar.slider("Annual Interest Rate (%)", 0.0, 20.0, 8.0, 0.25) / 100
loan_term = st.sidebar.slider("Loan Term (Years)", 1, 30, 7)

st.sidebar.markdown("---")
st.sidebar.header("🎖️ Management Quality Multiplier")
management_track_record = st.sidebar.selectbox(
    "Leadership Track Record & Past Achievements",
    ["Tier 1: Exceptional (Proven scaled exits, decades tenure) [1.15x]", 
     "Tier 2: Competent & Stable Industry Veterans [1.05x]", 
     "Tier 3: Average / Unproven Execution Risk [1.00x]", 
     "Tier 4: Suboptimal / High Turnover History [0.85x]"]
)

# Parse multiplier
if "Tier 1" in management_track_record:
    mgmt_multiplier = 1.15
elif "Tier 2" in management_track_record:
    mgmt_multiplier = 1.05
elif "Tier 4" in management_track_record:
    mgmt_multiplier = 0.85
else:
    mgmt_multiplier = 1.00

st.sidebar.markdown("---")
st.sidebar.header("🔍 Historical Deal Recall")
recall_min_score = st.sidebar.slider("Minimum Acquisition Score", 0.0, 100.0, 50.0, 5.0)
recall_start_date = st.sidebar.date_input("Start Date", datetime.date.today() - datetime.timedelta(days=30))
recall_end_date = st.sidebar.date_input("End Date", datetime.date.today())

if st.sidebar.button("📂 Recall Saved Deals"):
    st.subheader("📁 Recalled Historical Analysis Results")
    recalled_deals = recall_stored_deals(recall_min_score, recall_start_date, recall_end_date)
    if recalled_deals:
        df_recalled = pd.DataFrame(recalled_deals)
        st.dataframe(df_recalled, use_container_width=True, hide_index=True)
    else:
        st.info("No historical deals found matching your score and date criteria.")

# Main Section: Multi-Document Uploader
st.header("📄 Batch Business Document Ingestion")
st.markdown("Upload business documents (Information Memorandums, P&L statements, or Annual Reports) to perform financial scraping, behavioral trend analysis, and public share price valuation.")

uploaded_files = st.file_uploader("Choose business documents (.pdf, .txt)", type=["pdf", "txt"], accept_multiple_files=True)

if uploaded_files:
    analyzed_leads_batch = []
    
    with st.spinner("Scraping financial data, running trend analysis, and computing appropriate share prices..."):
        for uploaded_file in uploaded_files:
            raw_text = extract_text_from_file(uploaded_file)
            title, asking_price, reported_profit, share_price, shares_outstanding, industry = parse_financials_from_text(raw_text, uploaded_file.name)
            
            # Trend and Behavioral Analysis
            trend_status, behavioral_risk = perform_trend_and_behavioral_analysis(raw_text)
            
            # Calculations
            multiple = round(asking_price / reported_profit, 2) if reported_profit > 0 else 0.0
            loan = asking_price * debt_fraction
            months = loan_term * 12
            monthly_rate = interest_rate / 12
            
            if loan <= 0:
                annual_debt_service = 0
            elif monthly_rate == 0:
                annual_debt_service = loan / loan_term
            else:
                monthly_payment = loan * monthly_rate / (1 - (1 + monthly_rate) ** (-months))
                annual_debt_service = monthly_payment * 12
                
            dscr = round(reported_profit / annual_debt_service, 2) if annual_debt_service > 0 else 99.0
            
            # Intrinsic appropriate share price modeling
            appropriate_share_price = calculate_appropriate_share_price(reported_profit, shares_outstanding, industry, mgmt_multiplier)
            
            # Scoring incorporating trend & behavioral health
            trend_bonus = 10 if "Positive" in trend_status else (-10 if "Downward" in trend_status else 0)
            risk_penalty = -15 if "Elevated" in behavioral_risk else 0
            score = round(max(0, min(100, (10 - multiple) * 7 + (dscr * 4) + trend_bonus + risk_penalty)), 1)
            payback_years = multiple
            
            analyzed_lead = {
                "title": title,
                "source": f"Uploaded File: {uploaded_file.name}",
                "industry": industry,
                "asking_price": asking_price,
                "reported_profit": reported_profit,
                "share_price": share_price,
                "shares_outstanding": shares_outstanding,
                "market_cap": share_price * shares_outstanding,
                "appropriate_share_price": appropriate_share_price,
                "multiple": multiple,
                "dscr": dscr,
                "payback_years": payback_years,
                "score": score,
                "trend_status": trend_status,
                "behavioral_risk": behavioral_risk,
                "raw_text": raw_text
            }
            
            save_analysis_to_db(analyzed_lead)
            analyzed_leads_batch.append(analyzed_lead)
            
    st.success(f"Successfully processed and analyzed {len(analyzed_leads_batch)} business documents!")
    
    # Display Batch Overview Table
    st.markdown("---")
    st.subheader("📊 Batch Comparative Screening & Valuation Overview")
    df_batch = pd.DataFrame(analyzed_leads_batch)
    st.dataframe(df_batch[["title", "industry", "reported_profit", "multiple", "dscr", "appropriate_share_price", "score", "trend_status"]], use_container_width=True, hide_index=True)
    
    # Individual Expanders for Detailed Review
    st.markdown("---")
    st.subheader("📋 Detailed Deal Breakdowns, Valuation & Due Diligence")
    for idx, lead in enumerate(analyzed_leads_batch, 1):
        with st.expander(f"[{idx}] {lead['title']} - Score: {lead['score']}/100 | Appropriate Share Price: ${lead['appropriate_share_price']} AUD"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Source Document:** {lead['source']}")
                st.markdown(f"**Extracted Industry:** {lead['industry']}")
                st.markdown(f"**Reported EBITDA / Profit:** ${lead['reported_profit']:,.2f}")
                st.markdown(f"**Valuation Multiple:** {lead['multiple']}x")
                st.markdown(f"**Estimated DSCR:** {lead['dscr']}x (Min 1.25x recommended)")
            with col2:
                st.markdown(f"**Market Share Price:** ${lead['share_price']:,.2f} AUD")
                st.markdown(f"**Calculated Appropriate Share Price:** **${lead['appropriate_share_price']:,.2f} AUD**")
                st.markdown(f"**Operational Trend:** {lead['trend_status']}")
                st.markdown(f"**Behavioral Risk Analysis:** {lead['behavioral_risk']}")
                st.markdown(f"**Acquisition Score:** **{lead['score']} / 100**")
                
            st.markdown("#### 🔍 Industry-Specific Due Diligence Checklist")
            dd_questions = get_due_diligence_questions(lead['industry'])
            for q in dd_questions:
                st.markdown(f"- {q}")
                
    # Export batch summary
    csv_data = df_batch.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Batch Executive Briefing (CSV)",
        data=csv_data,
        file_name=f"batch_acquisition_valuation_{datetime.date.today()}.csv",
        mime="text/css"
    )
else:
    st.info("Upload one or more documents above to begin batch-analyzing business acquisition targets and share price valuations.")