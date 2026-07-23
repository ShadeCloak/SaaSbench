
import json
import sys
import time
import requests

from config import APP_BASE_URL, HTTP_TIMEOUT, TEST_USERS

ADMIN_EMAIL = TEST_USERS["admin"]["email"]
ADMIN_PASSWORD = TEST_USERS["admin"]["password"]

session = requests.Session()
session.headers.update({"Content-Type": "application/json"})


def _url(path: str) -> str:
    return f"{APP_BASE_URL}{path}"


def _login_admin() -> str:
    session.cookies.clear()
    r = requests.post(_url("/auth/user/emailpass"),
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        token = r.json().get("token")
        if token:
            payload = _decode_jwt(token)
            if payload and payload.get("actor_id"):
                return token

    requests.post(_url("/auth/user/emailpass/register"),
                  json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                  timeout=HTTP_TIMEOUT)

    session.cookies.clear()
    r = requests.post(_url("/auth/user/emailpass"),
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=HTTP_TIMEOUT)
    if r.status_code == 200:
        return r.json().get("token", "")
    return ""


def _decode_jwt(token: str) -> dict | None:
    import base64
    try:
        payload = token.split(".")[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return None


def _admin(method: str, path: str, body=None, *, token: str) -> dict:
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    r = requests.request(method, _url(path), json=body, headers=headers, timeout=HTTP_TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {"_status": r.status_code, "_text": r.text[:500]}


def _store(method: str, path: str, body=None, *, pub_key: str = "", token: str = "") -> dict:
    headers = {"Content-Type": "application/json"}
    if pub_key:
        headers["x-publishable-api-key"] = pub_key
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, _url(path), json=body, headers=headers, timeout=HTTP_TIMEOUT)
    try:
        return r.json()
    except Exception:
        return {"_status": r.status_code, "_text": r.text[:500]}


def run_seed() -> dict:
    ctx = {}
    errors = []

    print("  [seed] Logging in as admin...")
    token = _login_admin()
    if not token:
        print("  [seed] FATAL: Cannot obtain admin token")
        return ctx
    ctx["admin_token"] = token
    print(f"  [seed] Admin token obtained")

    print("  [seed] Creating region...")
    resp = _admin("POST", "/admin/regions",
                  {"name": "Eval US Region", "currency_code": "usd", "countries": ["us"]},
                  token=token)
    region = resp.get("region", {})
    ctx["region_id"] = region.get("id", "")
    if not ctx["region_id"]:
        print(f"  [seed] WARN: Region creation failed: {json.dumps(resp)[:200]}")
        for r in _admin("GET", "/admin/regions", token=token).get("regions", []):
            if r.get("currency_code") == "usd":
                ctx["region_id"] = r["id"]
                region = r
                break
    print(f"  [seed] region_id = {ctx.get('region_id')}")

    print("  [seed] Creating sales channel...")
    existing_sc = _admin("GET", "/admin/sales-channels?limit=1", token=token).get("sales_channels", [])
    if existing_sc:
        ctx["sales_channel_id"] = existing_sc[0]["id"]
    else:
        resp = _admin("POST", "/admin/sales-channels",
                      {"name": "Eval Store", "description": "Evaluation channel"},
                      token=token)
        ctx["sales_channel_id"] = resp.get("sales_channel", {}).get("id", "")
    print(f"  [seed] sales_channel_id = {ctx.get('sales_channel_id')}")

    print("  [seed] Creating publishable API key...")
    existing_keys = _admin("GET", "/admin/api-keys?type=publishable&limit=1", token=token).get("api_keys", [])
    if existing_keys:
        pub_key_id = existing_keys[0]["id"]
        pub_key_token = existing_keys[0].get("token", "")
        ctx["publishable_key"] = pub_key_token
        ctx["pub_key_id"] = pub_key_id
    else:
        resp = _admin("POST", "/admin/api-keys",
                      {"title": "Eval Publishable Key", "type": "publishable"},
                      token=token)
        api_key = resp.get("api_key", {})
        pub_key_id = api_key.get("id", "")
        pub_key_token = api_key.get("token", "")
        ctx["publishable_key"] = pub_key_token
        ctx["pub_key_id"] = pub_key_id
    if pub_key_id and ctx["sales_channel_id"]:
        _admin("POST", f"/admin/api-keys/{pub_key_id}/sales-channels",
               {"add": [ctx["sales_channel_id"]]}, token=token)
    print(f"  [seed] publishable_key = {pub_key_token[:20]}..." if pub_key_token else "  [seed] WARN: No publishable key")

    print("  [seed] Creating stock location...")
    existing_locs = _admin("GET", "/admin/stock-locations?limit=1", token=token).get("stock_locations", [])
    if existing_locs:
        ctx["stock_location_id"] = existing_locs[0]["id"]
    else:
        resp = _admin("POST", "/admin/stock-locations",
                      {"name": "Eval Warehouse", "address": {
                          "address_1": "123 Test St", "city": "New York",
                          "country_code": "us", "postal_code": "10001"}},
                      token=token)
        loc = resp.get("stock_location", {})
        ctx["stock_location_id"] = loc.get("id", "")
    print(f"  [seed] stock_location_id = {ctx.get('stock_location_id')}")

    if ctx["stock_location_id"] and ctx["sales_channel_id"]:
        _admin("POST", f"/admin/stock-locations/{ctx['stock_location_id']}/sales-channels",
               {"add": [ctx["sales_channel_id"]]}, token=token)

    print("  [seed] Creating inventory item...")
    resp = _admin("POST", "/admin/inventory-items",
                  {"sku": "EVAL-SKU-001", "title": "Eval Inventory"},
                  token=token)
    inv = resp.get("inventory_item", {})
    ctx["inventory_item_id"] = inv.get("id", "")
    if not ctx["inventory_item_id"]:
        for ii in _admin("GET", "/admin/inventory-items?q=EVAL-SKU", token=token).get("inventory_items", []):
            ctx["inventory_item_id"] = ii["id"]
            break
    print(f"  [seed] inventory_item_id = {ctx.get('inventory_item_id')}")

    if ctx["inventory_item_id"] and ctx["stock_location_id"]:
        _admin("POST", f"/admin/inventory-items/{ctx['inventory_item_id']}/location-levels",
               {"location_id": ctx["stock_location_id"], "stocked_quantity": 1000000},
               token=token)

    print("  [seed] Creating shipping profile...")
    resp = _admin("POST", "/admin/shipping-profiles",
                  {"name": "Eval Default Profile", "type": "default"},
                  token=token)
    sp = resp.get("shipping_profile", {})
    ctx["shipping_profile_id"] = sp.get("id", "")
    if not ctx["shipping_profile_id"]:
        for s in _admin("GET", "/admin/shipping-profiles", token=token).get("shipping_profiles", []):
            ctx["shipping_profile_id"] = s["id"]
            break
    print(f"  [seed] shipping_profile_id = {ctx.get('shipping_profile_id')}")

    print("  [seed] Creating product with variant and prices...")
    product_body = {
        "title": "Eval Test Product",
        "status": "published",
        "options": [{"title": "Size", "values": ["Large", "Small"]},
                    {"title": "Color", "values": ["Blue"]}],
        "variants": [{
            "title": "Eval Variant Large Blue",
            "sku": "EVAL-SKU-001",
            "manage_inventory": True,
            "inventory_items": [{"inventory_item_id": ctx.get("inventory_item_id", ""), "required_quantity": 1}] if ctx.get("inventory_item_id") else [],
            "prices": [{"currency_code": "usd", "amount": 5000}],
            "options": {"Size": "Large", "Color": "Blue"},
        }],
    }
    if ctx.get("shipping_profile_id"):
        product_body["shipping_profile_id"] = ctx["shipping_profile_id"]

    resp = _admin("POST", "/admin/products", product_body, token=token)
    product = resp.get("product", {})
    ctx["product_id"] = product.get("id", "")
    if product.get("variants"):
        ctx["variant_id"] = product["variants"][0].get("id", "")
    if not ctx["product_id"]:
        for p in _admin("GET", "/admin/products?q=Eval+Test&limit=1", token=token).get("products", []):
            ctx["product_id"] = p["id"]
            if p.get("variants"):
                ctx["variant_id"] = p["variants"][0].get("id", "")
            break
    print(f"  [seed] product_id = {ctx.get('product_id')}, variant_id = {ctx.get('variant_id')}")

    print("  [seed] Creating fulfillment set...")
    if ctx.get("stock_location_id"):
        resp = _admin("POST",
                      f"/admin/stock-locations/{ctx['stock_location_id']}/fulfillment-sets?fields=*fulfillment_sets",
                      {"name": "Eval Fulfillment Set", "type": "shipping"},
                      token=token)
        fs_data = resp.get("stock_location", {}).get("fulfillment_sets", [])
        if fs_data:
            ctx["fulfillment_set_id"] = fs_data[0].get("id", "")
        if not ctx.get("fulfillment_set_id"):
            loc_resp = _admin("GET", f"/admin/stock-locations/{ctx['stock_location_id']}?fields=*fulfillment_sets", token=token)
            for fs in loc_resp.get("stock_location", {}).get("fulfillment_sets", []):
                ctx["fulfillment_set_id"] = fs["id"]
                break
    print(f"  [seed] fulfillment_set_id = {ctx.get('fulfillment_set_id')}")

    if ctx.get("fulfillment_set_id"):
        print("  [seed] Creating service zone...")
        resp = _admin("POST", f"/admin/fulfillment-sets/{ctx['fulfillment_set_id']}/service-zones",
                      {"name": "Eval US Zone",
                       "geo_zones": [{"type": "country", "country_code": "us"}]},
                      token=token)
        fs = resp.get("fulfillment_set", {})
        zones = fs.get("service_zones", [])
        if zones:
            ctx["service_zone_id"] = zones[-1].get("id", "")
        if not ctx.get("service_zone_id"):
            fs_resp = _admin("GET", f"/admin/fulfillment-sets/{ctx['fulfillment_set_id']}?fields=*service_zones", token=token)
            for sz in fs_resp.get("fulfillment_set", {}).get("service_zones", []):
                ctx["service_zone_id"] = sz["id"]
                break
        print(f"  [seed] service_zone_id = {ctx.get('service_zone_id')}")

    if ctx.get("stock_location_id"):
        providers = _admin("GET", "/admin/fulfillment-providers", token=token).get("fulfillment_providers", [])
        provider_id = ""
        for p in providers:
            if "manual" in p.get("id", ""):
                provider_id = p["id"]
                break
        if not provider_id and providers:
            provider_id = providers[0]["id"]
        ctx["fulfillment_provider_id"] = provider_id

        if provider_id:
            _admin("POST", f"/admin/stock-locations/{ctx['stock_location_id']}/fulfillment-providers",
                   {"add": [provider_id]}, token=token)
        print(f"  [seed] fulfillment_provider_id = {ctx.get('fulfillment_provider_id')}")

    print("  [seed] Creating shipping option...")
    if ctx.get("service_zone_id") and ctx.get("shipping_profile_id") and ctx.get("fulfillment_provider_id"):
        so_body = {
            "name": "Eval Standard Shipping",
            "service_zone_id": ctx["service_zone_id"],
            "shipping_profile_id": ctx["shipping_profile_id"],
            "provider_id": ctx["fulfillment_provider_id"],
            "price_type": "flat",
            "type": {"label": "Standard", "description": "Standard shipping", "code": "standard"},
            "prices": [
                {"currency_code": "usd", "amount": 1000},
                {"region_id": ctx.get("region_id", ""), "amount": 1100},
            ],
            "rules": [],
        }
        resp = _admin("POST", "/admin/shipping-options", so_body, token=token)
        so = resp.get("shipping_option", {})
        ctx["shipping_option_id"] = so.get("id", "")
    if not ctx.get("shipping_option_id"):
        for so in _admin("GET", "/admin/shipping-options?limit=1", token=token).get("shipping_options", []):
            ctx["shipping_option_id"] = so["id"]
            break
    print(f"  [seed] shipping_option_id = {ctx.get('shipping_option_id')}")

    def _get_variant_by_title(title, sku):
        import urllib.parse as _up
        for p in _admin("GET", f"/admin/products?q={_up.quote(title)}&limit=5&fields=id,title,*variants",
                        token=token).get("products", []):
            if p.get("title") != title:
                continue
            for v in p.get("variants", []):
                if v.get("sku") == sku:
                    return v["id"]
            if p.get("variants"):
                return p["variants"][0]["id"]
        return ""

    def _get_inv_by_sku(sku):
        for ii in _admin("GET", f"/admin/inventory-items?q={sku}&limit=5",
                         token=token).get("inventory_items", []):
            if ii.get("sku") == sku:
                return ii["id"]
        return ""

    def _ensure_inv(sku, title):
        iid = _get_inv_by_sku(sku)
        if not iid:
            iid = _admin("POST", "/admin/inventory-items",
                         {"sku": sku, "title": title}, token=token).get("inventory_item", {}).get("id", "")
        if iid and ctx.get("stock_location_id"):
            _admin("POST", f"/admin/inventory-items/{iid}/location-levels",
                   {"location_id": ctx["stock_location_id"], "stocked_quantity": 1000000}, token=token)
        return iid

    sc_link = [{"id": ctx["sales_channel_id"]}] if ctx.get("sales_channel_id") else []

    _so_profile = ""
    if ctx.get("shipping_option_id"):
        _so_profile = _admin("GET", f"/admin/shipping-options/{ctx['shipping_option_id']}?fields=shipping_profile_id",
                             token=token).get("shipping_option", {}).get("shipping_profile_id", "")
    _so_profile = _so_profile or ctx.get("shipping_profile_id", "")

    ctx["digital_variant_id"] = _get_variant_by_title("Eval Digital Product", "EVAL-DIGITAL-V")
    if not ctx["digital_variant_id"]:
        dig_profile = _admin("POST", "/admin/shipping-profiles",
                             {"name": "Eval Digital Profile", "type": "digital"},
                             token=token).get("shipping_profile", {}).get("id", "")
        if not dig_profile:
            for s in _admin("GET", "/admin/shipping-profiles", token=token).get("shipping_profiles", []):
                if s.get("name") == "Eval Digital Profile":
                    dig_profile = s["id"]; break
        dig_inv = _ensure_inv("EVAL-DIGITAL-INV", "Eval Digital Inventory")
        if dig_profile and dig_inv:
            dig_prod = _admin("POST", "/admin/products", {
                "title": "Eval Digital Product", "status": "published",
                "shipping_profile_id": dig_profile, "sales_channels": sc_link,
                "options": [{"title": "Fmt", "values": ["Download"]}],
                "variants": [{"title": "Eval Digital Variant", "sku": "EVAL-DIGITAL-V",
                              "manage_inventory": True,
                              "inventory_items": [{"inventory_item_id": dig_inv, "required_quantity": 1}],
                              "prices": [{"currency_code": "usd", "amount": 3000}],
                              "options": {"Fmt": "Download"}}],
            }, token=token).get("product", {})
            if dig_prod.get("variants"):
                ctx["digital_variant_id"] = dig_prod["variants"][0].get("id", "")
            if (ctx.get("service_zone_id") and dig_profile and ctx.get("fulfillment_provider_id")):
                dso = _admin("POST", "/admin/shipping-options", {
                    "name": "Eval Digital Shipping",
                    "service_zone_id": ctx["service_zone_id"],
                    "shipping_profile_id": dig_profile,
                    "provider_id": ctx["fulfillment_provider_id"],
                    "price_type": "flat",
                    "type": {"label": "Digital", "description": "Digital", "code": "digital"},
                    "prices": [{"currency_code": "usd", "amount": 0},
                               {"region_id": ctx.get("region_id", ""), "amount": 0}],
                    "rules": [],
                }, token=token).get("shipping_option", {})
                ctx["digital_shipping_option_id"] = dso.get("id", "")
    if not ctx.get("digital_shipping_option_id"):
        for so in _admin("GET", "/admin/shipping-options?limit=50&fields=id,name", token=token).get("shipping_options", []):
            if so.get("name") == "Eval Digital Shipping":
                ctx["digital_shipping_option_id"] = so["id"]; break
    print(f"  [seed] digital_variant_id = {ctx.get('digital_variant_id')}, digital_shipping_option_id = {ctx.get('digital_shipping_option_id')}")

    ctx["kit_variant_id"] = _get_variant_by_title("Eval Kit Product", "EVAL-KIT-V")
    ctx["kit_desk_inventory_id"] = _ensure_inv("EVAL-KIT-DESK", "Eval Kit Desk")
    ctx["kit_leg_inventory_id"] = _ensure_inv("EVAL-KIT-LEG", "Eval Kit Leg")
    if not ctx["kit_variant_id"] and _so_profile and ctx["kit_desk_inventory_id"] and ctx["kit_leg_inventory_id"]:
        kit_prod = _admin("POST", "/admin/products", {
            "title": "Eval Kit Product", "status": "published",
            "shipping_profile_id": _so_profile, "sales_channels": sc_link,
            "options": [{"title": "Kit", "values": ["Full"]}],
            "variants": [{"title": "Eval Kit Variant", "sku": "EVAL-KIT-V",
                          "manage_inventory": True,
                          "inventory_items": [
                              {"inventory_item_id": ctx["kit_desk_inventory_id"], "required_quantity": 1},
                              {"inventory_item_id": ctx["kit_leg_inventory_id"], "required_quantity": 4}],
                          "prices": [{"currency_code": "usd", "amount": 9000}],
                          "options": {"Kit": "Full"}}],
        }, token=token).get("product", {})
        if kit_prod.get("variants"):
            ctx["kit_variant_id"] = kit_prod["variants"][0].get("id", "")
    print(f"  [seed] kit_variant_id = {ctx.get('kit_variant_id')} (desk={ctx.get('kit_desk_inventory_id')}, leg={ctx.get('kit_leg_inventory_id')})")

    print("  [seed] Creating cart and completing checkout...")
    pub_key = ctx.get("publishable_key", "")

    existing_orders = _admin("GET", "/admin/orders?limit=5&fields=*items,*shipping_methods", token=token).get("orders", [])
    if len(existing_orders) >= 2:
        o1 = existing_orders[0]
        ctx["order_id"] = o1["id"]
        if o1.get("items"):
            ctx["order_item_id"] = o1["items"][0].get("id", "")
        if o1.get("shipping_methods"):
            ctx["order_shipping_id"] = o1["shipping_methods"][0].get("id", "")
        ctx["order_display_id"] = o1.get("display_id")
        ctx["order_email"] = o1.get("email", "")
        o2 = existing_orders[1]
        ctx["uncaptured_order_id"] = o2["id"]
        print(f"  [seed] Reused existing orders: {ctx['order_id']}, {ctx['uncaptured_order_id']}")
    elif ctx.get("region_id") and ctx.get("variant_id"):
        cart_body = {
            "currency_code": "usd",
            "email": "eval_checkout@test.com",
            "region_id": ctx["region_id"],
            "sales_channel_id": ctx.get("sales_channel_id", ""),
            "shipping_address": {
                "first_name": "Eval", "last_name": "Tester",
                "address_1": "123 Test St", "city": "New York",
                "country_code": "us", "province": "NY", "postal_code": "10001",
            },
            "billing_address": {
                "first_name": "Eval", "last_name": "Tester",
                "address_1": "123 Test St", "city": "New York",
                "country_code": "us", "province": "NY", "postal_code": "10001",
            },
            "items": [{"quantity": 2, "variant_id": ctx["variant_id"]}],
        }
        resp = _store("POST", "/store/carts", cart_body, pub_key=pub_key)
        cart = resp.get("cart", {})
        ctx["cart_id"] = cart.get("id", "")
        print(f"  [seed] cart_id = {ctx.get('cart_id')}")

        if ctx["cart_id"] and ctx.get("shipping_option_id"):
            _store("POST", f"/store/carts/{ctx['cart_id']}/shipping-methods",
                   {"option_id": ctx["shipping_option_id"]}, pub_key=pub_key)

            resp = _store("POST", "/store/payment-collections",
                          {"cart_id": ctx["cart_id"]}, pub_key=pub_key)
            pc = resp.get("payment_collection", {})
            ctx["payment_collection_id"] = pc.get("id", "")
            print(f"  [seed] payment_collection_id = {ctx.get('payment_collection_id')}")

            if ctx["payment_collection_id"]:
                _store("POST", f"/store/payment-collections/{ctx['payment_collection_id']}/payment-sessions",
                       {"provider_id": "pp_system_default"}, pub_key=pub_key)

                resp = _store("POST", f"/store/carts/{ctx['cart_id']}/complete", {}, pub_key=pub_key)
                order = resp.get("order", {})
                if not order:
                    order = resp.get("data", {}).get("order", {})
                ctx["order_id"] = order.get("id", "")
                print(f"  [seed] order_id = {ctx.get('order_id')}")

                if ctx["order_id"]:
                    full_order = _admin("GET",
                        f"/admin/orders/{ctx['order_id']}?fields=*items,*shipping_methods",
                        token=token)
                    order_data = full_order.get("order", full_order)
                    if order_data.get("items"):
                        ctx["order_item_id"] = order_data["items"][0].get("id", "")
                    if order_data.get("shipping_methods"):
                        ctx["order_shipping_id"] = order_data["shipping_methods"][0].get("id", "")
                    ctx["order_display_id"] = order_data.get("display_id")
                    ctx["order_email"] = order_data.get("email", "eval_checkout@test.com")

    if ctx.get("uncaptured_order_id"):
        pass
    elif ctx.get("region_id") and ctx.get("variant_id") and ctx.get("cart_id"):
        print("  [seed] Creating second order for cancel/edit tests...")
        cart2_body = {
            "currency_code": "usd",
            "email": "eval_cancel@test.com",
            "region_id": ctx["region_id"],
            "sales_channel_id": ctx.get("sales_channel_id", ""),
            "shipping_address": {
                "first_name": "Cancel", "last_name": "Test",
                "address_1": "456 Cancel St", "city": "LA",
                "country_code": "us", "province": "CA", "postal_code": "90001",
            },
            "billing_address": {
                "first_name": "Cancel", "last_name": "Test",
                "address_1": "456 Cancel St", "city": "LA",
                "country_code": "us", "province": "CA", "postal_code": "90001",
            },
            "items": [{"quantity": 1, "variant_id": ctx["variant_id"]}],
        }
        resp = _store("POST", "/store/carts", cart2_body, pub_key=pub_key)
        cart2 = resp.get("cart", {})
        cart2_id = cart2.get("id", "")

        if cart2_id and ctx.get("shipping_option_id"):
            _store("POST", f"/store/carts/{cart2_id}/shipping-methods",
                   {"option_id": ctx["shipping_option_id"]}, pub_key=pub_key)
            resp = _store("POST", "/store/payment-collections",
                          {"cart_id": cart2_id}, pub_key=pub_key)
            pc2 = resp.get("payment_collection", {})
            if pc2.get("id"):
                _store("POST", f"/store/payment-collections/{pc2['id']}/payment-sessions",
                       {"provider_id": "pp_system_default"}, pub_key=pub_key)
                resp = _store("POST", f"/store/carts/{cart2_id}/complete", {}, pub_key=pub_key)
                order2 = resp.get("order", {})
                if not order2:
                    order2 = resp.get("data", {}).get("order", {})
                ctx["uncaptured_order_id"] = order2.get("id", "")
                print(f"  [seed] uncaptured_order_id = {ctx.get('uncaptured_order_id')}")

    print("  [seed] Registering store customer...")
    cust_email = TEST_USERS.get("customer", {}).get("email", "eval_customer@test.com")
    cust_password = TEST_USERS.get("customer", {}).get("password", "EvalCustomer123!")

    existing_custs = _admin("GET", f"/admin/customers?q={cust_email}&limit=1", token=token).get("customers", [])
    if existing_custs:
        ctx["customer_id"] = existing_custs[0]["id"]
        login_resp = _store("POST", "/auth/customer/emailpass",
                            {"email": cust_email, "password": cust_password})
        ctx["customer_token"] = login_resp.get("token", "")
    else:
        reg_resp = _store("POST", "/auth/customer/emailpass/register",
                          {"email": cust_email, "password": cust_password})
        cust_token = reg_resp.get("token", "")
        if not cust_token:
            login_resp = _store("POST", "/auth/customer/emailpass",
                                {"email": cust_email, "password": cust_password})
            cust_token = login_resp.get("token", "")
        if cust_token:
            create_resp = _store("POST", "/store/customers",
                                 {"email": cust_email, "first_name": "Eval", "last_name": "Customer"},
                                 pub_key=pub_key, token=cust_token)
            cust_data = create_resp.get("customer", {})
            ctx["customer_id"] = cust_data.get("id", "")
            relogin = _store("POST", "/auth/customer/emailpass",
                             {"email": cust_email, "password": cust_password})
            ctx["customer_token"] = relogin.get("token", cust_token)
    if not ctx.get("customer_id"):
        for c in _admin("GET", "/admin/customers?limit=1", token=token).get("customers", []):
            ctx["customer_id"] = c["id"]
            break
    print(f"  [seed] customer_id = {ctx.get('customer_id')}")

    print("  [seed] Creating promotion...")
    promo_body = {
        "code": "EVAL10",
        "type": "standard",
        "status": "active",
        "application_method": {
            "type": "percentage",
            "value": 10,
            "target_type": "items",
            "allocation": "each",
            "max_quantity": 10,
        },
    }
    resp = _admin("POST", "/admin/promotions", promo_body, token=token)
    promo = resp.get("promotion", {})
    ctx["promotion_id"] = promo.get("id", "")
    ctx["promo_id"] = promo.get("id", "")
    if not ctx["promotion_id"]:
        for pm in _admin("GET", "/admin/promotions?limit=1", token=token).get("promotions", []):
            ctx["promotion_id"] = pm["id"]
            ctx["promo_id"] = pm["id"]
            break
    print(f"  [seed] promotion_id = {ctx.get('promotion_id')}")

    print("  [seed] Creating tax region...")
    tax_providers = _admin("GET", "/admin/tax-providers", token=token).get("tax_providers", [])
    tax_provider_id = tax_providers[0]["id"] if tax_providers else "tp_system"
    resp = _admin("POST", "/admin/tax-regions",
                  {"country_code": "us", "provider_id": tax_provider_id}, token=token)
    tax_region = resp.get("tax_region", {})
    ctx["tax_region_id"] = tax_region.get("id", "")
    if not ctx["tax_region_id"]:
        for tr in _admin("GET", "/admin/tax-regions?limit=1", token=token).get("tax_regions", []):
            ctx["tax_region_id"] = tr["id"]
            break
    print(f"  [seed] tax_region_id = {ctx.get('tax_region_id')}")

    for key in ["order_id", "uncaptured_order_id", "order_item_id", "order_shipping_id",
                 "variant_id", "stock_location_id", "region_id", "customer_id",
                 "inventory_item_id", "shipping_option_id", "publishable_key",
                 "sales_channel_id", "product_id"]:
        if ctx.get(key):
            ctx[f"seed_{key}"] = ctx[key]

    populated = {k: v for k, v in ctx.items() if v and not k.endswith("_token") and not k.startswith("seed_")}
    missing = [k for k, v in ctx.items() if not v and k != "admin_token" and not k.startswith("seed_")]
    print(f"\n  [seed] ✅ Populated {len(populated)} context entries")
    if missing:
        print(f"  [seed] ⚠ Missing: {', '.join(missing)}")

    return ctx


if __name__ == "__main__":
    print("=== Evaluation Seed Script ===")
    ctx = run_seed()
    out_path = sys.argv[1] if len(sys.argv) > 1 else "seed_context.json"
    with open(out_path, "w") as f:
        json.dump(ctx, f, indent=2)
    print(f"\nContext saved to {out_path}")
    print(f"Total entries: {len(ctx)}")
