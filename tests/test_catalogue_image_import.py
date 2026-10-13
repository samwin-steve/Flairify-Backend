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
