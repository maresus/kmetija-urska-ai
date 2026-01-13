from app.models.product import Product


def find_products(query: str) -> list[Product]:
    dummy_products = [
        Product(id=1, name="Domača salama", price=12.5, weight=0.5),
        Product(id=2, name="Kmečka klobasa", price=8.0, weight=0.35),
        Product(id=3, name="Sir z zelišči", price=15.0, weight=0.7),
    ]
    return dummy_products
