import sys
import os

# Ajout du dossier racine au chemin de recherche des modules Python
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app import create_app
from app.services.cart_service import CartService

@pytest.fixture
def app_context():
    app = create_app()
    with app.app_context():
        yield app

def test_multi_tenant_and_multi_client_cart_isolation(app_context):
    """
    Phase 7 : Validation d'isolation à 100% des paniers.
    
    Scénario :
    - Client A (Boutique A / PhoneID 1001) : 2x T-Shirt (P1)
    - Client B (Boutique A / PhoneID 1001) : 1x Jean Slim (P2)
    - Client C (Boutique B / PhoneID 2002) : 1x T-Shirt (P1)
    """
    
    # Identifiants de test
    BOUTIQUE_A_ID = "1001"
    BOUTIQUE_B_ID = "2002"
    
    CLIENT_A = "212600000001"
    CLIENT_B = "212600000002"
    CLIENT_C = "212600000003"
    
    # Nettoyage préalable des paniers de test
    CartService.clear_cart(BOUTIQUE_A_ID, CLIENT_A)
    CartService.clear_cart(BOUTIQUE_A_ID, CLIENT_B)
    CartService.clear_cart(BOUTIQUE_B_ID, CLIENT_C)

    # -------------------------------------------------------------------------
    # 1. EXECUTION DES ACTIONS
    # -------------------------------------------------------------------------
    
    # Client A (Boutique A) : Ajoute 2x T-Shirt (P1)
    CartService.add_item(
        phone_number_id=BOUTIQUE_A_ID,
        sender_phone=CLIENT_A,
        product_id="P1",
        product_name="T-Shirt Coton",
        price=250.0,
        quantity=2
    )

    # Client B (Boutique A) : Ajoute 1x Jean Slim (P2)
    CartService.add_item(
        phone_number_id=BOUTIQUE_A_ID,
        sender_phone=CLIENT_B,
        product_id="P2",
        product_name="Jean Slim Bleu",
        price=500.0,
        quantity=1
    )

    # Client C (Boutique B) : Ajoute 1x T-Shirt (P1)
    CartService.add_item(
        phone_number_id=BOUTIQUE_B_ID,
        sender_phone=CLIENT_C,
        product_id="P1",
        product_name="T-Shirt Coton",
        price=250.0,
        quantity=1
    )

    # -------------------------------------------------------------------------
    # 2. VERIFICATIONS & ASSERTIONS D'ISOLATION
    # -------------------------------------------------------------------------
    
    cart_a = CartService.get_cart(BOUTIQUE_A_ID, CLIENT_A)
    cart_b = CartService.get_cart(BOUTIQUE_A_ID, CLIENT_B)
    cart_c = CartService.get_cart(BOUTIQUE_B_ID, CLIENT_C)

    # Verification Client A
    assert len(cart_a) == 1, "Le panier du Client A doit contenir exactement 1 type de produit."
    assert cart_a[0]["product_id"] == "P1"
    assert cart_a[0]["quantity"] == 2
    assert cart_a[0]["price"] == 250.0

    # Verification Client B
    assert len(cart_b) == 1, "Le panier du Client B doit contenir exactement 1 type de produit."
    assert cart_b[0]["product_id"] == "P2"
    assert cart_b[0]["quantity"] == 1
    assert cart_b[0]["price"] == 500.0

    # Verification Client C (Autre boutique, même produit P1 que Client A)
    assert len(cart_c) == 1, "Le panier du Client C doit contenir exactement 1 type de produit."
    assert cart_c[0]["product_id"] == "P1"
    assert cart_c[0]["quantity"] == 1
    assert cart_c[0]["price"] == 250.0

    # Cross-Verification : S'assurer qu'aucune fuite de données n'a eu lieu
    assert cart_a != cart_b, "Le panier du Client A et du Client B ne doivent pas se mélanger."
    assert cart_a != cart_c, "Le panier du Client A (Boutique A) et du Client C (Boutique B) ne doivent pas se mélanger."

    # Nettoyage post-test
    CartService.clear_cart(BOUTIQUE_A_ID, CLIENT_A)
    CartService.clear_cart(BOUTIQUE_A_ID, CLIENT_B)
    CartService.clear_cart(BOUTIQUE_B_ID, CLIENT_C)
    
    print("\n✅ [PHASE 7 PASSEE AVEC SUCCES] Isolation 100% validée entre clients et boutiques !")