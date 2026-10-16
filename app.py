import os
import sqlite3
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash
)
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "shopsphere-dev-key-change-before-deployment"
)

os.makedirs("instance", exist_ok=True)
DATABASE = os.path.join("instance", "shopsphere.db")


# ---------------- DATABASE ----------------

def get_db_connection():
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    connection = get_db_connection()

    connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'customer',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    connection.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            price REAL NOT NULL,
            category TEXT NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            image_url TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (seller_id) REFERENCES users(id)
        )
    """)

    # ---------------- ORDERS TABLE ----------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            total_amount REAL NOT NULL,
            delivery_address TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Placed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES users(id)
        )
    """)

    # ---------------- ORDER ITEMS TABLE ----------------

    connection.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            subtotal REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    """)

    connection.commit()
    connection.close()


# ---------------- LOGIN REQUIRED ----------------

def login_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in first.", "error")
            return redirect(url_for("login"))

        return view_function(*args, **kwargs)

    return wrapped_view


# ---------------- HOME PAGE ----------------

@app.route("/")
def home():
    return render_template("index.html")


# ---------------- REGISTRATION ----------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "customer").strip().lower()

        if not name or not email or not password:
            flash("Please fill in all required fields.", "error")
            return render_template("register.html")

        if len(password) < 8:
            flash("Password must contain at least 8 characters.", "error")
            return render_template("register.html")

        if role not in ("customer", "seller"):
            flash("Invalid account type.", "error")
            return render_template("register.html")

        hashed_password = generate_password_hash(password)

        connection = get_db_connection()

        try:
            connection.execute(
                """
                INSERT INTO users (name, email, password, role)
                VALUES (?, ?, ?, ?)
                """,
                (name, email, hashed_password, role)
            )

            connection.commit()

            flash("Registration successful! Please log in.", "success")
            return redirect(url_for("login"))

        except sqlite3.IntegrityError:
            flash("This email is already registered.", "error")

        finally:
            connection.close()

    return render_template("register.html")


# ---------------- LOGIN ----------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        connection = get_db_connection()

        try:
            user = connection.execute(
                "SELECT * FROM users WHERE email = ?",
                (email,)
            ).fetchone()
        finally:
            connection.close()

        if user and check_password_hash(user["password"], password):

            session.clear()
            session["user_id"] = user["id"]
            session["user_name"] = user["name"]
            session["user_role"] = user["role"]

            flash("Welcome back, " + user["name"] + "!", "success")

            return redirect(url_for("dashboard"))

        flash("Invalid email or password.", "error")

    return render_template("login.html")


# ---------------- USER DASHBOARD ----------------

@app.route("/dashboard")
@login_required
def dashboard():

    role = session.get("user_role")

    if role == "seller":
        return redirect(url_for("seller_dashboard"))

    return f"""
        <h1>Welcome to ShopSphere, {session['user_name']}!</h1>
        <p>Your customer account is active.</p>
        <a href="/products">Browse Products</a>
        <br><br>
        <a href="/logout">Logout</a>
    """


# ---------------- SELLER DASHBOARD ----------------

@app.route("/seller/dashboard")
@login_required
def seller_dashboard():

    if session.get("user_role") != "seller":
        return "Access denied: Seller account required.", 403

    return f"""
        <h1>Seller Dashboard</h1>
        <p>Welcome, {session['user_name']}!</p>

        <h3>Product Management</h3>

        <a href="{url_for('add_product')}">
            ➕ Add New Product
        </a>

        <br><br>

        <a href="{url_for('seller_orders')}">
           📦 View Customer Orders
        </a>

        <a href="{url_for('products')}">
            🛍️ Browse Products
        </a>

        <br><br>

        <a href="{url_for('logout')}">
            Logout
        </a>
        """



# ---------------- ADD PRODUCT ----------------

@app.route("/seller/add-product", methods=["GET", "POST"])
@login_required
def add_product():

    if session.get("user_role") != "seller":
        flash("Only sellers can add products.", "error")
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        category = request.form.get("category", "").strip()
        image_url = request.form.get("image_url", "").strip()

        try:
            price = float(request.form.get("price", ""))
            stock = int(request.form.get("stock", ""))
        except (ValueError, TypeError):
            flash("Please enter a valid price and stock quantity.", "error")
            return render_template("add_product.html")

        if not name or not description or not category:
            flash("Please fill in all required fields.", "error")
            return render_template("add_product.html")

        if price <= 0 or price > 100000000 or stock < 0 or stock > 1000000:
            flash("Please enter a valid price and stock quantity.", "error")
            return render_template("add_product.html")

        if len(name) > 120 or len(description) > 2000:
            flash("Product name or description is too long.", "error")
            return render_template("add_product.html")

        if len(category) > 100 or len(image_url) > 1000:
            flash("Category or image URL is too long.", "error")
            return render_template("add_product.html")

        if image_url and not image_url.lower().startswith(("http://", "https://")):
            flash("Please enter a valid image URL.", "error")
            return render_template("add_product.html")

        connection = get_db_connection()

        try:
            connection.execute(
                """
                INSERT INTO products
                (seller_id, name, description, price, category, stock, image_url)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session["user_id"],
                    name,
                    description,
                    price,
                    category,
                    stock,
                    image_url
                )
            )

            connection.commit()

        finally:
            connection.close()

        flash("Product added successfully!", "success")
        return redirect(url_for("add_product"))

    return render_template("add_product.html")




