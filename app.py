from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_bcrypt import Bcrypt
import psycopg2
import base64
app = Flask(__name__)
bcrypt = Bcrypt(app)
app.secret_key = 'your_secret_key'

# Configurazione del database
DB_PARAMS = {
    'dbname': 'marketplace',
    'user': 'postgres',
    'password': 'malek',
    'host': 'localhost',
    'port': '5432'
}

def get_db_connection():
    try:
        return psycopg2.connect(**DB_PARAMS)
    except Exception as e:
        print("The error in the database connection:", e)
        return None
    
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        birth_date = request.form['birth_date']
        username = request.form['username']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        if len(password) < 6:
            flash('The password must be at least 6 characters long.', 'danger')
            return redirect(url_for('register'))

        if password != confirm_password:
            flash('The passwords do not match.', 'danger')
            return redirect(url_for('register'))

        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO users (name, surname, birth_date, username, password, balance)
                    VALUES (%s, %s, %s, %s, %s, 0)""", 
                    (name, surname, birth_date, username, hashed_password))
                conn.commit()
                cur.close()
                conn.close()
                flash('Registration completed successfully!', 'success')
                return redirect(url_for('login'))
            except Exception as e:
                flash(f'Error in registration: {e}', 'danger')

    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor()
                cur.execute("SELECT id, password, active FROM users WHERE username = %s", (username,))
                user = cur.fetchone()
                cur.close()
                conn.close()

                if user is None:
                    flash('Invalid credentials. Please try again.', 'danger')
                    return redirect(url_for('login'))

                user_id, hashed_password, is_active = user

                # Debug: stampiamo il valore di active per verificare cosa restituisce il DB
                print(f"DEBUG: is_active = {is_active} (type: {type(is_active)})")

                # Controllo corretto su active
                if bool(is_active) is False:  # Convertiamo in booleano per sicurezza
                    flash('Your account is deactivated. Please contact the administrator.', 'warning')
                    return redirect(url_for('login'))

                if bcrypt.check_password_hash(hashed_password, password):
                    session['user_id'] = user_id
                    session['username'] = username
                    flash('Login effettuato con successo!', 'success')
                    return redirect(url_for('dashboard'))
                else:
                    flash('Invalid credentials. Please try again.', 'danger')

            except Exception as e:
                flash('Error during login: ' + str(e), 'danger')

    return render_template('login.html')


@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'user_id' not in session:
        flash('You must log in to access the dashboard.', 'danger')
        return redirect(url_for('login'))
    
    user_id = session['user_id']

    # Recupera il saldo attuale
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT balance FROM users WHERE id = %s", (user_id,))
    balance = cur.fetchone()[0]

    # Recupera i parametri di ricerca dalla richiesta
    name_filter = request.args.get('name', '').strip()
    category_filter = request.args.get('category', '').strip()
    min_price = request.args.get('min_price', '').strip()
    max_price = request.args.get('max_price', '').strip()

    # Modifica della query per includere anche l'immagine (img1)
    query = """
        SELECT p.id, p.name, p.category, p.price, p.quantity, u.name AS seller_name, pi.img1
        FROM products p 
        JOIN users u ON p.id_user = u.id
        LEFT JOIN product_images pi ON p.id = pi.id_product
        WHERE 1=1
    """
    params = []

    if name_filter:
        query += " AND p.name ILIKE %s"
        params.append(f"%{name_filter}%")
    if category_filter:
        query += " AND p.category ILIKE %s"
        params.append(f"%{category_filter}%")
    if min_price:
        query += " AND p.price >= %s"
        params.append(min_price)
    if max_price:
        query += " AND p.price <= %s"
        params.append(max_price)

    cur.execute(query, params)
    products = cur.fetchall()
    cur.close()
    conn.close()

    # Processa ogni prodotto: se esiste un'immagine, la converte in Base64
    processed_products = []
    for p in products:
        image_data = p[6]  # p[6] corrisponde al campo img1
        if image_data:
            # Nel caso in cui il dato sia un memoryview, lo convertiamo in bytes
            if isinstance(image_data, memoryview):
                image_data = image_data.tobytes()
            encoded_image = "data:image/jpeg;base64," + base64.b64encode(image_data).decode('utf-8')
        else:
            encoded_image = None
        # Creiamo una tupla con i dati aggiornati, dove la settima posizione contiene l'immagine codificata
        processed_products.append((p[0], p[1], p[2], p[3], p[4], p[5], encoded_image))

    # Se la richiesta è AJAX restituisce i dati in JSON
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        products_list = []
        for p in processed_products:
            products_list.append({
                'id': p[0],
                'name': p[1],
                'category': p[2],
                'price': p[3],
                'quantity': p[4],
                'seller_name': p[5],
                'image': p[6]
            })
        return jsonify({'products': products_list})
    
    # Per una richiesta normale, passa i prodotti elaborati al template
    return render_template('dashboard.html', balance=balance, products=processed_products, 
                           name_filter=name_filter, category_filter=category_filter, 
                           min_price=min_price, max_price=max_price)

@app.route('/purchased_products', methods=['GET'])
def purchased_products():
    if 'user_id' not in session:
        flash('You must log in to access this page.', 'danger')
        return redirect(url_for('login'))
    
    buyer_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        # Recupera le transazioni (acquisti) effettuate dall'utente loggato
        cur.execute("""
            SELECT ts.id, ts.id_producr, ts.quantity, ts.total_import, 
                   p.name, p.category, p.price, p.description
            FROM transfer_season ts
            JOIN products p ON ts.id_producr = p.id
            WHERE ts.id_buyerr = %s
            ORDER BY ts.id DESC
        """, (buyer_id,))
        purchases = cur.fetchall()
        cur.close()
        conn.close()
        return render_template('purchased_products.html', purchases=purchases)
    except Exception as e:
        flash('Error retrieving purchases: ' + str(e), 'danger')
        cur.close()
        conn.close()
        return redirect(url_for('dashboard'))

@app.route('/modify_profile', methods=['GET', 'POST'])
def modify_profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))

    user_id = session['user_id']
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        # Recupera i dati del form
        name = request.form.get('name')
        surname = request.form.get('surname')
        birth_date = request.form.get('birth_date')
        username = request.form.get('username')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        # Se l'utente ha inserito una nuova password, esegui i controlli
        if new_password:
            if new_password != confirm_password:
                flash("The passwords do not match.", "danger")
                return redirect(url_for('modify_profile'))
            if len(new_password) < 6:
                flash("The password must be at least 6 characters long.", "danger")
                return redirect(url_for('modify_profile'))
            # Genera la password crittografata
            hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
            cur.execute("""
                UPDATE users 
                SET name=%s, surname=%s, birth_date=%s, username=%s, password=%s
                WHERE id=%s
            """, (name, surname, birth_date, username, hashed_password, user_id))
        else:
            # Aggiornamento senza modificare la password
            cur.execute("""
                UPDATE users 
                SET name=%s, surname=%s, birth_date=%s, username=%s
                WHERE id=%s
            """, (name, surname, birth_date, username, user_id))

        conn.commit()
        cur.close()
        conn.close()

        flash("Profile updated successfully!", "success")
        return redirect(url_for('dashboard'))

    # In caso di GET, recupera i dati correnti dell'utente
    cur.execute("SELECT name, surname, birth_date, username FROM users WHERE id=%s", (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()

    return render_template('modify_profile.html', user=user)



@app.route('/product/<int:product_id>')
def product_details(product_id):
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT p.name, p.category, p.price, p.quantity, p.description, p.id_user, 
               i.img1, i.img2, i.img3
        FROM products p
        left JOIN product_images i ON p.id = i.id_product
        WHERE p.id = %s
    """, (product_id,))
    
    product = cur.fetchone()
    cur.close()
    conn.close()
    
    if not product:
        return "Product not found.", 404
    
    # 🔍 Debug: Controllo immagini
    images = []
    for img in product[6:9]:  # img1, img2, img3
        if img:
            try:
                base64_image = base64.b64encode(img).decode('utf-8')
                images.append(base64_image)
            except Exception as e:
                print(f"Error in Base64 conversion. {e}")

    product_data = {
        'name': product[0],
        'category': product[1],
        'price': product[2],
        'quantity': product[3],
        'description': product[4],
        'seller_id': product[5],
        'images': images
    }
    
    return render_template('product_details.html', product=product_data)


