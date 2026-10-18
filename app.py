import streamlit as st
import sqlite3
import pandas as pd
import datetime
import re
import io

# Optional PDF parsing support (install pypdf via pip install pypdf if using PDFs)
try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# ==========================================
# PAGE CONFIGURATION & BRANDING HIDE
# ==========================================
st.set_page_config(
    page_title="Australian Business Acquisition Protocol | Enterprise",
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
                    multiple REAL,
                    dscr REAL,
                    payback_years REAL,
                    score REAL,
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
                INSERT INTO analyzed_leads (title, source, industry, asking_price, reported_profit, multiple, dscr, payback_years, score, analysis_date, raw_text)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lead['title'], lead['source'], lead['industry'], lead['asking_price'], lead['reported_profit'], 
                lead['multiple'], lead['dscr'], lead['payback_years'], lead['score'], 
                datetime.date.today().isoformat(), lead['raw_text']
            ))
            conn.commit()
    except Exception as e:
        st.warning(f"Could not save analysis to database: {e}")

def recall_stored_deals(min_score, start_date, end_date):
    try:
        with sqlite3.connect("acquisitions.db") as conn:
            query = """
                SELECT title, source, industry, asking_price, reported_profit, multiple, dscr, payback_years, score, analysis_date 
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
# DOCUMENT TEXT SCRAPING & EXTRACTION ENGINE
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
            st.error(f"Error reading PDF file: {e}")
    else:
        try:
            text = uploaded_file.read().decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"Error reading text file: {e}")
    return text

def parse_financials_from_text(text):
    """Smart pattern-matching scraper to extract business metrics from unstructured IM or financial text."""
    lines = text.split('\n')
    
    # Defaults
    title = "Extracted Acquisition Target"
    asking_price = 500000.0
    ebitda = 120000.0
    industry = "General"
    
    # Simple regex extractions
    for line in lines:
        line_lower = line.lower()
        if "business" in line_lower or "company" in line_lower or "title" in line_lower:
            if len(line.strip()) < 50 and ":" in line:
                title = line.split(":")[-1].strip()
        
        if "asking price" in line_lower or "price:" in line_lower:
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

        if "transport" in line_lower or "logistics" in line_lower:
            industry = "Transport & Logistics"
        elif "manufacturing" in line_lower:
            industry = "Manufacturing"
        elif "supply chain" in line_lower or "distribution" in line_lower:
            industry = "Supply Chain"
        elif "service" in line_lower:
            industry = "Commercial Services"

    return title, asking_price, ebitda, industry

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
st.markdown("Individual document ingestion and automated financial scraping engine with historical deal recall.")

# Sidebar Configuration for Financing & Deal Recall
st.sidebar.header("⚙️ Financing Parameters")
debt_fraction = st.sidebar.slider("Debt Funding (%)", 0, 90, 70) / 100
interest_rate = st.sidebar.slider("Annual Interest Rate (%)", 0.0, 20.0, 8.0, 0.25) / 100
loan_term = st.sidebar.slider("Loan Term (Years)", 1, 30, 7)

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

# Main Section: Single Document Uploader
st.header("📄 Single Business Document Ingestion")
st.markdown("Upload a business document (Information Memorandum, P&L statement, or summary text file) to automatically extract metrics and analyze the opportunity individually.")

uploaded_file = st.file_uploader("Choose a business document (.pdf, .txt)", type=["pdf", "txt"])

if uploaded_file is not None:
    with st.spinner("Scraping financial data and calculating institutional metrics..."):
        raw_text = extract_text_from_file(uploaded_file)
        title, asking_price, reported_profit, industry = parse_financials_from_text(raw_text)
        
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
        score = round(max(0, min(100, (10 - multiple) * 8 + (dscr * 5))), 1)
        payback_years = multiple
        
        analyzed_lead = {
            "title": title,
            "source": f"Uploaded File: {uploaded_file.name}",
            "industry": industry,
            "asking_price": asking_price,
            "reported_profit": reported_profit,
            "multiple": multiple,
            "dscr": dscr,
            "payback_years": payback_years,
            "score": score,
            "raw_text": raw_text
        }
        
        # Save to database automatically on analysis
        save_analysis_to_db(analyzed_lead)
        
    st.success(f"Successfully scraped and analyzed: **{title}**!")
    
    # Display Individual Business Breakdown
    st.markdown("---")
    st.subheader(f"📊 Financial & Valuation Breakdown: {title}")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Extracted Industry:** {industry}")
        st.markdown(f"**Asking Price:** ${asking_price:,.2f}")
        st.markdown(f"**Reported EBITDA / Profit:** ${reported_profit:,.2f}")
        st.markdown(f"**Valuation Multiple:** {multiple}x")
    with col2:
        st.markdown(f"**Estimated DSCR:** {dscr}x (Min 1.25x recommended)")
        st.markdown(f"**Simple Payback Period:** {payback_years} years")
        st.markdown(f"**Acquisition Score:** **{score} / 100**")
        
    st.markdown("#### 🔍 Industry-Specific Due Diligence Checklist")
    dd_questions = get_due_diligence_questions(industry)
    for q in dd_questions:
        st.markdown(f"- {q}")
        
    # Export single executive summary
    df_single = pd.DataFrame([analyzed_lead])
    csv_data = df_single.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Executive Briefing (CSV)",
        data=csv_data,
        file_name=f"acquisition_analysis_{title.replace(' ', '_')}_{datetime.date.today()}.csv",
        mime="text/csv"
    )
else:
    st.info("Upload a document above to begin analyzing an individual business acquisition target.")