# ---------------- PRODUCTS ----------------

@app.route("/products")
def products():

    connection = get_db_connection()

    try:
        all_products = connection.execute("""
            SELECT products.*, users.name AS seller_name
            FROM products
            JOIN users ON products.seller_id = users.id
            ORDER BY products.id DESC
        """).fetchall()
    finally:
        connection.close()

    return render_template(
        "products.html",
        products=all_products
    )

# ---------------- ADD TO CART ----------------

@app.route("/cart/add/<int:product_id>", methods=["POST"])
@login_required
def add_to_cart(product_id):

    if session.get("user_role") != "customer":
        flash("Only customers can add products to cart.", "error")
        return redirect(url_for("products"))

    connection = get_db_connection()

    try:
        product = connection.execute(
            "SELECT * FROM products WHERE id = ?",
            (product_id,)
        ).fetchone()

        if product is None:
            flash("Product not found.", "error")
            return redirect(url_for("products"))

        if product["stock"] <= 0:
            flash("This product is out of stock.", "error")
            return redirect(url_for("products"))

        cart_items = session.get("cart", {})
        product_key = str(product_id)

        current_quantity = int(cart_items.get(product_key, 0))

        if current_quantity >= product["stock"]:
            flash("Available stock limit reached.", "error")
            return redirect(url_for("products"))

        cart_items[product_key] = current_quantity + 1
        session["cart"] = cart_items
        session.modified = True

        flash("Product added to cart successfully!", "success")

    finally:
        connection.close()

    return redirect(url_for("cart"))


# ---------------- SHOPPING CART ----------------

@app.route("/cart")
@login_required
def cart():

    cart_items = session.get("cart", {})
    products_in_cart = []
    total_price = 0

    connection = get_db_connection()

    try:
        for product_id, quantity in cart_items.items():

            product = connection.execute(
                """
                SELECT products.*, users.name AS seller_name
                FROM products
                JOIN users ON products.seller_id = users.id
                WHERE products.id = ?
                """,
                (int(product_id),)
            ).fetchone()

            if product is None:
                continue

            quantity = int(quantity)

            if quantity <= 0:
                continue

            subtotal = float(product["price"]) * quantity

            products_in_cart.append({
                "id": product["id"],
                "name": product["name"],
                "description": product["description"],
                "price": float(product["price"]),
                "stock": product["stock"],
                "image_url": product["image_url"],
                "quantity": quantity,
                "subtotal": subtotal
            })

            total_price += subtotal

    finally:
        connection.close()

    return render_template(
        "cart.html",
        cart_items=products_in_cart,
        total_price=total_price
    )


# ---------------- UPDATE CART QUANTITY ----------------

@app.route("/cart/update/<int:product_id>", methods=["POST"])
@login_required
def update_cart(product_id):

    cart_items = session.get("cart", {})
    product_key = str(product_id)

    if product_key not in cart_items:
        flash("Product is not in your cart.", "error")
        return redirect(url_for("cart"))

    try:
        quantity = int(request.form.get("quantity", "1"))
    except (ValueError, TypeError):
        flash("Invalid quantity.", "error")
        return redirect(url_for("cart"))

    connection = get_db_connection()

    try:
        product = connection.execute(
            "SELECT stock FROM products WHERE id = ?",
            (product_id,)
        ).fetchone()

        if product is None:
            cart_items.pop(product_key, None)
            session["cart"] = cart_items
            flash("Product no longer exists.", "error")
            return redirect(url_for("cart"))

        if quantity < 1:
            flash("Quantity must be at least 1.", "error")

        elif quantity > product["stock"]:
            flash(
                f"Only {product['stock']} item(s) are available.",
                "error"
            )

        else:
            cart_items[product_key] = quantity
            session["cart"] = cart_items
            session.modified = True
            flash("Cart quantity updated.", "success")

    finally:
        connection.close()

    return redirect(url_for("cart"))


