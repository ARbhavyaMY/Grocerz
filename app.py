

from flask import Flask, render_template, request, redirect, url_for, flash, session
import pandas as pd
import os
import qrcode
from io import BytesIO
from flask import send_file


app = Flask(__name__)
app.secret_key = "dev-secret"  # OK for local testing only

# Path to Excel inventory
DATA_PATH = os.path.join("data", "inventory.xlsx")


def load_products():
    """
    Read Excel into a pandas DataFrame and return it.
    Keeps logic simple and robust for common messy Excel files.
    """
    df = pd.read_excel(DATA_PATH, engine="openpyxl")

    # ensure text columns exist and clean them
    text_cols = ["sku", "name", "brand", "size",
                 "color", "ingredient_tags", "aisle"]
    for c in text_cols:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).fillna("").str.strip()

    # price -> float (non-numeric -> 0.0)
    if "price" not in df.columns:
        df["price"] = 0.0
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

    # stock_qty -> int (non-numeric -> 0)
    if "stock_qty" not in df.columns:
        df["stock_qty"] = 0
    df["stock_qty"] = pd.to_numeric(
        df["stock_qty"], errors="coerce").fillna(0).astype(int)

    return df


def stock_label(qty):
    """Return only 'In stock' or 'Out of stock'"""
    try:
        if int(qty) > 0:
            return "In stock"
    except Exception:
        pass
    return "Out of stock"


def get_shopping_list():
    """Ensure shopping_list exists in session and return it (dict: sku -> qty)."""
    session.setdefault("shopping_list", {})
    return session["shopping_list"]


def generate_qr(link: str) -> BytesIO:
    """
    Create a PNG QR image for `link` and return a BytesIO buffer ready to send.
    """
    qr = qrcode.QRCode(box_size=6, border=2)
    qr.add_data(link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


# ROUTES

@app.route("/")
def index():
    return """
    <h2>Grocerz </h2>
    <p>Open <a href="/products">/products</a> to view items.</p>
    <p>Shopping list: <a href="/shopping-list">/shopping-list</a></p>
    <p>Map: <a href="/map">/map</a></p>
    """


@app.route("/products")
def products():
    # Read query parameters for search and brand filter
    q = request.args.get("q", "").strip().lower()
    brand_q = request.args.get("brand", "").strip().lower()

    df = load_products()

    # simple search: name or sku
    if q:
        mask = df["name"].str.lower().str.contains(
            q) | df["sku"].str.lower().str.contains(q)
        df = df[mask]

    # brand filter
    if brand_q:
        df = df[df["brand"].str.lower().str.contains(brand_q)]

    # create availability text
    df["availability"] = df["stock_qty"].apply(stock_label)

    # convert to list of dicts for template
    products = df.to_dict(orient="records")

    return render_template("products.html", products=products, q=q, brand=brand_q)


# Add to shopping list

@app.route("/add_to_list", methods=["POST"])
def add_to_list():
    sku = request.form.get("sku", "").strip()
    qty_raw = request.form.get("qty", "1").strip()
    try:
        qty = int(qty_raw)
    except Exception:
        qty = 1
    if qty < 1:
        qty = 1

    df = load_products()
    if df[df["sku"] == sku].empty:
        flash("Product not found.")
        return redirect(url_for("products"))

    cart = get_shopping_list()
    cart[sku] = cart.get(sku, 0) + qty
    session["shopping_list"] = cart  # write back to session
    flash(f"Added {qty} x {sku} to your shopping list.")
    return redirect(url_for("products"))


# Shopping list
@app.route("/shopping-list")
def shopping_list():
    cart = get_shopping_list()
    items = []
    if cart:
        df = load_products()
        for sku, qty in cart.items():
            row = df[df["sku"] == sku]
            if row.empty:
                items.append(
                    {"sku": sku, "name": "(not in inventory)", "qty": qty, "aisle": ""})
            else:
                r = row.iloc[0]
                items.append({
                    "sku": sku,
                    "name": r["name"],
                    "qty": qty,
                    "aisle": r.get("aisle", "")
                })
    total_items = sum(cart.values()) if cart else 0
    return render_template("shopping_list.html", items=items, total_items=total_items)


@app.route("/update_shopping_list", methods=["POST"])
def update_shopping_list():

    session.setdefault("shopping_list", {})

    updated = {}
    for key, val in request.form.items():
        if key.startswith("qty-"):
            sku = key.split("qty-", 1)[1]
            try:
                q = int(val)
            except Exception:
                q = 0
            if q > 0:
                updated[sku] = q

    session["shopping_list"] = updated
    flash("Shopping list updated.")
    return redirect(url_for("shopping_list"))


@app.route("/remove_from_list", methods=["POST"])
def remove_from_list():
    sku = request.form.get("sku", "").strip()
    cart = get_shopping_list()
    if sku in cart:
        del cart[sku]
        session["shopping_list"] = cart
        flash(f"Removed {sku} from your shopping list.")
    return redirect(url_for("shopping_list"))


@app.route("/clear_list", methods=["POST"])
def clear_list():
    session["shopping_list"] = {}
    flash("Shopping list cleared.")
    return redirect(url_for("shopping_list"))


# Simple store map
@app.route("/map")
def store_map():
    """
    Render a simple map page. Accepts ?highlight=Aisle%203 to highlight an aisle.
    Change the aisles list below to match your Excel aisle names.
    """
    highlight = request.args.get("highlight", "")

    aisles = ["Aisle 1", "Aisle 2", "Aisle 3", "Aisle 4", "Aisle 5",
              "Aisle 6", "Aisle 7", "Aisle 8", "Aisle 9", "Aisle 10",
              "Freezer", "Produce"]
    return render_template("map.html", aisles=aisles, highlight=highlight)

# qr


@app.route("/qr")
def qr():
    """
    Return PNG image for a QR. Pass ?link=<url> to create a QR for any URL.
    If no link given, defaults to site root.
    Example: /qr?link=https%3A%2F%2Fexample.com
    """
    link = request.args.get("link")
    if not link:
        # default to app root (use request.host_url to build absolute URL)
        link = request.host_url.rstrip("/")  # e.g. http://127.0.0.1:5000
    buf = generate_qr(link)
    return send_file(buf, mimetype="image/png")


@app.route("/show-qr")
def show_qr():
    """
    Simple page that shows the QR (image is served by /qr).
    Accepts optional ?link= argument to set different links.
    """
    link = request.args.get("link", request.host_url.rstrip("/"))
    # Pass the link to the template so the <img> src can include it
    return render_template("qr_page.html", link=link)

# ----------------------
# Admin: upload Excel (optional)
# ----------------------


@app.route("/admin/upload", methods=["POST"])
def upload():
    file = request.files.get("excel")
    if not file:
        flash("Please select an Excel file to upload.")
        return redirect(url_for("index"))
    os.makedirs("data", exist_ok=True)
    file.save(DATA_PATH)
    flash("Inventory uploaded. Visit /products to see the items.")
    return redirect(url_for("products"))


# ----------------------
# Run server
# ----------------------
if __name__ == "__main__":
    print("Running Grocerz at http://127.0.0.1:5000")
    app.run(debug=True)