@app.route('/purchase_product/<int:product_id>', methods=['POST'])
def purchase_product(product_id):
    if 'user_id' not in session:
        flash('You must log in to make a purchase.', 'danger')
        return redirect(url_for('login'))

    buyer_id = session['user_id']

    # Recupera le informazioni del prodotto
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id_user, price, quantity FROM products WHERE id = %s", (product_id,))
    product = cur.fetchone()

    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('dashboard'))

    seller_id, price, available_quantity = product

    # Verifica la disponibilità del prodotto
    if available_quantity <= 0:
        flash('The product is not available for purchase.', 'danger')
        return redirect(url_for('dashboard'))

    # Calcola il totale
    quantity_to_buy = int(request.form['quantity'])  # Prendi la quantità dal form
    total_price = price * quantity_to_buy

    # Verifica il saldo dell'acquirente
    cur.execute("SELECT balance FROM users WHERE id = %s", (buyer_id,))
    buyer_balance = cur.fetchone()[0]

    if buyer_balance < total_price:
        flash('Saldo insufficiente per completare l\'acquisto.', 'danger')
        return redirect(url_for('dashboard'))

    # Aggiorna il saldo dell'acquirente e il prodotto
    try:
        # Aggiorna il saldo dell'acquirente
        cur.execute("UPDATE users SET balance = balance - %s WHERE id = %s", (total_price, buyer_id))

        # Aggiorna la quantità del prodotto
        cur.execute("UPDATE products SET quantity = quantity - %s WHERE id = %s", (quantity_to_buy, product_id))

        # Aggiungi la transazione nella tabella transfer_season
        cur.execute("""
            INSERT INTO transfer_season (id_seller, id_buyerr, id_producr, quantity, total_import)
            VALUES (%s, %s, %s, %s, %s)
        """, (seller_id, buyer_id, product_id, quantity_to_buy, total_price))

        # Aggiorna il saldo del venditore (aggiungendo l'importo ricevuto)
        cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s", (total_price, seller_id))

        conn.commit()
        flash('Purchase completed successfully!', 'success')
        cur.close()
        conn.close()

        return redirect(url_for('dashboard'))

    except Exception as e:
        conn.rollback()
        flash(f'Error during the purchase: {e}', 'danger')
        return redirect(url_for('dashboard'))


