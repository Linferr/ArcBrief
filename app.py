"""Streamlit dev UI (deprecated). Prefer Next.js frontend."""

import streamlit as st

from foreign_query_agent import QueryAgent, Settings

st.set_page_config(page_title="ArcBrief Dev UI", layout="wide")

st.markdown("# ArcBrief Dev UI")
st.markdown("This Streamlit UI is **deprecated**. Use the Next.js frontend instead.")
st.markdown("If you still want a quick sanity check, you can run a single research query below.")

query = st.text_input("Research query", value="AI policy updates in US and EU")
run = st.button("Run Query Agent")

if run:
    settings = Settings(output_dir="outputs")
    agent = QueryAgent(settings)
    report = agent.research(query)
    st.markdown("## Report")
    st.write(report)
