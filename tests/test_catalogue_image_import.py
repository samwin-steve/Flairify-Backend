import pytest

from app.catalogue.image_import import PhotoListing, product_id, target_category, visual_only


def listing(**changes):
    return dict(
        usable=True,
        name="Green Blazer",
        category="jacket",
        colour="green",
        pattern="solid",
        description="Notched lapels",
        bbox=[200, 100, 700, 800],
        confidence=0.9,
        uncertainty=[],
        **changes,
    )


def test_low_confidence_or_invalid_evidence_cannot_publish():
    base = listing()
    for changes in (
        {"bbox": [200, 100, 1100, 800]},
        {"bbox": [700, 100, 200, 800]},
        {"confidence": 0.5},
        {"category": "unknown"},
    ):
        with pytest.raises(ValueError):
            PhotoListing.model_validate({**base, **changes})
    assert not PhotoListing.model_validate({**base, "usable": False, "confidence": 0.4}).usable


def test_file_identity_is_independent_of_folder_and_filename():
    assert product_id("file-one") == product_id("file-one")
    assert product_id("file-one") != product_id("file-two")
    assert target_category("womens-bags") == "bag"
    assert target_category("mens-wedding-shoes") == "shoes"
    assert target_category("zara-benito-antonio") is None


def test_image_does_not_establish_material_in_title_or_description():
    result = visual_only(
        PhotoListing.model_validate(
            {
                **listing(),
                "name": "Brown Leather Bag",
                "category": "bag",
                "description": "Made of genuine leather. Two zip pockets are visible.",
            }
        )
    )
    assert result.name == "Brown Bag"
    assert result.description == "Two zip pockets are visible."
    assert result.uncertainty


def test_generated_listing_text_cannot_become_retailer_material_evidence():
    from app.catalogue.enrichment import validate
    from app.catalogue.schema import Analysis, Tag

    product = {
        "name": "Blue Cotton Shirt",
        "category": "top",
        "description": "",
        "attributes": {"description_source": "gemini_visual"},
        "variants": [],
    }
    result = Analysis(
        image_quality="adequate",
        image_matches_product=True,
        tags=[
            Tag(
                field="primary_colour",
                value="blue",
                confidence=0.98,
                source="seller",
                evidence="Blue",
                source_field="name",
            ),
            Tag(
                field="fabric",
                value="cotton",
                confidence=0.98,
                source="seller",
                evidence="Cotton",
                source_field="name",
            ),
        ],
    )
    tags, issues, unknown = validate(result, product, True)
    assert len(tags) == 2 and all(t.source == "visual" and t.confidence <= 0.9 for t in tags)
    assert "fabric" in unknown and "fabric:physical_claim_without_seller_evidence" in issues
