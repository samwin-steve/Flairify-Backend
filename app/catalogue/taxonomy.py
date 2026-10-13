"""Controlled vocabulary. Bump TAXONOMY_VERSION when meanings or values change."""

SCHEMA_VERSION = "1"
TAXONOMY_VERSION = "1"
PROMPT_VERSION = "1"

COLOURS = "black white ivory cream beige brown tan grey navy blue green olive yellow orange red pink purple burgundy gold silver multicolour"
GARMENTS = "shirt t_shirt polo blouse tunic kurta kurti sweater sweatshirt hoodie trousers chinos jeans leggings shorts skirt dress saree jumpsuit blazer jacket coat cardigan waistcoat"
FOOTWEAR = "sneakers running_shoes loafers flats sandals heels boots formal_shoes slippers"
ACCESSORIES = "belt scarf sunglasses watch jewellery tote handbag backpack clutch"

VOCAB = {
    "category": "top bottom dress jacket shoes bag accessory",
    "subcategory": f"{GARMENTS} {FOOTWEAR} {ACCESSORIES}",
    "fabric": "cotton linen silk wool polyester viscose rayon nylon denim leather suede satin velvet chiffon georgette elastane knit blend",
    "fit": "slim regular relaxed oversized fitted straight",
    "silhouette": "straight a_line flared tapered wide_leg bodycon wrap fit_and_flare boxy structured flowing longline cropped",
    "neckline": "crew v_neck scoop square boat halter sweetheart off_shoulder collar mandarin_collar hooded high_neck",
    "sleeve_length": "sleeveless cap short elbow three_quarter long",
    "pattern": "solid striped checked floral geometric abstract polka_dot graphic paisley colour_block textured animal_print",
    "primary_colour": COLOURS,
    "secondary_colour": COLOURS,
    "shade": "light dark pastel muted bright jewel_tone earthy warm cool metallic",
    "print": "floral botanical geometric abstract paisley animal slogan logo ethnic polka_dot camouflage",
    "design_detail": "buttons zip pockets pleats ruffles embroidery lace sequins embellishment contrast_trim cutout slit tie_waist belt draping gathered ribbed distressed cuffed lapels open_front platform block_heel stiletto flat_sole ankle_strap laces buckle woven quilted",
    "occasion": "wedding party office casual_outing travel festival date_night workout formal_event",
    "weather": "warm_weather cool_weather cold_weather transitional indoor",
    "breathability": "breathable low_breathability",
    "weight": "lightweight heavyweight",
    "stretch": "stretch non_stretch",
    "layering": "base_layer mid_layer outer_layer standalone",
    "style": "minimalist formal smart_casual streetwear vintage bohemian contemporary classic sporty romantic ethnic preppy edgy",
    "outfit_template": "office_ready wedding_guest vacation_capsule weekend_casual date_night athleisure festive_celebration",
    "matching_garment": GARMENTS,
    "complementary_colour": COLOURS,
    "footwear": FOOTWEAR,
    "accessory": ACCESSORIES,
    "mix_and_match": "neutral_foundation statement_piece tonal_pairing contrast_pairing capsule_friendly occasion_specific",
}
VOCAB = {key: frozenset(value.split()) for key, value in VOCAB.items()}
PHYSICAL = frozenset({"fabric", "breathability", "weight", "stretch"})
INFERRED = frozenset(
    {
        "occasion",
        "weather",
        "layering",
        "style",
        "outfit_template",
        "matching_garment",
        "complementary_colour",
        "footwear",
        "accessory",
        "mix_and_match",
    }
)
# These supplied attributes describe clothing, unlike URLs, dataset IDs and stock provenance.
FACT_ATTRIBUTES = frozenset(
    {
        "department",
        "colour",
        "color",
        "primary_colour",
        "secondary_colour",
        "pattern",
        "fabric",
        "material",
        "fit",
        "silhouette",
        "neckline",
        "sleeve",
        "sleeve_length",
        "style",
        "styles",
        "occasion",
        "season",
        "weight",
        "stretch",
        "breathability",
        "subcategory",
        "print",
        "design_details",
        "weather",
        "layering",
    }
)
