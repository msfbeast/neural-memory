#!/usr/bin/env python3
"""Test the marketplace functionality."""

import sys
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.marketplace.redactor import Redactor
from src.marketplace.cards import MemoryCard, PackCard
from src.marketplace.packs import PackManager
from src.capture.extractor import Engram


def test_redactor():
    """Test the redaction engine."""
    print("=" * 60)
    print("Testing Redactor")
    print("=" * 60)

    redactor = Redactor()

    # Test 1: API key redaction
    text1 = "My API key is sk-1234567890abcdef1234567890abcdef"
    redacted1, count1 = redactor.redact_text(text1)
    assert count1 > 0, f"Expected redaction, got {count1}"
    assert "sk-1234567890abcdef" not in redacted1, "API key not redacted"
    print(f"✓ API key redacted: {text1[:30]}... → {redacted1[:30]}...")

    # Test 2: Email redaction
    text2 = "Contact me at user@example.com for help"
    redacted2, count2 = redactor.redact_text(text2)
    assert count2 > 0, f"Expected redaction, got {count2}"
    assert "user@example.com" not in redacted2, "Email not redacted"
    print(f"✓ Email redacted: {text2[:30]}... → {redacted2[:30]}...")

    # Test 3: File path redaction
    text3 = "Read /Users/msfbeast/wiki/05-tools/neural-memory/README.md"
    redacted3, count3 = redactor.redact_text(text3)
    assert count3 > 0, f"Expected redaction, got {count3}"
    assert "/Users/msfbeast" not in redacted3, "File path not redacted"
    print(f"✓ File path redacted: {text3[:40]}... → {redacted3[:40]}...")

    # Test 4: GitHub token redaction
    text4 = "Token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghij"
    redacted4, count4 = redactor.redact_text(text4)
    assert count4 > 0, f"Expected redaction, got {count4}"
    assert "ghp_" not in redacted4, "GitHub token not redacted"
    print(f"✓ GitHub token redacted: {text4[:30]}... → {redacted4[:30]}...")

    # Test 5: Clean text (no redaction needed)
    text5 = "This is a normal sentence with no sensitive data"
    redacted5, count5 = redactor.redact_text(text5)
    assert count5 == 0, f"Expected no redaction, got {count5}"
    assert text5 == redacted5, "Clean text was modified"
    print(f"✓ Clean text unchanged: {text5}")

    print(f"\nAll {5} redaction tests passed!")


def test_cards():
    """Test memory and pack cards."""
    print("\n" + "=" * 60)
    print("Testing Cards")
    print("=" * 60)

    # Test MemoryCard
    card = MemoryCard(
        id="NM-20260516-abc123",
        title="Python debugging tip",
        statement="User prefers using pdb for debugging Python code",
        tags=["python", "debugging"],
        category="user_preference",
        type="behavioral",
        author="testuser",
        redacted=True,
        redaction_count=2,
    )

    card_dict = card.to_dict()
    assert card_dict["id"] == "NM-20260516-abc123"
    assert card_dict["redacted"] == True
    print(f"✓ MemoryCard serialized: {card_dict['id']}")

    card_restored = MemoryCard.from_dict(card_dict)
    assert card_restored.id == card.id
    assert card_restored.statement == card.statement
    print(f"✓ MemoryCard deserialized: {card_restored.id}")

    # Test PackCard
    pack = PackCard(
        id="pack-20260516-abc123",
        name="Python Debugging Pack",
        description="Common debugging patterns",
        cards=["NM-20260516-abc1", "NM-20260516-abc2"],
        tags=["python", "debugging"],
        author="testuser",
    )

    pack_dict = pack.to_dict()
    assert len(pack_dict["cards"]) == 2
    print(f"✓ PackCard serialized: {pack_dict['name']} ({len(pack_dict['cards'])} cards)")

    pack_restored = PackCard.from_dict(pack_dict)
    assert pack_restored.name == pack.name
    assert len(pack_restored.cards) == 2
    print(f"✓ PackCard deserialized: {pack_restored.name}")

    # Test Markdown output
    md = card.to_markdown()
    assert "Python debugging tip" in md
    assert "🔒" in md  # Redacted badge
    print(f"✓ MemoryCard Markdown output generated ({len(md)} chars)")

    pack_md = pack.to_markdown()
    assert "Python Debugging Pack" in pack_md
    assert "NM-20260516-abc1" in pack_md
    print(f"✓ PackCard Markdown output generated ({len(pack_md)} chars)")

    print(f"\nAll {4} card tests passed!")


