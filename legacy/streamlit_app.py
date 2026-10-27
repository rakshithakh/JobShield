import streamlit as st
import re
import pickle
import os
import requests
import pdfplumber
import io

st.set_page_config(page_title="JobSentinel", page_icon="🛡️", layout="centered")

st.markdown("""
<style>
.score-box { padding:24px; border-radius:14px; text-align:center; margin:16px 0; }
.red-box    { background:#fff0f0; border:2px solid #ff4444; }
.orange-box { background:#fff8f0; border:2px solid #ff8c00; }
.green-box  { background:#f0fff4; border:2px solid #00cc44; }
.big-score  { font-size:58px; font-weight:bold; }
.verdict    { font-size:22px; font-weight:bold; margin-top:8px; }
</style>
""", unsafe_allow_html=True)

SCAM_PATTERNS = {
    "Registration/Training Fee": (30, [
        r'(registration\s*fee|training\s*fee|joining\s*fee|security\s*deposit)',
        r'pay\s*(rs\.?|rs|inr|₹)\.?\s*\d+',
        r'(rs\.?|₹)\s*\d+\s*(registration|fee|joining|deposit|charge)',
        r'pay\s+\d+\s*(before|to\s*get|for\s*joining)',
        r'(fee|deposit|charge)\s*(of|is|:)?\s*(rs\.?|₹)\s*\d+',
    ]),
    "Urgency Tactics": (20, [
        r'(only\s+\d+\s+seats?|limited\s+seats?|seats?\s+left)',
        r'\b(urgent|urgently|immediately|apply\s+now|apply\s+today)\b',
        r'(last\s+date\s+today|closing\s+soon|hurry|don.t\s+miss)',
        r'(limited\s+(time|positions?|slots?|openings?))',
    ]),
    "Unrealistic Promises": (20, [
        r'(no\s+experience\s+(needed|required|necessary))',
        r'(anyone\s+can\s+apply|no\s+qualification\s+required)',
        r'(guaranteed\s+(income|salary|earning|payment))',
        r'(unlimited\s+(earning|income|money|opportunity))',
        r'(be\s+your\s+own\s+boss)',
    ]),
    "Personal Email Contact": (25, [
        r'[\w\.\-]+@(gmail|yahoo|hotmail|outlook|rediffmail|ymail|aol)\.com',
    ]),
    "Suspicious Work Pattern": (20, [
        r'(work\s+(timing|time)\s*[:\-]?\s*24\s*/\s*7)',
        r'(work\s+any\s*time|anytime\s+work)',
        r'(daily\s+payment|payment\s+daily|pay\s+daily)',
        r'(upi|digital\s+wallet|paytm)\s*(payment|transfer)',
        r'(per\s+entry|per\s+form|per\s+page)\s*(rs|₹|\d)',
        r'(rs|₹)\s*\d+\s*per\s*(entry|form|page)',
    ]),
    "MLM/Network Marketing": (30, [
        r'(network\s+marketing|mlm|multi[\s\-]?level|direct\s+selling)',
        r'(refer\s+(friends?|others?|people).*earn)',
        r'(join\s+our\s+network|build\s+your\s+network)',
        r'(downline|upline|pyramid)',
    ]),
    "Too Good To Be True": (20, [
        r'(free\s+(laptop|mobile|phone|accommodation|iphone))',
        r'(car\s+after\s+(target|achieving|joining|level))',
        r'(foreign\s+trip|abroad\s+trip|international\s+tour)',
        r'(earn\s+(rs\.?|₹)\s*[1-9]\s*lakh|1\s*lakh\s+per\s+month)',
    ]),
}

