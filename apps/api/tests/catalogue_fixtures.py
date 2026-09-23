"""Offline inventory for tests only; never loaded by the application."""

from app.models.product import Product, utcnow
from app.services.catalogue import Catalogue
from app.sources.registry import enabled_retailers


def source():
    return next(r for r in enabled_retailers() if r.key == "assemblylabel")


def raw_product():
    return {
        "id": 100,
        "title": "Relaxed Linen Shirt",
        "handle": "relaxed-linen-shirt",
        "body_html": "<p>100% linen. Relaxed fit.</p>",
        "product_type": "Mens Shirts",
        "vendor": "Fixture Brand",
        "tags": ["mens"],
        "options": [{"name": "Size", "position": 1}, {"name": "Colour", "position": 2}],
        "variants": [
            {"id": 101, "option1": "S", "option2": "Black", "available": True, "price": "70"},
            {"id": 102, "option1": "M", "option2": "Black", "available": True, "price": "100"},
            {"id": 103, "option1": "L", "option2": "Black", "available": False, "price": "40"},
            {"id": 104, "option1": "M", "option2": "Blue", "available": True, "price": "50"},
        ],
        "images": [{"src": "https://cdn.shopify.com/fixture-shirt.jpg"}],
    }


async def seed_catalogue(catalogue: Catalogue):
    await catalogue.initialise()
    specifications = [
        ("Relaxed Black Linen Shirt", "shirt", "black", "linen", 99),
        ("Tailored Black Linen Shirt", "shirt", "black", "linen", 115),
        ("Cream Linen Overshirt", "overshirt", "cream", "linen", 125),
        ("Olive Corduroy Overshirt", "overshirt", "olive", "corduroy", 105),
        ("Olive Cotton Chore Jacket", "jacket", "olive", "cotton", 139),
        ("Cotton Overshirt", "overshirt", "cream", "cotton", 110),
        ("Charcoal Wool Overshirt", "overshirt", "charcoal", "wool", 149),
        ("Grey Cotton Hoodie", "hoodie", "grey", "cotton", 80),
        ("Wool Overcoat", "coat", "navy", "wool", 240),
    ]
    retailer = source()
    products = []
    for index, (title, category, colour, material, price) in enumerate(specifications):
        url = f"https://assemblylabel.com/products/test-fixture-{index}?variant={index}"
        products.append(
            Product(
                product_id=str(index),
                listing_id=str(index),
                variant_size="m",
                title=title,
                description=f"Relaxed {colour} {material} {category}",
                brand="Test fixture",
                retailer=retailer.key,
                retailer_name=retailer.name,
                product_url=url,
                affiliate_url=url,
                category=category,
                colours=[colour],
                materials=[material],
                available_sizes=["m"],
                price=price,
                original_price=price + 40,
                in_stock=True,
                retrieved_at=utcnow(),
            )
        )
    token = await catalogue.claim(retailer.key, force=True)
    assert token
    await catalogue.publish(retailer.key, token, products)