@app.route('/my_store', methods=['GET', 'POST'])
def my_store():
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))

    user_id = session['user_id']

    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        description = request.form['description']

        # Recupera i file inviati dal form
        img1_file = request.files.get('img1')
        img2_file = request.files.get('img2')
        img3_file = request.files.get('img3')

        # Leggi i dati binari delle immagini se sono stati caricati
        binary_img1 = psycopg2.Binary(img1_file.read()) if img1_file and img1_file.filename != '' else None
        binary_img2 = psycopg2.Binary(img2_file.read()) if img2_file and img2_file.filename != '' else None
        binary_img3 = psycopg2.Binary(img3_file.read()) if img3_file and img3_file.filename != '' else None

        try:
            conn = get_db_connection()
            cur = conn.cursor()

            # Inserisci il prodotto e recupera il suo id
            cur.execute("""
                INSERT INTO products (name, category, price, quantity, description, id_user)
                VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
            """, (name, category, price, quantity, description, user_id))
            product_id = cur.fetchone()[0]

            # Inserisci tutte le immagini in un'unica riga
            cur.execute("""
                INSERT INTO product_images (id_product, img1, img2, img3)
                VALUES (%s, %s, %s, %s)
            """, (product_id, binary_img1, binary_img2, binary_img3))

            conn.commit()
            cur.close()
            conn.close()

            flash('Product successfully added!', 'success')
            return redirect(url_for('my_store'))
        except Exception as e:
            flash(f'Error while adding the product: {e}', 'danger')
            return redirect(url_for('my_store'))

    # Recupero dei prodotti per la visualizzazione nella pagina GET
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.id, p.name, p.category, p.price, p.quantity, p.description, 
               pi.img1, pi.img2, pi.img3
        FROM products p
        LEFT JOIN product_images pi ON p.id = pi.id_product
        WHERE p.id_user = %s
    """, (user_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    products = []
    for row in rows:
        product_id, name, category, price, quantity, description, img1, img2, img3 = row
        images = []
        if img1:
            images.append(base64.b64encode(img1).decode('utf-8'))
        if img2:
            images.append(base64.b64encode(img2).decode('utf-8'))
        if img3:
            images.append(base64.b64encode(img3).decode('utf-8'))
        products.append({
            'id': product_id,
            'name': name,
            'category': category,
            'price': price,
            'quantity': quantity,
            'description': description,
            'images': images
        })

    return render_template('my_store.html', products=products)


@app.route('/add_product', methods=['POST'])
def add_product():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    name = request.form['name']
    category = request.form['category']
    price = float(request.form['price'])
    quantity = int(request.form['quantity'])
    description = request.form['description']
    
    img1 = request.files.get('img1')
    img2 = request.files.get('img2')
    img3 = request.files.get('img3')
    
    binary_img1 = img1.read() if img1 else None
    binary_img2 = img2.read() if img2 else None
    binary_img3 = img3.read() if img3 else None
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    try:
        # Inserimento del prodotto
        cur.execute("""
            INSERT INTO products (name, category, price, quantity, description, id_user)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        """, (name, category, price, quantity, description, user_id))
        product_id = cur.fetchone()[0]
        
        # Inserimento delle immagini
        cur.execute("""
            INSERT INTO product_images (id_product, img1, img2, img3)
            VALUES (%s, %s, %s, %s)
        """, (product_id, binary_img1, binary_img2, binary_img3))
        
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Error during product insertion:", e)
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('dashboard'))


@app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
def edit_product(product_id):
    if 'user_id' not in session:
        flash('You need to log in.', 'danger')
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Recupera i dettagli del prodotto
    cur.execute("SELECT id, name, category, price, quantity, description FROM products WHERE id = %s AND id_user = %s", (product_id, session['user_id']))
    product = cur.fetchone()
    
    if not product:
        flash('Product not found or unauthorized.', 'danger')
        return redirect(url_for('my_store'))
    
    if request.method == 'POST':
        name = request.form['name']
        category = request.form['category']
        price = float(request.form['price'])
        quantity = int(request.form['quantity'])
        description = request.form['description']
        
        try:
            # Aggiorna i dati del prodotto nel database
            cur.execute("""
                UPDATE products 
                SET name = %s, category = %s, price = %s, quantity = %s, description = %s 
                WHERE id = %s
            """, (name, category, price, quantity, description, product_id))
            conn.commit()
            flash('Product updated successfully!', 'success')
            return redirect(url_for('my_store'))
        except Exception as e:
            flash(f'Error during the update: {e}', 'danger')
    
    cur.close()
    conn.close()

    return render_template('edit_product.html', product=product)




@app.route('/delete_product', methods=['POST'])
def delete_product():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "You must log in."})

    product_id = request.form['id']
    user_id = session['user_id']

    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM product_images WHERE id_product = %s", (product_id,))
        cur.execute("DELETE FROM products WHERE id = %s AND id_user = %s", (product_id, user_id))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({"success": True})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": str(e)})


@app.route('/charge_balance', methods=['POST'])
def charge_balance():
    if 'user_id' not in session:
        return jsonify({"success": False, "message": "You must log in."})

    amount = request.form.get('amount', type=float)
    if amount is None or amount <= 0:
        return jsonify({"success": False, "message": "Please enter a valid amount."})

    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor()
            cur.execute("UPDATE users SET balance = balance + %s WHERE id = %s RETURNING balance", (amount, session['user_id']))
            new_balance = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
            return jsonify({"success": True, "new_balance": new_balance})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    return jsonify({"success": False, "message": "Database connection error."})

@app.route('/view_product/<int:product_id>')
def view_product(product_id):
    product = get_product_by_id(product_id)
    if not product:
        flash('Product not found.', 'danger')
        return redirect(url_for('dashboard'))
    
    images = get_product_images(product_id)
    # Aggiunge le immagini al dizionario del prodotto
    product['images'] = images

    return render_template('view_product.html', product=product)


# Funzione per ottenere i dettagli del prodotto
def get_product_by_id(product_id):
    conn = get_db_connection()
    if not conn:
        return None
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, category, price, quantity, description FROM products WHERE id = %s",
        (product_id,)
    )
    product_row = cur.fetchone()
    cur.close()
    conn.close()
    if product_row:
        product = {
            'id': product_row[0],
            'name': product_row[1],
            'category': product_row[2],
            'price': product_row[3],
            'quantity': product_row[4],
            'description': product_row[5]
        }
        return product
    return None


import base64

def get_product_images(product_id):
    conn = get_db_connection()
    if not conn:
        return []
    cur = conn.cursor()
    cur.execute(
        "SELECT img1, img2, img3 FROM product_images WHERE id_product = %s",
        (product_id,)
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    image_list = []
    if row:
        for img in row:
            if img:
                try:
                    # Se l'immagine è di tipo memoryview, converti in bytes
                    if isinstance(img, memoryview):
                        img = img.tobytes()
                    encoded_image = base64.b64encode(img).decode('utf-8')
                    image_list.append(encoded_image)
                except Exception as e:
                    print(f"Error in Base64 conversion: {e}")
    return image_list



@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))
@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        print(f"Entered username: {username}, Entered password: {password}")  # Debug

        if username == 'admin' and password == 'admin':
            session['admin_logged_in'] = True
            print("Login successful!")  # Debug
            flash("Administrator access successful!", "success")
            return redirect(url_for('admin_dashboard'))
        else:
            print("Login failed!")  # Debug
            flash("Invalid admin credentials.", "danger")

    return render_template('admin_login.html')


@app.route('/admin_dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        flash("You must log in as an administrator to access the dashboard.", "danger")
        return redirect(url_for('admin_login'))

    return render_template('admin_dashboard.html')


@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash("Administrator logout successful.", "success")
    return redirect(url_for('admin_login'))

@app.route('/toggle_user_status/<int:user_id>', methods=['POST'])
def toggle_user_status(user_id):
    if not session.get('admin_logged_in'):
        flash("Access denied!", "danger")
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # Otteniamo lo stato attuale dell'utente
    cursor.execute('SELECT active FROM users WHERE id = %s', (user_id,))
    user = cursor.fetchone()

    if user is None:
        flash("User not found!", "danger")
    else:
        new_status = not user[0]  # Invertiamo lo stato (da True a False e viceversa)
        cursor.execute('UPDATE users SET active = %s WHERE id = %s', (new_status, user_id))
        conn.commit()

        status_text = "attivato" if new_status else "disattivato"
        flash(f"Utente {status_text} con successo!", "success")

    cursor.close()
    conn.close()
    
    return redirect(url_for('manage_users'))
@app.route('/manage_users')
def manage_users():
    if not session.get('admin_logged_in'):
        flash("You need to log in as an administrator.", "danger")
        return redirect(url_for('admin_login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id, name, surname, username, birth_date, balance, active FROM users')
    users = [
        {
            "id": row[0],
            "name": row[1],
            "surname": row[2],
            "username": row[3],
            "birth_date": row[4],
            "balance": row[5],
            "active": row[6],  # Aggiungiamo il campo active
        }
        for row in cursor.fetchall()
    ]

    cursor.close()
    conn.close()

    return render_template('admin_users.html', users=users)


# Rotta per eliminare un utente



if __name__ == '__main__':
    app.run(debug=True)