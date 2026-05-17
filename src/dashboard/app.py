"""NeuralMemory Dashboard - Streamlit web app.

View, search, filter, and manage engrams captured from Hermes Agent sessions.
Features:
  - Overview stats (total, by type, by category)
  - Full-text BM25 search
  - Filter by category, type, domain, date range
  - Detail view with all engram fields
  - Delete engrams
  - Live capture status indicator

Run: streamlit run src/dashboard/app.py
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import streamlit as st
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Import chain - order matters to avoid circular imports
# 1. config (no deps)
# 2. filters (depends on config)
# 3. extractor (depends on filters)
# 4. engrams (depends on config + extractor)
# 5. bm25 (depends on config)
# ---------------------------------------------------------------------------
from src.config import config
from src.capture.filters import CaptureDecision, EventCategory
from src.capture.extractor import Engram, Extractor
from src.storage.engrams import EngramStore
from src.storage.bm25 import BM25Index

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_store():
    """Lazy-load the engram store."""
    if "store" not in st.session_state:
        st.session_state.store = EngramStore()
    return st.session_state.store

def get_bm25():
    """Lazy-load the BM25 index."""
    if "bm25" not in st.session_state:
        st.session_state.bm25 = BM25Index()
    return st.session_state.bm25

def get_capture_enabled():
    """Check capture status from config."""
    return config.get("capture.enabled", True)

def format_date(dt_str):
    """Format ISO date string for display."""
    if not dt_str:
        return "N/A"
    try:
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, AttributeError):
        return dt_str

def confidence_badge(confidence):
    """Return a colored badge for confidence level."""
    if confidence >= 0.9:
        return "High"
    elif confidence >= 0.7:
        return "Medium"
    else:
        return "Low"

def type_tag(etype):
    """Return an emoji tag for engram type."""
    tags = {
        "behavioral": "Behavioral",
        "terminological": "Terminological",
        "procedural": "Procedural",
        "architectural": "Architectural",
    }
    return tags.get(etype, etype)

def category_badge(category):
    """Return a colored badge for category."""
    badges = {
        "user_correction": "Correction",
        "debug_breakthrough": "Debug",
        "new_workflow": "Workflow",
        "architecture_decision": "Architecture",
        "api_quirk": "API Quirk",
        "user_preference": "Preference",
        "budget_constraint": "Budget",
        "project_convention": "Convention",
        "error_pattern": "Error Pattern",
        "tool_discovery": "Tool Discovery",
    }
    return badges.get(category, category)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="NeuralMemory Dashboard",
    page_icon="G",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.title("NeuralMemory")
    st.markdown("Agent Session Memory System")
    st.markdown("---")

    # Capture status
    try:
        capture_enabled = get_capture_enabled()
        st.metric("Capture Status", "Enabled" if capture_enabled else "Disabled", delta=None)
    except Exception:
        st.metric("Capture Status", "Error", delta=None)

    st.markdown("---")

    # Filters
    st.subheader("Filters")

    store = get_store()
    stats = store.stats()
    categories = sorted(stats.get("by_category", {}).keys())

    selected_categories = st.multiselect(
        "Category",
        options=categories,
        default=[],
        help="Filter by engram category",
    )

    types = sorted(stats.get("by_type", {}).keys())
    selected_types = st.multiselect(
        "Type",
        options=types,
        default=[],
        help="Filter by engram type",
    )

    domains = []
    all_engrams = store.get_all(limit=1000)
    if all_engrams:
        domains = sorted(set(e.domain for e in all_engrams if e.domain))
    selected_domain = st.selectbox(
        "Domain",
        options=["All"] + domains,
        index=0,
        help="Filter by domain",
    )

    st.markdown("**Date Range**")
    col_d1, col_d2 = st.columns(2)
    with col_d1:
        start_date = st.date_input("From", value=None)
    with col_d2:
        end_date = st.date_input("To", value=None)

    st.markdown("---")

    # Actions
    if st.button("Refresh", use_container_width=True):
        for key in ["store", "bm25", "last_search", "selected_detail"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    if st.button("Clear All Engrams", use_container_width=True, type="primary"):
        st.session_state.confirm_clear = True
        st.rerun()

    st.markdown("---")
    st.caption("Database: " + store.db_path)

# ---------------------------------------------------------------------------
# Confirmation modal
# ---------------------------------------------------------------------------
if st.session_state.get("confirm_clear"):
    with st.dialog("Confirm Clear All Engrams"):
        st.warning("This will delete ALL engrams. This cannot be undone!")
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Yes, Delete All", type="primary", use_container_width=True):
                for engram in store.get_all(limit=10000):
                    store.delete(engram.id)
                st.session_state.confirm_clear = False
                st.success("All engrams deleted!")
                for key in ["store", "bm25", "last_search", "selected_detail"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        with col_b:
            if st.button("Cancel", use_container_width=True):
                st.session_state.confirm_clear = False
                st.rerun()

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
tab_overview, tab_search, tab_list, tab_detail = st.tabs([
    "Overview",
    "Search",
    "All Engrams",
    "Detail View",
])

# ---------------------------------------------------------------------------
# Tab 1: Overview
# ---------------------------------------------------------------------------
with tab_overview:
    st.header("Overview")

    stats = store.stats()
    total = stats["total"]

    # Top metrics
    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Total Engrams", total)
    col_m2.metric("Types", len(stats.get("by_type", {})))
    col_m3.metric("Categories", len(stats.get("by_category", {})))
    col_m4.metric("Capture", "Active" if store.count() > 0 else "Idle")

    st.markdown("---")

    # Distribution charts
    col_c1, col_c2 = st.columns(2)

    with col_c1:
        st.subheader("By Type")
        by_type = stats.get("by_type", {})
        if by_type:
            type_labels = [type_tag(t) for t in by_type]
            type_values = list(by_type.values())
            st.bar_chart(dict(zip(type_labels, type_values)))
        else:
            st.info("No engrams captured yet.")

    with col_c2:
        st.subheader("By Category")
        by_cat = stats.get("by_category", {})
        if by_cat:
            cat_labels = [category_badge(c) for c in by_cat]
            cat_values = list(by_cat.values())
            st.bar_chart(dict(zip(cat_labels, cat_values)))
        else:
            st.info("No engrams captured yet.")

    st.markdown("---")

    # Recent engrams
    st.subheader("Recent Engrams")
    recent = store.get_all(limit=5)
    if recent:
        for e in recent:
            with st.expander(category_badge(e.category) + " " + e.statement[:80] + "...", expanded=False):
                st.markdown("**Type:** " + type_tag(e.type))
                st.markdown("**Domain:** " + (e.domain or "N/A"))
                st.markdown("**Confidence:** " + confidence_badge(e.confidence))
                st.markdown("**Created:** " + format_date(e.created_at))
                st.markdown("**Statement:**\n\n" + e.statement)
                if e.rationale:
                    st.markdown("**Rationale:**\n\n" + e.rationale)
                if e.tags:
                    st.markdown("**Tags:** " + ", ".join(e.tags))
    else:
        st.info("No engrams yet. Start a session with capture enabled to collect knowledge.")

# ---------------------------------------------------------------------------
# Tab 2: Search
# ---------------------------------------------------------------------------
with tab_search:
    st.header("Search Engrams")

    query = st.text_input(
        "Search query",
        placeholder="Type keywords to search engrams...",
        key="search_input",
    )

    if query and query != st.session_state.get("last_search", ""):
        st.session_state.last_search = query
        st.session_state.search_results = None
        st.session_state.selected_detail = None

    if query:
        bm25 = get_bm25()
        results = bm25.search(query, limit=50)

        if results:
            st.success("Found " + str(len(results)) + " result(s)")

            for rank, (engram_id, score) in enumerate(results, 1):
                engram = store.get(engram_id)
                if engram:
                    title = "#" + str(rank) + " [" + str(round(score, 2)) + "] " + category_badge(engram.category) + " " + engram.statement[:100]
                    with st.expander(title, expanded=(rank <= 3)):
                        col_e1, col_e2, col_e3 = st.columns(3)
                        with col_e1:
                            st.markdown("**Type:** " + type_tag(engram.type))
                        with col_e2:
                            st.markdown("**Confidence:** " + confidence_badge(engram.confidence))
                        with col_e3:
                            st.markdown("**Created:** " + format_date(engram.created_at))

                        st.markdown("**Domain:** " + (engram.domain or "N/A"))
                        st.markdown("**Category:** " + category_badge(engram.category))
                        st.markdown("**Statement:**\n\n" + engram.statement)
                        if engram.rationale:
                            st.markdown("**Rationale:**\n\n" + engram.rationale)
                        if engram.tags:
                            st.markdown("**Tags:** " + ", ".join(engram.tags))

                        col_btn1, col_btn2, col_btn3 = st.columns([1, 1, 1])
                        with col_btn1:
                            if st.button("View Full", key="view_" + engram.id, use_container_width=True):
                                st.session_state.selected_detail = engram_id
                                st.rerun()
                        with col_btn2:
                            if st.button("Delete", key="del_" + engram.id, use_container_width=True):
                                store.delete(engram.id)
                                st.session_state.search_results = None
                                st.session_state.last_search = ""
                                st.success("Deleted engram " + engram.id)
                                st.rerun()
        else:
            st.info("No results found. Try different keywords.")
    else:
        st.info("Enter a search query to find engrams.")

# ---------------------------------------------------------------------------
# Tab 3: All Engrams
# ---------------------------------------------------------------------------
with tab_list:
    st.header("All Engrams")

    page = st.number_input("Page", min_value=1, value=1, step=1)
    per_page = st.selectbox("Per page", [10, 25, 50, 100], index=1)

    offset = (page - 1) * per_page
    all_engrams = store.get_all(limit=per_page, offset=offset)
    total_count = store.count()

    st.caption("Showing " + str(offset + 1) + "-" + str(min(offset + per_page, total_count)) + " of " + str(total_count) + " engrams")

    if all_engrams:
        for engram in all_engrams:
            stmt_preview = engram.statement[:100]
            if len(engram.statement) > 100:
                stmt_preview += "..."
            title = category_badge(engram.category) + " " + type_tag(engram.type) + " " + stmt_preview
            with st.expander(title, expanded=False):
                col_l1, col_l2, col_l3 = st.columns(3)
                with col_l1:
                    st.markdown("**Type:** " + type_tag(engram.type))
                    st.markdown("**Domain:** " + (engram.domain or "N/A"))
                with col_l2:
                    st.markdown("**Confidence:** " + confidence_badge(engram.confidence))
                    st.markdown("**Category:** " + category_badge(engram.category))
                with col_l3:
                    st.markdown("**Created:** " + format_date(engram.created_at))
                    st.markdown("**Source:** " + (engram.source_tool or "N/A"))

                st.markdown("**Statement:**\n\n" + engram.statement)
                if engram.rationale:
                    st.markdown("**Rationale:**\n\n" + engram.rationale)
                if engram.tags:
                    st.markdown("**Tags:** " + ", ".join(engram.tags))
                if engram.session_id:
                    st.markdown("**Session:** " + engram.session_id)

                if st.button("Delete", key="list_del_" + engram.id, use_container_width=True):
                    store.delete(engram.id)
                    st.success("Deleted engram " + engram.id)
                    st.rerun()
    else:
        st.info("No engrams found.")

# ---------------------------------------------------------------------------
# Tab 4: Detail View
# ---------------------------------------------------------------------------
with tab_detail:
    st.header("Engram Detail")

    detail_id = st.session_state.get("selected_detail")

    if detail_id:
        engram = store.get(detail_id)
        if engram:
            st.markdown("**ID:** " + engram.id)
            st.markdown("**Type:** " + type_tag(engram.type))
            st.markdown("**Category:** " + category_badge(engram.category))
            st.markdown("**Domain:** " + (engram.domain or "N/A"))
            st.markdown("**Scope:** " + engram.scope)
            st.markdown("**Confidence:** " + confidence_badge(engram.confidence))
            st.markdown("**Visibility:** " + engram.visibility)
            st.markdown("**Source Tool:** " + (engram.source_tool or "N/A"))
            if engram.session_id:
                st.markdown("**Session ID:** " + engram.session_id)
            st.markdown("**Created:** " + format_date(engram.created_at))
            st.markdown("**Updated:** " + format_date(engram.updated_at))

            st.markdown("---")
            st.markdown("**Statement:**")
            st.markdown(engram.statement)

            if engram.rationale:
                st.markdown("---")
                st.markdown("**Rationale:**")
                st.markdown(engram.rationale)

            if engram.tags:
                st.markdown("---")
                st.markdown("**Tags:**")
                for tag in engram.tags:
                    st.markdown("- " + tag)

            st.markdown("---")
            col_back, col_del = st.columns(2)
            with col_back:
                if st.button("Back to Search", use_container_width=True):
                    st.session_state.selected_detail = None
                    st.rerun()
            with col_del:
                if st.button("Delete This Engram", type="primary", use_container_width=True):
                    store.delete(engram.id)
                    st.session_state.selected_detail = None
                    st.success("Engram deleted!")
                    st.rerun()
        else:
            st.error("Engram " + detail_id + " not found.")
            st.session_state.selected_detail = None
    else:
        st.subheader("Look up by ID")
        lookup_id = st.text_input("Engram ID", placeholder="Enter engram ID...")
        if lookup_id:
            engram = store.get(lookup_id)
            if engram:
                st.session_state.selected_detail = lookup_id
                st.rerun()
            else:
                st.error("Engram " + lookup_id + " not found.")
        else:
            st.info("Select an engram from Search or All Engrams tabs, or enter an ID above.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption("NeuralMemory Dashboard - Auto-captured knowledge from Hermes Agent sessions")