# ---------------- REMOVE FROM CART ----------------

@app.route("/cart/remove/<int:product_id>", methods=["POST"])
@login_required
def remove_from_cart(product_id):

    cart_items = session.get("cart", {})
    cart_items.pop(str(product_id), None)

    session["cart"] = cart_items
    session.modified = True

    flash("Product removed from cart.", "success")

    return redirect(url_for("cart"))


# ---------------- CHECKOUT ----------------

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():

    if session.get("user_role") != "customer":
        flash("Only customers can place orders.", "error")
        return redirect(url_for("products"))

    cart_items = session.get("cart", {})

    if not cart_items:
        flash("Your shopping cart is empty.", "error")
        return redirect(url_for("products"))

    connection = get_db_connection()

    try:
        order_products = []
        total_amount = 0

        # Validate cart products and stock
        for product_id, quantity in cart_items.items():

            try:
                product_id = int(product_id)
                quantity = int(quantity)
            except (ValueError, TypeError):
                flash("Invalid cart details. Please review your cart.", "error")
                return redirect(url_for("cart"))

            if quantity <= 0:
                flash("Invalid product quantity.", "error")
                return redirect(url_for("cart"))

            product = connection.execute(
                """
                SELECT id, name, price, stock
                FROM products
                WHERE id = ?
                """,
                (product_id,)
            ).fetchone()

            if product is None:
                flash("A product in your cart no longer exists.", "error")
                return redirect(url_for("cart"))

            if quantity > product["stock"]:
                flash(
                    f"Insufficient stock for {product['name']}. "
                    f"Available quantity: {product['stock']}.",
                    "error"
                )
                return redirect(url_for("cart"))

            subtotal = round(float(product["price"]) * quantity, 2)
            total_amount += subtotal

            order_products.append({
                "id": product["id"],
                "name": product["name"],
                "price": float(product["price"]),
                "quantity": quantity,
                "subtotal": subtotal
            })

        total_amount = round(total_amount, 2)

        if request.method == "POST":

            full_name = request.form.get("full_name", "").strip()
            phone = request.form.get("phone", "").strip()
            address = request.form.get("address", "").strip()
            city = request.form.get("city", "").strip()
            state = request.form.get("state", "").strip()
            pincode = request.form.get("pincode", "").strip()

            if not all([
                full_name, phone, address,
                city, state, pincode
            ]):
                flash("Please fill in all delivery details.", "error")

            elif (
                len(full_name) > 100
                or len(phone) != 10
                or not phone.isdigit()
                or phone[0] not in "6789"
                or len(address) > 1000
                or len(city) > 100
                or len(state) > 100
                or len(pincode) != 6
                or not pincode.isdigit()
            ):
                flash("Please enter valid delivery details.", "error")

            else:
                delivery_address = (
                    f"{full_name}\n"
                    f"Phone: {phone}\n"
                    f"{address}\n"
                    f"{city}, {state} - {pincode}"
                )

                try:
                    # Recheck stock immediately before placing the order.
                    for item in order_products:

                        updated = connection.execute(
                            """
                            UPDATE products
                            SET stock = stock - ?
                            WHERE id = ? AND stock >= ?
                            """,
                            (
                                item["quantity"],
                                item["id"],
                                item["quantity"]
                            )
                        )

                        if updated.rowcount != 1:
                            raise ValueError(
                                f"Insufficient stock for {item['name']}."
                            )

                    # Create order
                    cursor = connection.execute(
                        """
                        INSERT INTO orders
                        (customer_id, total_amount, delivery_address, status)
                        VALUES (?, ?, ?, ?)
                        """,
                        (
                            session["user_id"],
                            total_amount,
                            delivery_address,
                            "Placed"
                        )
                    )

                    order_id = cursor.lastrowid

                    # Save order items
                    for item in order_products:

                        connection.execute(
                            """
                            INSERT INTO order_items
                            (
                                order_id,
                                product_id,
                                product_name,
                                quantity,
                                price,
                                subtotal
                            )
                            VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                order_id,
                                item["id"],
                                item["name"],
                                item["quantity"],
                                item["price"],
                                item["subtotal"]
                            )
                        )

                    connection.commit()

                    # Clear cart only after successful database commit.
                    session["cart"] = {}
                    session.modified = True

                    return redirect(
                        url_for("order_confirmation", order_id=order_id)
                    )

                except ValueError as error:
                    connection.rollback()
                    flash(str(error), "error")

                except sqlite3.Error:
                    connection.rollback()
                    app.logger.exception("Could not place the order.")
                    flash(
                        "Unable to place the order. Please try again.",
                        "error"
                    )

        return render_template(
            "checkout.html",
            order_products=order_products,
            total_amount=total_amount
        )

    finally:
        connection.close()


# ---------------- SELLER ORDERS ----------------

@app.route("/seller/orders")
@login_required
def seller_orders():

    if session.get("user_role") != "seller":
        return "Access denied: Seller account required.", 403

    connection = get_db_connection()

    try:
        orders = connection.execute(
            """
            SELECT
                orders.id AS order_id,
                orders.status AS order_status,
                orders.created_at,
                orders.delivery_address,
                order_items.product_name,
                order_items.quantity,
                order_items.price,
                order_items.subtotal,
                users.name AS customer_name,
                users.email AS customer_email
            FROM orders
            JOIN order_items
                ON orders.id = order_items.order_id
            JOIN products
                ON order_items.product_id = products.id
            JOIN users
                ON orders.customer_id = users.id
            WHERE products.seller_id = ?
            ORDER BY orders.id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    finally:
        connection.close()

    return render_template(
        "seller_orders.html",
        orders=orders
    )



    # ---------------- UPDATE ORDER STATUS ----------------

@app.route("/seller/orders/update/<int:order_id>", methods=["POST"])
@login_required
def update_order_status(order_id):

    if session.get("user_role") != "seller":
        return "Access denied: Seller account required.", 403

    new_status = request.form.get("status", "").strip()

    allowed_statuses = [
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled"
    ]

    if new_status not in allowed_statuses:
        flash("Invalid order status.", "error")
        return redirect(url_for("seller_orders"))

    connection = get_db_connection()

    try:
        seller_has_order = connection.execute(
            """
            SELECT orders.id
            FROM orders
            JOIN order_items ON orders.id = order_items.order_id
            JOIN products ON order_items.product_id = products.id
            WHERE orders.id = ?
              AND products.seller_id = ?
            """,
            (order_id, session["user_id"])
        ).fetchone()

        if seller_has_order is None:
            flash("Order not found for your products.", "error")
            return redirect(url_for("seller_orders"))

        connection.execute(
            "UPDATE orders SET status = ? WHERE id = ?",
            (new_status, order_id)
        )

        connection.commit()

        flash("Order status updated successfully!", "success")

    finally:
        connection.close()

    return redirect(url_for("seller_orders"))


# ---------------- MY ORDERS ----------------

@app.route("/my-orders")
@login_required
def my_orders():

    if session.get("user_role") != "customer":
        flash("Only customers can view their orders.", "error")
        return redirect(url_for("dashboard"))

    connection = get_db_connection()

    try:
        orders = connection.execute(
            """
            SELECT *
            FROM orders
            WHERE customer_id = ?
            ORDER BY id DESC
            """,
            (session["user_id"],)
        ).fetchall()

    finally:
        connection.close()

    return render_template(
        "my_orders.html",
        orders=orders
    )

# ---------------- ORDER CONFIRMATION ----------------

@app.route("/order-confirmation/<int:order_id>")
@login_required
def order_confirmation(order_id):

    if session.get("user_role") != "customer":
        flash("Only customers can view order confirmation.", "error")
        return redirect(url_for("products"))

    connection = get_db_connection()

    try:
        order = connection.execute(
            """
            SELECT *
            FROM orders
            WHERE id = ? AND customer_id = ?
            """,
            (order_id, session["user_id"])
        ).fetchone()

        if order is None:
            return "Order not found.", 404

        items = connection.execute(
            """
            SELECT *
            FROM order_items
            WHERE order_id = ?
            """,
            (order_id,)
        ).fetchall()

    finally:
        connection.close()

    return render_template(
        "order_confirmation.html",
        order=order,
        items=items
    )


# ---------------- LOGOUT ----------------

@app.route("/logout")
def logout():

    session.clear()
    flash("You have been logged out.", "success")

    return redirect(url_for("home"))


# ---------------- START APPLICATION ----------------

init_db()

if __name__ == "__main__":
    from waitress import serve
    print("ShopSphere server running at http://127.0.0.1:5000")
    serve(app, host="127.0.0.1", port=5000)