TRUSTED = [
    "infosys","tcs","tata consultancy","wipro","hcl","tech mahindra",
    "accenture","ibm","microsoft","google","amazon","flipkart","zoho",
    "cognizant","capgemini","deloitte","oracle","sap","swiggy","zomato",
    "ola","paytm","razorpay","freshworks","persistent","hexaware","bosch",
    "samsung","cisco","dell","hp","hdfc","icici","sbi","axis bank","kotak",
    "reliance","tata","mahindra","bajaj","kpmg","pwc","ey ","ernst",
    "infosys bpm","wipro bps","accenture solutions","ltimindtree","mphasis"
]

SCAM_KEYWORDS = [
    "nexgen","fastjobs","quickhire","easyjobs","dreamjobs",
    "earnfast","fastmoney","quickearn","homejobs","easywork","earnbig",
    "workeasy","jobseasy","hirefast","bestjobs","topjobs","earnquick",
    "moneyearn","workfromhomejobs","onlinejobsindia"
]

SALARY_DB = {
    "software developer":   {"min":300000,"max":800000},
    "software engineer":    {"min":350000,"max":1200000},
    "data analyst":         {"min":300000,"max":700000},
    "data scientist":       {"min":500000,"max":1500000},
    "web developer":        {"min":250000,"max":700000},
    "frontend developer":   {"min":300000,"max":900000},
    "backend developer":    {"min":350000,"max":1000000},
    "full stack developer": {"min":400000,"max":1200000},
    "machine learning":     {"min":600000,"max":1800000},
    "devops engineer":      {"min":500000,"max":1400000},
    "call center":          {"min":150000,"max":360000},
    "data entry":           {"min":120000,"max":300000},
    "customer support":     {"min":180000,"max":400000},
    "sales executive":      {"min":200000,"max":600000},
    "digital marketing":    {"min":250000,"max":700000},
    "content writer":       {"min":180000,"max":500000},
    "graphic designer":     {"min":200000,"max":600000},
    "work from home":       {"min":120000,"max":400000},
    "marketing executive":  {"min":200000,"max":600000},
    "hr executive":         {"min":250000,"max":600000},
    "accountant":           {"min":250000,"max":600000},
}

FREE_DOMAINS = [
    "gmail.com","yahoo.com","hotmail.com","outlook.com",
    "rediffmail.com","ymail.com","aol.com","yahoo.in",
    "hotmail.in","live.com","icloud.com"
]


# ── MODEL LOADING — lazy imports so app starts fast ───────────────────────────
@st.cache_resource
def load_model():
    # Try DistilBERT first — only imports torch if folder exists
    bert_path = "distilbert_model"
    if os.path.exists(bert_path):
        try:
            import torch
            from transformers import (DistilBertTokenizerFast,
                                      DistilBertForSequenceClassification)
            tokenizer = DistilBertTokenizerFast.from_pretrained(bert_path)
            model = DistilBertForSequenceClassification.from_pretrained(bert_path)
            model.eval()
            return "bert", tokenizer, model
        except Exception:
            pass

    # Fall back to TF-IDF pickle model
    mp = os.path.join("model","scam_model.pkl")
    vp = os.path.join("model","vectorizer.pkl")
    if os.path.exists(mp) and os.path.exists(vp):
        with open(mp,"rb") as f: mdl = pickle.load(f)
        with open(vp,"rb") as f: vec = pickle.load(f)
        return "tfidf", vec, mdl

    return "none", None, None


def predict_scam(text, model_type, obj1, obj2):
    """Returns scam probability 0-100"""
    if model_type == "bert":
        import torch
        import torch.nn.functional as F
        tokenizer, model = obj1, obj2
        inputs = tokenizer(
            text, return_tensors="pt",
            truncation=True, max_length=256, padding=True
        )
        with torch.no_grad():
            outputs = model(**inputs)
        probs = F.softmax(outputs.logits, dim=1)
        return int(probs[0][1].item() * 100)

    elif model_type == "tfidf":
        vec, model = obj1, obj2
        prob = model.predict_proba(vec.transform([text]))[0][1]
        return int(prob * 100)

    return 0