def test_packs():
    """Test pack management."""
    print("\n" + "=" * 60)
    print("Testing PackManager")
    print("=" * 60)

    pack_manager = PackManager()

    # Create a test pack
    pack = pack_manager.create_pack(
        name="Test Pack",
        description="A test pack for verification",
        card_ids=["NM-20260516-abc1", "NM-20260516-abc2"],
        tags=["test", "verification"],
        author="testuser",
    )

    assert pack.id.startswith("pack-")
    print(f"✓ Pack created: {pack.id}")

    # Retrieve the pack
    retrieved = pack_manager.get_pack(pack.id)
    assert retrieved is not None
    assert retrieved.name == "Test Pack"
    assert len(retrieved.cards) == 2
    print(f"✓ Pack retrieved: {retrieved.name} ({len(retrieved.cards)} cards)")

    # List packs
    packs = pack_manager.list_packs()
    assert len(packs) > 0
    print(f"✓ Listed {len(packs)} pack(s)")

    # Export pack
    export_path = pack_manager.export_pack(pack.id)
    assert export_path is not None
    assert Path(export_path).exists()
    print(f"✓ Pack exported to: {export_path}")

    # Import pack
    import_data = pack.to_dict()
    imported = pack_manager.import_pack(import_data, author="importer")
    assert imported is not None
    assert imported.author == "importer"  # Author should be overridden
    print(f"✓ Pack imported: {imported.name} (author: {imported.author})")

    # Delete pack
    deleted = pack_manager.delete_pack(pack.id)
    assert deleted == True
    assert pack_manager.get_pack(pack.id) is None
    print(f"✓ Pack deleted: {pack.id}")

    print(f"\nAll {6} pack tests passed!")


def test_redact_engram():
    """Test redacting a full engram."""
    print("\n" + "=" * 60)
    print("Testing Engram Redaction")
    print("=" * 60)

    redactor = Redactor()

    # Create a test engram with sensitive data
    engram = Engram(
        id="NM-20260516-abc123",
        statement="Terminal command: cat /Users/msfbeast/.env && export API_KEY=sk-1234567890abcdef",
        rationale="User shared their API configuration",
        tags=["terminal", "api"],
        category="user_preference",
        type="behavioral",
        visibility="marketplace",
    )

    result = redactor.redact(engram)

    assert result.redacted_count > 0, f"Expected redaction, got {result.redacted_count}"
    assert "/Users/msfbeast" not in result.redacted_statement
    assert "sk-1234567890abcdef" not in result.redacted_statement
    print(f"✓ Engram redacted: {result.redacted_count} items redacted")
    print(f"  Original: {engram.statement[:60]}...")
    print(f"  Redacted: {result.redacted_statement[:60]}...")

    # Test is_safe
    safe_engram = Engram(
        id="NM-20260516-def456",
        statement="User prefers concise responses",
        tags=["preference"],
        category="user_preference",
        type="behavioral",
    )

    assert redactor.is_safe(safe_engram) == True
    print(f"✓ Safe engram detected (no redaction needed)")

    unsafe_engram = Engram(
        id="NM-20260516-ghi789",
        statement="API key: sk-1234567890abcdef",
        tags=["api"],
        category="api_quirk",
        type="terminological",
    )

    assert redactor.is_safe(unsafe_engram) == False
    print(f"✓ Unsafe engram detected (redaction needed)")

    print(f"\nAll {4} engram redaction tests passed!")


if __name__ == "__main__":
    try:
        test_redactor()
        test_cards()
        test_packs()
        test_redact_engram()

        print("\n" + "=" * 60)
        print("ALL MARKETPLACE TESTS PASSED! ✅")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
