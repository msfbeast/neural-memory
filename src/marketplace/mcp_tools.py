"""MCP tools for marketplace operations."""

from typing import Optional

from src.marketplace.client import MarketplaceClient


def neural_memory_share(
    engram_id: str,
    title: Optional[str] = None,
    author: str = "anonymous",
    tags: str = "",
) -> str:
    """Share a memory to the marketplace.

    Args:
        engram_id: The engram ID to share
        title: Optional custom title (auto-generated if not provided)
        author: Author name (default: anonymous)
        tags: Comma-separated tags to add to the card

    Returns:
        JSON status of the share operation
    """
    client = MarketplaceClient()

    # Parse tags
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    result = client.share_memory(
        engram_id=engram_id,
        title=title,
        author=author,
        tags=tag_list,
    )

    import json
    return json.dumps(result, indent=2)


def neural_memory_unshare(engram_id: str) -> str:
    """Remove a memory from the marketplace.

    Args:
        engram_id: The engram ID to unshare

    Returns:
        JSON status of the unshare operation
    """
    client = MarketplaceClient()
    result = client.unshare_memory(engram_id)

    import json
    return json.dumps(result, indent=2)


def neural_memory_browse_packs(
    query: str = "",
    tags: str = "",
    limit: int = 20,
) -> str:
    """Browse available memory packs.

    Args:
        query: Search query (optional)
        tags: Comma-separated tags to filter by (optional)
        limit: Maximum number of results (default: 20)

    Returns:
        JSON list of available packs
    """
    client = MarketplaceClient()

    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    packs = client.browse_packs(
        query=query if query else None,
        tags=tag_list,
        limit=limit,
    )

    import json
    return json.dumps([p.to_dict() for p in packs], indent=2)


def neural_memory_download_pack(pack_id: str) -> str:
    """Download and install a memory pack.

    Args:
        pack_id: The pack ID to download

    Returns:
        JSON result of the download operation
    """
    client = MarketplaceClient()
    result = client.download_pack(pack_id)

    import json
    return json.dumps(result, indent=2)


def neural_memory_list_shared() -> str:
    """List memories I've shared to the marketplace.

    Returns:
        JSON list of shared memories
    """
    client = MarketplaceClient()
    shared = client.list_shared()

    import json
    return json.dumps(shared, indent=2)


def neural_memory_create_pack(
    name: str,
    description: str,
    card_ids: str,
    tags: str = "",
    author: str = "anonymous",
) -> str:
    """Create a pack from local memory cards.

    Args:
        name: Pack name
        description: Pack description
        card_ids: Comma-separated engram IDs to include
        tags: Comma-separated tags for the pack
        author: Author name (default: anonymous)

    Returns:
        JSON result of the pack creation
    """
    client = MarketplaceClient()
    card_id_list = [c.strip() for c in card_ids.split(",") if c.strip()]
    tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

    pack = client.pack_manager.create_pack(
        name=name,
        description=description,
        card_ids=card_id_list,
        tags=tag_list,
        author=author,
    )

    import json
    return json.dumps(pack.to_dict(), indent=2)