# ── ANALYSIS FUNCTIONS ────────────────────────────────────────────────────────
def analyze_nlp(text, model_type, obj1, obj2):
    t = text.lower()
    flags, pattern_score = [], 0

    for category, (pts, patterns) in SCAM_PATTERNS.items():
        for p in patterns:
            if re.search(p, t):
                flags.append(f"🔴 {category} detected")
                pattern_score += pts
                break

    pattern_score = min(pattern_score, 70)
    ml_score = predict_scam(text, model_type, obj1, obj2)

    if model_type == "bert":
        if ml_score >= 75:
            flags.append(f"🤖 DistilBERT: {ml_score}% scam probability — HIGH CONFIDENCE")
            final = int(0.6 * ml_score + 0.4 * pattern_score)
        elif ml_score >= 50:
            flags.append(f"🤖 DistilBERT: {ml_score}% — moderate signal")
            final = int(0.4 * ml_score + 0.6 * pattern_score)
        else:
            flags.append(f"🤖 DistilBERT: {ml_score}% — likely safe signal")
            final = int(0.2 * ml_score + 0.8 * pattern_score)

    elif model_type == "tfidf":
        if ml_score >= 75:
            flags.append(f"🤖 ML Model: {ml_score}% scam probability — HIGH CONFIDENCE")
            final = int(0.6 * ml_score + 0.4 * pattern_score)
        elif ml_score >= 50:
            flags.append(f"🤖 ML Model: {ml_score}% — LOW CONFIDENCE (limited training data)")
            final = int(0.3 * ml_score + 0.7 * pattern_score)
        else:
            flags.append(f"🤖 ML Model: {ml_score}% — likely safe signal")
            final = int(0.2 * ml_score + 0.8 * pattern_score)
    else:
        flags.append("ℹ️ No ML model — pattern detection only. Run train_model.py")
        final = pattern_score

    if not flags:
        flags.append("✅ No scam patterns detected in text")

    return flags, min(final, 100)


