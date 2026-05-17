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
# ---------------------------------------------------------------------------
# Import chain - order matters to avoid circular imports
# ---------------------------------------------------------------------------
from src.config import config
from src.capture.filters import CaptureDecision, EventCategory
from src.capture.extractor import Engram, Extractor
from src.storage.engrams import EngramStore
from src.storage.bm25 import BM25Index
from src.marketplace.redactor import Redactor
from src.marketplace.packs import PackManager, RecipeManager
from src.marketplace.client import MarketplaceClient

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
        "conventions": "Convention",
        "error_pattern": "Error Pattern",
        "error_patterns": "Error Pattern",
        "tool_discovery": "Tool Discovery",
        "project_convention": "Convention",
        "file_operation": "File Op",
        "config_change": "Config",
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
        start_date = st.date_input("From", value=None, key="sidebar_start_date")
    with col_d2:
        end_date = st.date_input("To", value=None, key="sidebar_end_date")

    st.markdown("---")

    # Actions
    if st.button("Refresh", use_container_width=True, key="sidebar_refresh"):
        for key in ["store", "bm25", "last_search", "selected_detail"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

    if st.button("Clear All Engrams", use_container_width=True, type="primary", key="sidebar_clear"):
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
            if st.button("Yes, Delete All", type="primary", use_container_width=True, key="dialog_delete_all"):
                for engram in store.get_all(limit=10000):
                    store.delete(engram.id)
                st.session_state.confirm_clear = False
                st.success("All engrams deleted!")
                for key in ["store", "bm25", "last_search", "selected_detail"]:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun()
        with col_b:
            if st.button("Cancel", use_container_width=True, key="dialog_cancel"):
                st.session_state.confirm_clear = False
                st.rerun()

# ---------------------------------------------------------------------------
# Main content
# ---------------------------------------------------------------------------
tab_overview, tab_search, tab_list, tab_detail, tab_marketplace, tab_sync = st.tabs([
    "Overview",
    "Search",
    "All Engrams",
    "Detail View",
    "Marketplace & Recipes",
    "PLUR Sync",
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
    col_m4.metric("Capture", "Active" if get_capture_enabled() else "Disabled")

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
        key="search_query",
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

            for rank, result in enumerate(results, 1):
                engram_id = result.get("id") if isinstance(result, dict) else result[0]
                score = result.get("score", 0) if isinstance(result, dict) else result[1]
                if not engram_id:
                    continue
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

    page = st.number_input("Page", min_value=1, value=1, step=1, key="list_page")
    per_page = st.selectbox("Per page", [10, 25, 50, 100], index=1, key="list_per_page")

    offset = (page - 1) * per_page
    all_engrams = store.get_all(limit=per_page, offset=offset)
    total_count = store.count()

    # Apply sidebar filters
    if selected_categories:
        all_engrams = [e for e in all_engrams if e.category in selected_categories]
    if selected_types:
        all_engrams = [e for e in all_engrams if e.type in selected_types]
    if selected_domain and selected_domain != "All":
        all_engrams = [e for e in all_engrams if e.domain == selected_domain]
    if start_date:
        from datetime import date as _date
        start_str = _date.isoformat(start_date)
        all_engrams = [e for e in all_engrams if e.created_at and e.created_at[:10] >= start_str]
    if end_date:
        from datetime import date as _date
        end_str = _date.isoformat(end_date)
        all_engrams = [e for e in all_engrams if e.created_at and e.created_at[:10] <= end_str]

    st.caption("Showing " + str(offset + 1) + "-" + str(min(offset + per_page, len(all_engrams))) + " of " + str(total_count) + " engrams")

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
                if st.button("Back to Search", use_container_width=True, key="detail_back"):
                    st.session_state.selected_detail = None
                    st.rerun()
            with col_del:
                if st.button("Delete This Engram", type="primary", use_container_width=True, key="detail_delete"):
                    store.delete(engram.id)
                    st.session_state.selected_detail = None
                    st.success("Engram deleted!")
                    st.rerun()
        else:
            st.error("Engram " + detail_id + " not found.")
            st.session_state.selected_detail = None
    else:
        st.subheader("Look up by ID")
        lookup_id = st.text_input("Engram ID", placeholder="Enter engram ID...", key="detail_lookup_id")
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
# Tab 5: Marketplace
# ---------------------------------------------------------------------------
with tab_marketplace:
    st.header("NeuralMemory Marketplace")
    st.caption("Share your knowledge. Discover what others have learned.")

    mp_tab_share, mp_tab_browse, mp_tab_my_shared, mp_tab_recipes = st.tabs([
        "Share Memory",
        "Browse Packs",
        "My Shared",
        "📦 Recipes",
    ])

    # ---- Share Memory ----
    with mp_tab_share:
        st.subheader("Share a Memory")
        st.markdown("Memories are **private by default**. Only share when you're comfortable with others seeing them.")

        col_s1, col_s2 = st.columns([2, 1])
        with col_s1:
            share_id = st.text_input("Engram ID", placeholder="NM-20260516-abc123", key="share_id")
        with col_s2:
            share_title = st.text_input("Title (optional)", placeholder="Auto-generated if empty", key="share_title")

        col_s3, col_s4 = st.columns(2)
        with col_s3:
            share_author = st.text_input("Author", value="anonymous", key="share_author")
        with col_s4:
            share_tags = st.text_input("Tags", placeholder="python, debugging", key="share_tags")

        if st.button("Share to Marketplace", type="primary", key="share_marketplace"):
            if not share_id:
                st.error("Please enter an engram ID.")
            else:
                client = MarketplaceClient()
                tag_list = [t.strip() for t in share_tags.split(",") if t.strip()] if share_tags else None
                result = client.share_memory(
                    engram_id=share_id,
                    title=share_title if share_title else None,
                    author=share_author,
                    tags=tag_list,
                )
                if result.get("success"):
                    st.success(result.get("message", "Memory shared!"))
                    if result.get("redacted"):
                        st.warning(f"🔒 {result.get('redaction_count', 0)} sensitive items were auto-redacted.")
                else:
                    st.error(result.get("error", "Failed to share."))

        # Preview redaction
        st.markdown("---")
        st.subheader("Redaction Preview")
        st.markdown("Paste text to see how sensitive data would be redacted:")
        preview_text = st.text_area("", height=100, placeholder="Paste text here...", key="redaction_preview")
        if preview_text:
            redactor = Redactor()
            redacted, count = redactor.redact_text(preview_text)
            if count > 0:
                st.warning(f"🔒 {count} sensitive item(s) detected and redacted:")
                st.code(redacted, language="text")
            else:
                st.success("✅ No sensitive data detected.")

    # ---- Browse Packs ----
    with mp_tab_browse:
        st.subheader("Browse Memory Packs")

        col_b1, col_b2, col_b3 = st.columns([2, 1, 1])
        with col_b1:
            browse_query = st.text_input("Search", placeholder="Search packs...", key="browse_query")
        with col_b2:
            browse_tags = st.text_input("Tags", placeholder="python, api", key="browse_tags")
        with col_b3:
            browse_limit = st.number_input("Limit", min_value=5, max_value=50, value=20, key="browse_limit")

        if st.button("Search", use_container_width=True, key="browse_search"):
            client = MarketplaceClient()
            tag_list = [t.strip() for t in browse_tags.split(",") if t.strip()] if browse_tags else None
            packs = client.browse_packs(
                query=browse_query if browse_query else None,
                tags=tag_list,
                limit=browse_limit,
            )
            st.session_state.browse_results = packs
        else:
            packs = st.session_state.get("browse_results", [])

        if packs:
            st.success(f"Found {len(packs)} pack(s)")
            for pack in packs:
                with st.expander(f"📦 {pack.name} ({len(pack.cards)} memories)", expanded=False):
                    st.markdown(pack.description)
                    st.markdown(f"**Author:** {pack.author} | **Rating:** ⭐ {pack.rating:.1f} | **Downloads:** 📥 {pack.downloads}")
                    st.markdown(" ".join(f"`{t}`" for t in pack.tags))
                    if st.button("Download Pack", key=f"dl_pack_{pack.id}", type="primary"):
                        client = MarketplaceClient()
                        result = client.download_pack(pack.id)
                        if result.get("success"):
                            st.success(result.get("message", "Pack installed!"))
                        else:
                            st.error(result.get("error", "Failed to download."))
        else:
            st.info("No packs found. Try a different search or check back later.")

    # ---- My Shared ----
    with mp_tab_my_shared:
        st.subheader("My Shared Memories")

        if st.button("Refresh", use_container_width=True, key="my_shared_refresh"):
            client = MarketplaceClient()
            st.session_state.my_shared = client.list_shared()

        shared = st.session_state.get("my_shared", [])

        if shared:
            st.success(f"You've shared {len(shared)} memory(ies)")
            for card in shared:
                if not card:
                    continue
                title = card.get("title", card.get("id", "Unknown"))
                statement = card.get("statement", "")
                etype = card.get("type", "N/A")
                ecategory = card.get("category", "N/A")
                redacted = card.get("redacted", False)
                redaction_count = card.get("redaction_count", 0)
                tags = card.get("tags", [])
                card_id = card.get("id", "")
                with st.expander(f"🔒 {title}", expanded=False):
                    st.markdown(statement)
                    st.markdown(f"**Type:** {etype} | **Category:** {ecategory}")
                    if redacted:
                        st.warning(f"🔒 Redacted ({redaction_count} items)")
                    st.markdown(" ".join(f"`{t}`" for t in tags))
                    if st.button("Unshare", key=f"unshare_{card_id}", type="primary"):
                        client = MarketplaceClient()
                        result = client.unshare_memory(card_id)
                        if result.get("success"):
                            st.success(result.get("message", "Memory unshared."))
                            del st.session_state.my_shared
                            st.rerun()
                        else:
                            st.error(result.get("error", "Failed to unshare."))
        else:
            st.info("You haven't shared any memories yet. Go to the 'Share Memory' tab to get started!")

    # ---- Recipes ----
    with mp_tab_recipes:
        st.subheader("Installable Recipes")
        st.caption("Curated setups — install a complete configuration with one click.")

        rtab_browse, rtab_create = st.tabs(["Browse Recipes", "Create Recipe"])

        # --- Browse Recipes ---
        with rtab_browse:
            col_r1, col_r2, col_r3 = st.columns([2, 1, 1])
            with col_r1:
                r_query = st.text_input("Search", placeholder="Search recipes...", key="recipe_browse_query")
            with col_r2:
                r_category = st.selectbox(
                    "Category",
                    options=["All", "tools", "workflows", "ai_setup", "automation", "misc"],
                    index=0,
                    key="recipe_browse_category",
                )
            with col_r3:
                r_difficulty = st.selectbox(
                    "Difficulty",
                    options=["All", "beginner", "intermediate", "advanced"],
                    index=0,
                    key="recipe_browse_difficulty",
                )

            if st.button("Search", use_container_width=True, key="recipe_search"):
                rm = RecipeManager()
                recipes = rm.search_recipes(
                    query=r_query if r_query != "" else None,
                    tags=None,
                    category=r_category if r_category != "All" else None,
                )
                st.session_state.recipe_results = [
                    {
                        "id": r.id,
                        "name": r.name,
                        "description": r.description,
                        "category": r.category,
                        "difficulty": r.difficulty,
                        "estimated_minutes": r.estimated_minutes,
                        "author": r.author,
                        "tags": r.tags,
                        "downloads": r.downloads,
                        "rating": r.rating,
                        "verified": r.verified,
                        "instructions": r.instructions,
                    }
                    for r in recipes
                ]

            recipes = st.session_state.get("recipe_results", [])

            if recipes:
                st.success(f"Found {len(recipes)} recipe(s)")
                for recipe in recipes:
                    diff_emoji = {"beginner": "🟢", "intermediate": "🟡", "advanced": "🔴"}.get(recipe.get("difficulty", ""), "⚪")
                    time_emoji = "⏱️"
                    with st.expander(f"{diff_emoji} {recipe.get('name', 'Unknown')} ({recipe.get('estimated_minutes', 0)} min)", expanded=False):
                        st.markdown(recipe.get("description", ""))
                        st.markdown(
                            f"**Author:** {recipe.get('author', 'anonymous')} | "
                            f"**Difficulty:** {recipe.get('difficulty', 'N/A')} | "
                            f"**Downloads:** 📥 {recipe.get('downloads', 0)} | "
                            f"**Rating:** ⭐ {recipe.get('rating', 0):.1f}"
                        )
                        tags = recipe.get("tags", [])
                        if tags:
                            st.markdown(" ".join(f"`{t}`" for t in tags))
                        if st.button("Install Recipe", key=f"install_recipe_{recipe.get('id', '')}", type="primary"):
                            rm = RecipeManager()
                            result = rm.install_recipe(recipe.get("id", ""))
                            if result.get("success"):
                                st.success(f"✅ Recipe installed: {recipe.get('name', '')}")
                                st.markdown("**Instructions:**")
                                st.info(result.get("instructions", ""))
                            else:
                                st.error(result.get("error", "Failed to install."))
            else:
                st.info("No recipes found. Try a different search or create your own!")

        # --- Create Recipe ---
        with rtab_create:
            st.subheader("Create a Recipe")
            st.markdown("Bundle related memories into an installable setup with step-by-step instructions.")

            col_c1, col_c2 = st.columns(2)
            with col_c1:
                recipe_name = st.text_input("Recipe Name", placeholder="e.g., Local AI Supercomputer", key="recipe_create_name")
                recipe_desc = st.text_area("Description", height=80, placeholder="What does this recipe set up?", key="recipe_create_desc")
            with col_c2:
                recipe_category = st.selectbox(
                    "Category",
                    options=["tools", "workflows", "ai_setup", "automation", "misc"],
                    index=0,
                    key="recipe_create_category",
                )
                recipe_difficulty = st.selectbox(
                    "Difficulty",
                    options=["beginner", "intermediate", "advanced"],
                    index=0,
                    key="recipe_create_difficulty",
                )
                recipe_minutes = st.number_input("Est. Minutes", min_value=1, value=10, key="recipe_create_minutes")

            recipe_memories = st.text_area(
                "Memory IDs",
                placeholder="NM-20260516-abc123, NM-20260516-def456\n(Comma-separated engram IDs)",
                height=100,
                key="recipe_create_memories",
            )
            recipe_instructions = st.text_area(
                "Setup Instructions",
                placeholder="Step-by-step instructions for installing this recipe:\n\n1. Install dependencies...\n2. Run setup script...\n3. Configure...",
                height=200,
                key="recipe_create_instructions",
            )
            recipe_deps = st.text_area(
                "Dependencies",
                placeholder="e.g., whisper.cpp, git, ffmpeg",
                key="recipe_create_deps",
            )
            recipe_tags = st.text_input("Tags", placeholder="ai, local, whisper", key="recipe_create_tags")
            recipe_author = st.text_input("Author", value="anonymous", key="recipe_create_author")

            if st.button("Create Recipe", type="primary", key="create_recipe"):
                if not recipe_name or not recipe_memories or not recipe_instructions:
                    st.error("Name, memories, and instructions are required.")
                else:
                    rm = RecipeManager()
                    result = rm.create_recipe(
                        name=recipe_name,
                        description=recipe_desc,
                        memories=[m.strip() for m in recipe_memories.split(",") if m.strip()],
                        instructions=recipe_instructions,
                        dependencies=[d.strip() for d in recipe_deps.split(",") if d.strip()] if recipe_deps else [],
                        tags=[t.strip() for t in recipe_tags.split(",") if t.strip()] if recipe_tags else None,
                        category=recipe_category,
                        difficulty=recipe_difficulty,
                        estimated_minutes=recipe_minutes,
                        author=recipe_author,
                    )
                    st.success(f"✅ Recipe created: {recipe_name}")

# ---------------------------------------------------------------------------
# Tab 6: PLUR Sync
# ---------------------------------------------------------------------------
with tab_sync:
    st.header("PLUR Sync")

    from src.bridge.consumer import PLURConsumer
    from src.bridge.plur import PLURBridge

    consumer = PLURConsumer()
    bridge = PLURBridge()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        pending = consumer.get_pending_count()
        st.metric("Pending Markers", pending)
    with col2:
        sync_config = bridge.get_sync_config()
        st.metric("Sync Enabled", "Yes" if sync_config["sync_enabled"] else "No")
    with col3:
        st.metric("Sync Direction", sync_config.get("sync_direction", "N/A"))

    st.divider()

    # Pending markers detail
    st.subheader("Pending Sync Queue")
    markers = consumer.get_pending_markers()

    if not markers:
        st.info("No pending markers. All engrams synced or none captured.")
    else:
        for i, m in enumerate(markers, 1):
            with st.expander(f"{i}. {m.get('nm_id', '?')[:20]}..."):
                st.text(f"Statement: {m.get('statement', '')[:200]}")
                st.text(f"Scope: {m.get('scope', 'global')}")
                st.text(f"Type: {m.get('type', 'behavioral')}")
                st.text(f"Domain: {m.get('domain', '')}")
                st.text(f"Tags: {', '.join(m.get('tags', []))}")
                st.text(f"Rationale: {m.get('rationale', '')[:150]}")

    st.divider()

    # Actions
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        if st.button("🚀 Push All to PLUR", type="primary", key="push_all"):
            results = consumer.process_all()
            success = sum(1 for r in results if r.success)
            failed = sum(1 for r in results if not r.success)
            st.success(f"Pushed {success}/{len(results)} engrams to PLUR")
            if failed > 0:
                st.warning(f"{failed} failed — retries recommended")
            st.rerun()

    with col_b:
        if st.button("🔄 Dry Run", key="dry_run"):
            markers = consumer.get_pending_markers()
            if markers:
                st.info(f"{len(markers)} markers would be pushed")
                for m in markers[:3]:
                    st.text(f"  - {m.get('statement', '')[:80]}...")
            else:
                st.info("No markers to push")

    with col_c:
        if st.button("🗑 Clear All Markers", key="clear_all"):
            count = consumer.clear_pending()
            st.success(f"Cleared {count} markers")
            st.rerun()

    st.divider()

    # Push queue (fallback)
    st.subheader("Push Queue (PostToolUse Hook)")
    push_queue_path = consumer.marker_path.parent / "plur_sync_push_pending.jsonl"
    if push_queue_path.exists():
        with open(push_queue_path) as f:
            queue_lines = [l.strip() for l in f if l.strip()]
        st.info(f"{len(queue_lines)} engrams in push queue (waiting for agent hook)")
        for i, line in enumerate(queue_lines[:5], 1):
            try:
                entry = __import__('json').loads(line)
                st.text(f"  {i}. {entry.get('statement', '')[:80]}...")
            except:
                st.text(f"  {i}. [corrupt entry]")
    else:
        st.info("Push queue is empty")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------
st.markdown("---")
st.caption("NeuralMemory Dashboard - Auto-captured knowledge from Hermes Agent sessions")
