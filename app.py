# app.py -  Grocerz 
# Requirements: flask, pandas, openpyxl
# Run: activate your venv, then `python app.py`

from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os
import qrcode
from io import BytesIO
from flask import send_file

app = Flask(__name__)
app.secret_key = "dev-secret"  # ok for local dev

# Path to your Excel file (put inventory.xlsx inside the data/ folder)
DATA_PATH = os.path.join("data", "inventory.xlsx")


def load_products():
    """
    Read the Excel file into a pandas DataFrame and return it.
    This version is short, uses pandas helpers, and is easy to understand.
    """
    # Read Excel (first sheet) using openpyxl engine
    df = pd.read_excel(DATA_PATH, engine="openpyxl")

    # Ensure text columns exist and are tidy strings
    text_cols = ["sku", "name", "brand", "size",
                 "color", "ingredient_tags", "aisle"]
    for c in text_cols:
        if c not in df.columns:
            df[c] = ""               # create blank column if missing
        df[c] = df[c].astype(str).fillna("").str.strip()

    # Convert price to float safely (non-numeric -> 0)
    if "price" not in df.columns:
        df["price"] = 0.0
    df["price"] = pd.to_numeric(df["price"], errors="coerce").fillna(0.0)

    # Convert stock_qty to integer safely (non-numeric -> 0)
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


@app.route("/")
def index():
    # small homepage telling user where to go
    return """
    <h2>Grocerz </h2>
    <p>Open <a href="/products">/products</a> to view items.</p>
    <p>To upload a new inventory Excel file, use the /admin/upload route with a POST request.</p>
    """


@app.route("/product/<sku>")
def product_detail(sku):
    df = load_products()
    product = df[df["sku"].str.lower() == sku.lower()].to_dict(orient="records")
    if not product:
        return "Product not found", 404
    product = product[0]
    return render_template("product_detail.html", product=product)


@app.route("/qr/<sku>")
def qr_code(sku):
    qr_img = qrcode.make(f"http://localhost:5000/product/{sku}")
    buffer = BytesIO()
    qr_img.save(buffer, format="PNG")
    buffer.seek(0)
    return send_file(buffer, mimetype="image/png")


@app.route("/products")

def products():
    # get query parameters
    q = request.args.get("q", "").strip().lower()
    brand_q = request.args.get("brand", "").strip().lower()

    # load data
    df = load_products()

    # simple search (name or sku)
    if q:
        mask = df["name"].str.lower().str.contains(
            q) | df["sku"].str.lower().str.contains(q)
        df = df[mask]

    # brand filter
    if brand_q:
        df = df[df["brand"].str.lower().str.contains(brand_q)]

    # display stock as "In stock" or "Out of stock"
    df["availability"] = df["stock_qty"].apply(stock_label)

    products = df.to_dict(orient="records")
    return render_template("products.html", products=products, q=q, brand=brand_q)


# Optional: simple upload route for admin to replace Excel from browser
# (If you don't want this, you can remove the entire /admin/upload route.)
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


if __name__ == "__main__":
    # helpful message and start server
    print("Running Grocerz (simple) at http://127.0.0.1:5000")
    app.run(debug=True)

