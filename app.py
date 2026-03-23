"""
Streamlit web UI for LinkedIn Referral Finder.
Run with: streamlit run app.py
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import streamlit as st
from finder import ReferralFinder
from generator import create_generator
from models import ICPCriteria, SellerContext

st.set_page_config(
    page_title="Referral Finder",
    page_icon="🔗",
    layout="wide",
)

st.title("🔗 LinkedIn Referral Finder")
st.caption("Paste a LinkedIn profile URL → get warm ICP prospects through their real network.")

# ── Sidebar: ICP Criteria ─────────────────────────────────────────────────────
with st.sidebar:
    st.header("Who are you looking for?")

    titles_raw = st.text_area(
        "Target titles (one per line)",
        placeholder="VP of Sales\nHead of Revenue\nDirector of Sales",
        height=120,
    )

    industries_raw = st.text_area(
        "Industries (one per line, optional)",
        placeholder="SaaS\nFintech",
        height=80,
    )

    company_size = st.multiselect(
        "Company size",
        ["1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001+"],
        default=[],
    )

    st.divider()
    st.header("About you (for AI briefs)")

    seller_name = st.text_input("Your name", placeholder="Jane Smith")
    seller_title = st.text_input("Your title", placeholder="Head of SDR")
    seller_company = st.text_input("Your company", placeholder="AskElephant")
    product_desc = st.text_area(
        "What your product does",
        placeholder="AskElephant analyzes sales conversations to surface what messaging and CTAs actually convert...",
        height=100,
    )

    generate_briefs = st.checkbox("Generate AI briefs", value=True,
        help="Uses Google Gemini (free) to write About Them, Why Them, and intro messages.")

    min_score = st.slider("Minimum relationship score", 0, 100, 20)

# ── Main: LinkedIn URL input ───────────────────────────────────────────────────
linkedin_url = st.text_input(
    "LinkedIn profile URL of your referral source",
    placeholder="https://linkedin.com/in/johndoe",
)

run = st.button("Find Prospects", type="primary", use_container_width=True)

# ── Run ───────────────────────────────────────────────────────────────────────
if run:
    if not linkedin_url.strip():
        st.error("Please enter a LinkedIn profile URL.")
        st.stop()

    titles = [t.strip() for t in titles_raw.splitlines() if t.strip()]
    industries = [i.strip() for i in industries_raw.splitlines() if i.strip()]

    icp = ICPCriteria(
        titles=titles,
        industries=industries,
        company_sizes=company_size,
    )

    seller = None
    if generate_briefs and all([seller_name, seller_title, seller_company, product_desc]):
        seller = SellerContext(
            name=seller_name,
            title=seller_title,
            company=seller_company,
            product_description=product_desc,
        )
    elif generate_briefs:
        st.warning("Fill in all 'About you' fields in the sidebar to generate AI briefs.")

    from config import get_settings
    settings = get_settings()
    settings.min_relationship_score = min_score

    with st.spinner("Fetching profile and searching network..."):
        try:
            with ReferralFinder() as finder:
                result = finder.run(linkedin_url.strip(), icp, seller=seller)
        except Exception as e:
            st.error(f"Error: {e}")
            st.stop()

    if not result.prospects:
        st.warning("No prospects found. Try lowering the minimum score or broadening your ICP.")
        st.stop()

    source = result.referral_source
    st.success(
        f"Found **{len(result.prospects)} prospects** from "
        f"**{source.full_name}**'s network "
        f"({len(result.companies_searched)} companies searched)"
    )

    # ── Generate AI briefs ─────────────────────────────────────────────────
    if generate_briefs and seller:
        with st.spinner(f"Generating AI briefs for {len(result.prospects)} prospects..."):
            gen = create_generator()
            result.prospects = gen.generate_batch(result.prospects, source, seller)

    # ── Display results ────────────────────────────────────────────────────
    for i, p in enumerate(result.prospects, 1):
        with st.expander(
            f"{i}. **{p.full_name}** · {p.title} @ {p.company}  "
            f"· Score: {p.relationship_score:.0f}",
            expanded=(i <= 3),
        ):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"**Company:** {p.company}")
                if p.company_size:
                    st.markdown(f"**Size:** {p.company_size}")
                if p.industry:
                    st.markdown(f"**Industry:** {p.industry}")
                if p.location:
                    st.markdown(f"**Location:** {p.location}")
                if p.linkedin_url:
                    st.markdown(f"[View LinkedIn Profile]({p.linkedin_url})")

            with col2:
                st.markdown("**Why they're warm:**")
                for sig in p.relationship_signals:
                    st.markdown(f"- {sig.label}: {sig.detail}")

            if p.narrative:
                st.divider()
                nc1, nc2, nc3 = st.columns(3)
                with nc1:
                    st.markdown("**About Them**")
                    st.write(p.narrative.about_them)
                with nc2:
                    st.markdown("**Why Them**")
                    st.write(p.narrative.why_them)
                with nc3:
                    st.markdown("**Suggested Message**")
                    st.code(p.narrative.suggested_message, language=None)

    # ── Download buttons ───────────────────────────────────────────────────
    st.divider()
    from report import export_csv, export_html
    col_a, col_b = st.columns(2)
    with col_a:
        st.download_button(
            "Download HTML report",
            data=export_html(result),
            file_name="referral-prospects.html",
            mime="text/html",
            use_container_width=True,
        )
    with col_b:
        st.download_button(
            "Download CSV",
            data=export_csv(result),
            file_name="referral-prospects.csv",
            mime="text/csv",
            use_container_width=True,
        )