def verify_company(name):
    flags, score = [], 0

    if not name or not name.strip():
        return ["🔴 No company name provided — cannot verify employer"], 35

    nl = name.lower().strip()

    # Step 1 — Trusted whitelist
    for t in TRUSTED:
        if t in nl or nl in t:
            return [f"✅ '{name}' is a well-known verified company"], 0

    # Step 2 — Known scam keywords
    matched_kw = False
    for kw in SCAM_KEYWORDS:
        if kw in nl:
            flags.append(f"🔴 '{name}' matches known scam company patterns")
            score += 30
            matched_kw = True
            break

    # Step 3 — MCA21 API
    key = os.getenv("MCA_API_KEY","")
    if key:
        nicknames = {
            "tcs":           "TATA CONSULTANCY SERVICES LIMITED",
            "infosys":       "INFOSYS LIMITED",
            "wipro":         "WIPRO LIMITED",
            "hcl":           "HCL TECHNOLOGIES LIMITED",
            "tech mahindra": "TECH MAHINDRA LIMITED",
        }
        official = nicknames.get(nl, name.upper())
        try:
            resp = requests.get(
                "https://api.data.gov.in/resource/21c98e49-f834-4e04-8b33-4e93f0e4f3ef",
                params={"api-key":key,"format":"json",
                        "filters[company_name]":official,"limit":1},
                timeout=6
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("count",0) == 0:
                    flags.append(f"🔴 '{name}' NOT found in MCA21 government database")
                    score += 25
                else:
                    status = data["records"][0].get("company_status","").lower()
                    if "struck" in status or "dissolved" in status:
                        flags.append(f"🔴 Company legally '{status}' — inactive")
                        score += 35
                    else:
                        flags.append(f"✅ Found in MCA21 — Status: {status.title()}")
                        score -= 10
            else:
                if not matched_kw:
                    score += 8
        except:
            flags.append("ℹ️ Could not reach MCA21 API")
            if not matched_kw:
                score += 5
    else:
        if not matched_kw:
            flags.append(f"ℹ️ Set MCA_API_KEY env variable to verify '{name}' in govt database")
            score += 8

    # Step 4 — Clearbit website check
    try:
        domain_guess = re.sub(r"[^a-z0-9]","",nl) + ".com"
        resp = requests.get(f"https://logo.clearbit.com/{domain_guess}", timeout=4)
        if resp.status_code == 200:
            flags.append(f"✅ Company website verified — '{domain_guess}' exists")
            score = max(0, score - 8)
        else:
            flags.append(f"⚠️ No company website found for '{domain_guess}'")
            score += 10
    except:
        flags.append("ℹ️ Could not verify company website")

    return flags, max(0, min(score, 40))


def check_domain(text, company=""):
    t = text.lower()
    matches = re.findall(r'[\w\.\-]+@([\w\.\-]+\.[a-zA-Z]{2,})', t)

    if not matches:
        return ["🔴 No company email found in description — suspicious for a real job"], 15

    domain = matches[0].lower()
    flags, score = [], 0

    is_free = any(fd in domain for fd in FREE_DOMAINS)

    if is_free:
        flags.append(f"🔴 Contact uses free email '@{domain}' — legitimate companies use their own domain")
        score += 30
        if company:
            slug = re.sub(r"[^a-z0-9]","",company.lower())
            dom_clean = re.sub(r"[^a-z0-9]","",domain)
            if slug not in dom_clean:
                flags.append(f"🔴 Email domain doesn't match company name '{company}'")
                score += 10
    else:
        flags.append(f"✅ Contact uses company domain '@{domain}'")
        score -= 5

    return flags, max(0, min(score, 40))
def check_salary(title, text):
    t = (title + " " + text).lower()
    flags, score = [], 0

    monthly_patterns = [
        r'(?:rs\.?|rs|inr|₹|earn|salary|package|stipend|ctc)[/\s\.]*(\d+(?:,\d+)*)\s*(?:/-\s*)?(?:per\s*month|/month|monthly|month\b)',
        r'(\d+(?:,\d+)*)\s*(?:rs\.?|rs|₹)\s*(?:per\s*month|/month|monthly)',
        r'(\d+)k\s*(?:per\s*month|/month)',
    ]

    annual_patterns = [
        r'(\d+(?:\.\d+)?)\s*(?:lakh|lac|lpa|l\.p\.a)',
        r'ctc[:\s]+(\d+(?:\.\d+)?)\s*(?:lakh|lac|lpa)',
        r'package[:\s]+(\d+(?:\.\d+)?)\s*(?:lakh|lac|lpa)',
    ]

    salary_annual = None
    display = ""

    # ---- Monthly Salary Detection ----
    for pat in monthly_patterns:
        m = re.search(pat, t)

        if m:
            try:
                val = float(m.group(1).replace(",", ""))

                # Handle values like 25k/month
                if pat.strip().startswith(r'(\d+)k'):
                    val *= 1000

                salary_annual = val * 12
                display = f"₹{val:,.0f}/month (₹{salary_annual/100000:.1f} LPA)"
                break

            except:
                pass

    # ---- Annual Salary Detection ----
    if not salary_annual:
        for pat in annual_patterns:
            m = re.search(pat, t)

            if m:
                try:
                    val = float(m.group(1))

                    salary_annual = val * 100000
                    display = f"₹{val:.1f} LPA"
                    break

                except:
                    pass

    # ---- No Salary Found ----
    if not salary_annual:
        return ["ℹ️ No specific salary mentioned in description"], 0

    flags.append(f"💰 Mentioned salary: {display}")

    # ---- Role Matching ----
    role = None

    for r in SALARY_DB:
        keywords = r.split()

        if sum(1 for kw in keywords if kw in t) >= len(keywords):
            role = r
            break

    # ---- Salary Comparison ----
    if role:
        mn = SALARY_DB[role]["min"]
        mx = SALARY_DB[role]["max"]
        mid = (mn + mx) / 2

        if salary_annual > mx * 2.0:
            flags.append(
                f"🔴 Salary is {salary_annual/mid:.1f}x above market for '{role}' — UNREALISTIC"
            )
            score += 30

        elif salary_annual > mx * 1.3:
            flags.append(
                f"⚠️ Salary above market rate for '{role}' (₹{mn//100000}L–₹{mx//100000}L)"
            )
            score += 15

        elif salary_annual < mn * 0.6:
            flags.append(
                f"⚠️ Salary below market rate for '{role}' — unusually low"
            )
            score += 8

        else:
            flags.append(
                f"✅ Salary within market range for '{role}' (₹{mn//100000}L–₹{mx//100000}L)"
            )
            score -= 5

    else:
        flags.append("ℹ️ Role not found in salary benchmark database")

    return flags, max(0, min(score, 30))

def final_score(nlp, company, domain, salary):
    company_norm = (company / 40) * 100
    domain_norm  = (domain  / 40) * 100
    salary_norm  = (salary  / 30) * 100
    return min(int(
        nlp          * 0.40 +
        company_norm * 0.25 +
        domain_norm  * 0.20 +
        salary_norm  * 0.15
    ), 100)


def verdict(score):
    if score >= 60:
        return "HIGH RISK — DO NOT APPLY", "🔴", "red-box", "#cc0000"
    elif score >= 35:
        return "SUSPICIOUS — VERIFY FIRST", "🟠", "orange-box", "#cc6600"
    else:
        return "LIKELY SAFE", "🟢", "green-box", "#007700"


# ── LOAD MODEL ────────────────────────────────────────────────────────────────
model_type, obj1, obj2 = load_model()


# ── UI ────────────────────────────────────────────────────────────────────────
st.title("🛡️ JobSentinel")

if model_type == "bert":
    st.success("🤖 DistilBERT active — transformer-based high accuracy detection")
elif model_type == "tfidf":
    st.info("🤖 TF-IDF ML model active — add distilbert_model/ folder for higher accuracy")
else:
    st.warning("⚠️ No ML model — pattern detection only. Run train_model.py first")

st.markdown("*Detect job scams instantly — paste any job description below.*")
st.divider()

c1, c2 = st.columns(2)
company_name = c1.text_input("🏢 Company Name", placeholder="e.g. Nexgen Solutions")
job_title    = c2.text_input("💼 Job Title",    placeholder="e.g. Data Entry Operator")
job_text     = st.text_area(
    "📋 Paste Job Description / WhatsApp Message / Offer Letter",
    height=220,
    placeholder="Paste full job description here — include the contact email if present..."
)

pdf = st.file_uploader("📎 Or Upload Offer Letter PDF", type=["pdf"])
if pdf:
    try:
        with pdfplumber.open(io.BytesIO(pdf.read())) as doc:
            extracted = " ".join(p.extract_text() or "" for p in doc.pages)
        st.success(f"✅ PDF extracted — {len(extracted)} characters")
        job_text = (job_text + " " + extracted).strip()
    except:
        st.error("Could not read PDF — paste text directly")

st.divider()
st.markdown("**Try a demo:**")
d1, d2, d3 = st.columns(3)

if "prefill" not in st.session_state:
    st.session_state.prefill = None

if d1.button("🔴 Scam Example"):  st.session_state.prefill = "scam"
if d2.button("🟢 Real Job"):       st.session_state.prefill = "real"
if d3.button("🟠 Suspicious"):     st.session_state.prefill = "suspicious"

if st.session_state.prefill == "scam":
    company_name = "Nexgen Solutions"
    job_title    = "Data Entry Operator"
    job_text     = ("Urgent hiring! Work from home data entry job. "
                    "Earn Rs 45000 per month. No experience needed. "
                    "Only 3 seats left. Pay Rs 999 registration fee before joining. "
                    "Daily payment via UPI. Work timing 24/7 you can work anytime. "
                    "Contact: hr.nexgen2024@gmail.com")
elif st.session_state.prefill == "real":
    company_name = "Infosys"
    job_title    = "Software Engineer"
    job_text     = ("Infosys hiring Software Engineers for Bangalore office. "
                    "0-2 years Java and Spring Boot experience required. "
                    "CTC 4.5 LPA. Apply at careers.infosys.com. "
                    "Contact: hr@infosys.com. No fee charged at any stage.")
elif st.session_state.prefill == "suspicious":
    company_name = "TechWork Solutions"
    job_title    = "Marketing Executive"
    job_text     = ("Marketing executives needed urgently. "
                    "Earn Rs 25000 to Rs 80000 per month. Field work required. "
                    "No experience necessary. Training will be provided. "
                    "Contact: hiring@techworksolutions.in")

if st.button("🔍 Analyse Now", type="primary", use_container_width=True):
    if not job_text.strip() and not company_name.strip():
        st.warning("Please enter a job description or company name.")
    else:
        full = f"{job_title} {company_name} {job_text}".strip()

        prog = st.progress(0, text="🤖 Running NLP + AI analysis...")
        nlp_flags,  nlp_score  = analyze_nlp(full, model_type, obj1, obj2)
        prog.progress(25, text="🏢 Verifying company...")
        comp_flags, comp_score = verify_company(company_name)
        prog.progress(50, text="🌐 Checking email domain...")
        dom_flags,  dom_score  = check_domain(full, company_name)
        prog.progress(75, text="💰 Benchmarking salary...")
        sal_flags,  sal_score  = check_salary(job_title, full)
        prog.progress(100, text="✅ Analysis complete!")

        fs = final_score(nlp_score, comp_score, dom_score, sal_score)
        v, emoji, box, color = verdict(fs)

        st.markdown(f"""
        <div class="score-box {box}">
            <div class="big-score" style="color:{color}">{fs}/100</div>
            <div class="verdict" style="color:{color}">{emoji} {v}</div>
        </div>""", unsafe_allow_html=True)

        cc1, cc2, cc3, cc4 = st.columns(4)
        cc1.metric("NLP + AI",  f"{nlp_score}/100")
        cc2.metric("Company",   f"{comp_score}/40")
        cc3.metric("Domain",    f"{dom_score}/40")
        cc4.metric("Salary",    f"{sal_score}/30")

        st.divider()
        st.subheader("🔍 Detailed Findings")

        with st.expander("🤖 NLP + AI Analysis", expanded=True):
            for f in nlp_flags: st.write(f)
        with st.expander("🏢 Company Verification"):
            for f in comp_flags: st.write(f)
        with st.expander("🌐 Email & Domain Check"):
            for f in dom_flags: st.write(f)
        with st.expander("💰 Salary Reality Check"):
            for f in sal_flags: st.write(f)

        st.divider()
        all_red = [f for f in nlp_flags+comp_flags+dom_flags+sal_flags if "🔴" in f]
        st.markdown(f"**{len(all_red)} red flag(s) detected**")

        if fs >= 60:
            st.error("**DO NOT APPLY.** Report at https://cybercrime.gov.in | Helpline: **1930**")
        elif fs >= 35:
            st.warning("**VERIFY FIRST.** Contact company only via official website. Never pay any fee.")
        else:
            st.success("**LIKELY SAFE.** Always verify on official website. Never pay fees or share OTP.")

        with st.expander("📢 How to report a job scam"):
            st.markdown("""
            - **National Cyber Crime Portal:** https://cybercrime.gov.in
            - **Helpline:** Call **1930**
            - **Consumer Forum:** https://consumerhelpline.gov.in
            """)

st.divider()
st.markdown(
    "<p style='text-align:center;color:gray;font-size:13px;'>"
    "JobSentinel — Protecting job seekers across India 🇮🇳</p>",
    unsafe_allow_html=True
)
