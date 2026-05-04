# app.py - Pystore Optimized Version
# ✅ Cache per-request, batch lookup, lazy loading ready, performance logging

import os
import hashlib
import base64
import requests
import secrets
import time
import threading
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))

# ===================== CONFIG =====================
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

DEFAULT_IMG = "https://placehold.co/400x300?text=No+Image"

# Midtrans Config
MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "")
MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY", "")
MIDTRANS_SNAP_URL   = "https://app.sandbox.midtrans.com/snap/snap.js"
MIDTRANS_API_URL    = "https://app.sandbox.midtrans.com/snap/v1/transactions"

# JSONBin Config
JSONBIN_BIN_ID  = os.environ.get("JSONBIN_BIN_ID",  "69cc62dfaaba882197b1ce2d")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY",  "$2a$10$ZM2UievsWh.L.67pqGxzqOLfou5wub3IHXNeEwj9Q1X4KpxPRYlte")
JSONBIN_URL     = "https://api.jsonbin.io/v3/b/" + JSONBIN_BIN_ID

# Fallback STORE (hanya jika JSONBin down)
STORE = {
    "barang": [
        {"id": 1, "nama": "Indomie Goreng",      "harga": 3000, "gambar": "https://yoline.co.id/media/products/ProductIndomie_goreng_special_jumbo_129gr.png", "stok": 100},
        {"id": 2, "nama": "Air Mineral 600ml",   "harga": 2000, "gambar": "https://down-id.img.susercontent.com/file/id-11134201-23030-gby2tljppfov1a",  "stok": 100},
        {"id": 3, "nama": "Roti Tawar",          "harga": 7000, "gambar": "https://image.astronauts.cloud/product-images/2025/7/RotitawarJumboRevisi2_bbad0227-c7a3-4788-9628-5dd6144aeed6_900x900.jpg",   "stok": 100},
        {"id": 4, "nama": "Telur Ayam (1 butir)","harga": 1500, "gambar": "https://ichef.bbci.co.uk/ace/ws/800/cpsprodpb/16CE/production/_105483850_35a5b348-5c3f-45ca-94d7-4210aebc1a8e.jpg.webp", "stok": 100},
        {"id": 5, "nama": "Susu UHT Full Cream", "harga": 5000, "gambar": "https://www.jni.co.id/cdn/shop/products/b1d42094-90a1-42a2-bf81-b183d95a2243-fullcream-946ml.jpg?v=1738552499",        "stok": 100},
    ],
    "next_id": 6,
    "orders": [],
    "qris_url": "",
    "pending_orders": {}
}

# Admin password hash
_ADMIN_PW_DEFAULT   = hashlib.sha256("admin1234".encode()).hexdigest()
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", _ADMIN_PW_DEFAULT)

# ===================== CACHE HELPER (NEW!) =====================
_request_cache = {}
_cache_lock = threading.Lock()

def get_cached_data(key, fetch_func, ttl_seconds=20):
    """Cache helper dengan TTL sederhana untuk hindari HTTP request berulang."""
    now = time.time()
    with _cache_lock:
        entry = _request_cache.get(key)
        if entry and (now - entry['time']) < ttl_seconds:
            return entry['data']
    data = fetch_func()
    with _cache_lock:
        _request_cache[key] = {'data': data, 'time': now}
    return data

def clear_cache():
    """Panggil setelah write ke JSONBin agar cache tidak stale."""
    global _request_cache
    with _cache_lock:
        _request_cache.clear()

# ===================== JSONBIN HELPERS (OPTIMIZED) =====================
def jsonbin_get():
    """Ambil data dari JSONBin dengan caching per-request."""
    cache_key = "jsonbin_main"
    
    def _fetch():
        try:
            resp = requests.get(
                JSONBIN_URL + "/latest",
                headers={"X-Master-Key": JSONBIN_API_KEY},
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json().get("record", {})
                if not data or not data.get("barang"):
                    return dict(STORE)
                data.setdefault("pending_orders", {})
                data.setdefault("qris_url", "")
                data.setdefault("orders", [])
                return data
        except Exception as e:
            print(f"⚠️ Error load JSONBin: {e}")
        return dict(STORE)
    
    return get_cached_data(cache_key, _fetch, ttl_seconds=20)

def jsonbin_set(data):
    """Simpan data ke JSONBin + clear cache."""
    try:
        requests.put(
            JSONBIN_URL,
            json=data,
            headers={"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"},
            timeout=5
        )
        clear_cache()  # ← Penting: clear cache setelah write!
    except Exception as e:
        print(f"⚠️ Error save JSONBin: {e}")

# ===================== DATA HELPERS (OPTIMIZED) =====================
def get_barang():
    return jsonbin_get().get("barang", [])

def get_orders():
    return jsonbin_get().get("orders", [])

def get_qris():
    return jsonbin_get().get("qris_url", "")

def set_qris(url):
    data = jsonbin_get()
    data["qris_url"] = url
    jsonbin_set(data)

def add_order(order):
    data = jsonbin_get()
    data.setdefault("orders", []).append(order)
    jsonbin_set(data)

def item_by_id(iid, products_dict=None):
    """Lookup O(1) jika products_dict disediakan, fallback ke linear search."""
    if products_dict is not None:
        return products_dict.get(iid)
    return next((b for b in get_barang() if b.get("id") == iid), None)

def kurangi_stok_batch(keranjang_items):
    """Kurangi stok dengan 1x fetch + 1x write ke JSONBin (batch update)."""
    data = jsonbin_get()
    products = {b['id']: b for b in data.get("barang", [])}
    
    updated = False
    for k in keranjang_items:
        if k["id"] in products:
            old_stok = products[k["id"]].get("stok", 0)
            products[k["id"]]["stok"] = max(0, old_stok - k["jumlah"])
            updated = True
    
    if updated:
        data["barang"] = list(products.values())
        jsonbin_set(data)  # ← Sudah ada clear_cache() di dalam jsonbin_set

def get_next_id():
    data = jsonbin_get()
    nid  = data.get("next_id", 6)
    data["next_id"] = nid + 1
    jsonbin_set(data)
    return nid

def save_pending_order(order_id, keranjang, pelanggan):
    data = jsonbin_get()
    data.setdefault("pending_orders", {})[order_id] = {
        "keranjang": keranjang,
        "pelanggan": pelanggan
    }
    jsonbin_set(data)

def pop_pending_order(order_id):
    data    = jsonbin_get()
    pending = data.get("pending_orders", {})
    result  = pending.pop(order_id, None)
    if result:
        data["pending_orders"] = pending
        jsonbin_set(data)
    return result

# ===================== SESSION / GAMBAR HELPERS (OPTIMIZED) =====================
def safe_gambar(gambar, item_id):
    if gambar and gambar.startswith(""):
        return "b64" + str(item_id)
    return gambar

def restore_gambar_batch(keranjang, products_dict=None):
    """Restore gambar dengan lookup O(1), bukan N HTTP requests."""
    if products_dict is None:
        products_dict = {b['id']: b for b in get_barang()}
    
    result = []
    for k in keranjang:
        item = dict(k)
        if str(item.get("gambar", "")).startswith("b64"):
            b = products_dict.get(item["id"])
            item["gambar"] = b.get("gambar", "") if b else DEFAULT_IMG
        result.append(item)
    return result

def produk_for_order(keranjang):
    return [{"id": k["id"], "nama": k["nama"], "harga": k["harga"],
             "jumlah": k["jumlah"], "subtotal": k["subtotal"]} for k in keranjang]

# ===================== PERFORMANCE LOGGING (NEW!) =====================
@app.before_request
def before_request():
    request.start_time = time.time()

@app.after_request
def after_request(response):
    if hasattr(request, 'start_time'):
        duration = time.time() - request.start_time
        if duration > 1.0:
            print(f"⚠️ Slow request: {request.path} — {duration:.2f}s")
    return response

# ===================== PUBLIC =====================
@app.route("/")
def index():
    products = get_barang()
    return render_template("index.html", barang=products,
                           pembeli=session.get("pembeli_nama"), default_img=DEFAULT_IMG)

@app.route("/login-pembeli", methods=["GET", "POST"])
def login_pembeli():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        if not nama:
            flash("Nama tidak boleh kosong!", "error")
            return redirect(url_for("login_pembeli"))
        session["pembeli_nama"] = nama
        session["keranjang"]   = []
        flash("Selamat datang, " + nama + "! 👋", "success")
        return redirect(url_for("index"))
    return render_template("login_pembeli.html")

@app.route("/logout-pembeli")
def logout_pembeli():
    session.pop("pembeli_nama", None)
    session.pop("keranjang",    None)
    flash("Berhasil keluar.", "info")
    return redirect(url_for("index"))

# ===================== KERANJANG (OPTIMIZED!) =====================
@app.route("/keranjang")
def keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    
    # ✅ Fetch produk SEKALI, konversi ke dict untuk O(1) lookup
    products_list = get_barang()
    products_dict = {b['id']: b for b in products_list}
    
    # ✅ Batch restore gambar
    raw_cart = session.get("keranjang", [])
    restored = restore_gambar_batch(raw_cart, products_dict)
    
    # ✅ Hitung total di backend (bukan di Jinja)
    total = sum(item['subtotal'] for item in restored)
    
    qris = get_qris()
    return render_template("keranjang.html", 
                          keranjang=restored,
                          pembeli=session["pembeli_nama"], 
                          default_img=DEFAULT_IMG,
                          qris_tersedia=bool(qris),
                          total=total)  # ← Kirim total ke template

@app.route("/tambah-keranjang", methods=["POST"])
def tambah_keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    try:
        id_beli = int(request.form.get("id_barang"))
        qty     = int(request.form.get("qty", 1))
        if qty <= 0:
            flash("Jumlah minimal 1.", "error")
            return redirect(url_for("index"))
    except (ValueError, TypeError):
        flash("Input tidak valid.", "error")
        return redirect(url_for("index"))

    # ✅ Fetch produk SEKALI untuk lookup
    products = {b['id']: b for b in get_barang()}
    b = products.get(id_beli)
    
    if not b:
        flash("Barang tidak ditemukan.", "error")
        return redirect(url_for("index"))

    stok     = b.get("stok", 0)
    cart     = session.get("keranjang", [])
    existing = next((k for k in cart if k["id"] == id_beli), None)
    sudah    = existing["jumlah"] if existing else 0

    if stok < sudah + qty:
        flash("Stok tidak mencukupi! Sisa: " + str(max(0, stok - sudah)), "error")
        return redirect(url_for("index"))

    if existing:
        existing["jumlah"]  += qty
        existing["subtotal"] = existing["harga"] * existing["jumlah"]
    else:
        cart.append({
            "id": b["id"], "nama": b["nama"], "harga": b["harga"],
            "gambar": safe_gambar(b.get("gambar", ""), b["id"]),
            "jumlah": qty, "subtotal": b["harga"] * qty
        })
    session["keranjang"] = cart
    flash("✅ " + b["nama"] + " x" + str(qty) + " ditambahkan ke keranjang.", "success")
    return redirect(url_for("index"))

@app.route("/hapus-keranjang/<int:item_id>")
def hapus_keranjang(item_id):
    session["keranjang"] = [k for k in session.get("keranjang", []) if k["id"] != item_id]
    flash("Item dihapus dari keranjang.", "info")
    return redirect(url_for("keranjang"))

# ===================== PILIH METODE =====================
@app.route("/pilih-bayar", methods=["POST"])
def pilih_bayar():
    if not session.get("pembeli_nama"):
        return redirect(url_for("login_pembeli"))
    if not session.get("keranjang"):
        flash("Keranjang kosong!", "error")
        return redirect(url_for("keranjang"))
    metode = request.form.get("metode", "midtrans")
    if metode == "cod":  return redirect(url_for("form_cod"))
    if metode == "qris": return redirect(url_for("bayar_qris"))
    return redirect(url_for("bayar"))

# ===================== COD (OPTIMIZED) =====================
@app.route("/cod", methods=["GET", "POST"])
def form_cod():
    if not session.get("pembeli_nama"):
        return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error")
        return redirect(url_for("keranjang"))
    
    # ✅ Batch restore
    products_dict = {b['id']: b for b in get_barang()}
    keranjang = restore_gambar_batch(raw, products_dict)

    if request.method == "POST":
        nama    = request.form.get("nama",    "").strip()
        telepon = request.form.get("telepon", "").strip()
        alamat  = request.form.get("alamat",  "").strip()
        catatan = request.form.get("catatan", "").strip()
        if not nama or not telepon or not alamat:
            flash("Nama, telepon, dan alamat wajib diisi!", "error")
            return redirect(url_for("form_cod"))

        total    = sum(k["subtotal"] for k in keranjang)
        order_id = "COD-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]

        # ✅ Batch stok update
        kurangi_stok_batch(keranjang)

        order = {
            "order_id": order_id, "pelanggan": session["pembeli_nama"],
            "nama_penerima": nama, "telepon": telepon, "alamat": alamat, "catatan": catatan,
            "produk": produk_for_order(keranjang), "total": total, "metode": "COD",
            "status": "Menunggu Konfirmasi", "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        }
        add_order(order)
        session["struk"]     = {**order, "bayar": 0, "kembalian": 0}
        session["keranjang"] = []
        return redirect(url_for("struk_page"))

    total = sum(k["subtotal"] for k in keranjang)
    return render_template("cod.html", keranjang=keranjang, total=total, pembeli=session["pembeli_nama"])

# ===================== QRIS (OPTIMIZED) =====================
@app.route("/bayar-qris")
def bayar_qris():
    if not session.get("pembeli_nama"):
        return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error")
        return redirect(url_for("keranjang"))
    qris = get_qris()
    if not qris:
        flash("QRIS belum tersedia. Pilih metode lain.", "warning")
        return redirect(url_for("keranjang"))
    
    products_dict = {b['id']: b for b in get_barang()}
    keranjang = restore_gambar_batch(raw, products_dict)
    total     = sum(k["subtotal"] for k in keranjang)
    order_id  = "QRIS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
    session["order_id"]    = order_id
    session["order_total"] = total
    return render_template("bayar_qris.html", qris_url=qris, total=total,
                           order_id=order_id, pembeli=session["pembeli_nama"])

@app.route("/konfirmasi-qris", methods=["POST"])
def konfirmasi_qris():
    if not session.get("pembeli_nama"):
        return redirect(url_for("login_pembeli"))
    raw       = session.get("keranjang", [])
    products_dict = {b['id']: b for b in get_barang()}
    keranjang = restore_gambar_batch(raw, products_dict)
    total     = session.get("order_total", sum(k["subtotal"] for k in keranjang))
    order_id  = session.get("order_id", "QRIS-" + datetime.now().strftime("%Y%m%d%H%M%S"))

    # ✅ Batch stok update
    kurangi_stok_batch(keranjang)

    order = {
        "order_id": order_id, "pelanggan": session["pembeli_nama"],
        "produk": produk_for_order(keranjang), "total": total, "metode": "QRIS",
        "status": "Menunggu Verifikasi", "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    }
    add_order(order)
    session["struk"]     = {**order, "bayar": total, "kembalian": 0}
    session["keranjang"] = []
    return redirect(url_for("struk_page"))

# ===================== MIDTRANS (OPTIMIZED) =====================
@app.route("/bayar", methods=["GET", "POST"])
def bayar():
    if not session.get("pembeli_nama"):
        return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error")
        return redirect(url_for("keranjang"))
    
    products_dict = {b['id']: b for b in get_barang()}
    keranjang = restore_gambar_batch(raw, products_dict)
    total     = sum(k["subtotal"] for k in keranjang)
    order_id  = "PYSTORE-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
    session["order_id"]    = order_id
    session["order_total"] = total

    item_details = [{"id": str(k["id"]), "price": k["harga"],
                     "quantity": k["jumlah"], "name": k["nama"][:50]} for k in keranjang]
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": total},
        "item_details": item_details,
        "customer_details": {"first_name": session["pembeli_nama"]},
        "callbacks": {
            "finish":  url_for("struk_page", _external=True),
            "error":   url_for("keranjang",  _external=True),
            "pending": url_for("struk_page", _external=True)
        }
    }
    try:
        auth = base64.b64encode((MIDTRANS_SERVER_KEY + ":").encode()).decode()
        resp = requests.post(MIDTRANS_API_URL, json=payload, headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "Authorization": "Basic " + auth}, timeout=15)
        result = resp.json()
        if "token" in result:
            save_pending_order(order_id, produk_for_order(keranjang), session["pembeli_nama"])
            return render_template("bayar.html", snap_token=result["token"],
                                   client_key=MIDTRANS_CLIENT_KEY, snap_url=MIDTRANS_SNAP_URL,
                                   total=total, pembeli=session["pembeli_nama"])
        else:
            flash("Gagal: " + str(result.get("error_messages", result)), "error")
            return redirect(url_for("keranjang"))
    except Exception as e:
        flash("Error Midtrans: " + str(e), "error")
        return redirect(url_for("keranjang"))

@app.route("/payment-success", methods=["POST"])
def payment_success():
    """Dipanggil dari browser via JS setelah snap.pay sukses."""
    data = request.get_json() or {}
    products_dict = {b['id']: b for b in get_barang()}
    struk = {
        "pelanggan": session.get("pembeli_nama", "Tamu"),
        "tanggal":   datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "produk":    produk_for_order(restore_gambar_batch(session.get("keranjang", []), products_dict)),
        "total":     session.get("order_total", 0),
        "bayar":     session.get("order_total", 0),
        "kembalian": 0,
        "order_id":  session.get("order_id", "-"),
        "metode":    "Midtrans - " + data.get("payment_type", "-"),
        "status":    data.get("transaction_status", "settlement")
    }
    session["struk"]     = struk
    session["keranjang"] = []
    return jsonify({"status": "ok"})

@app.route("/struk")
def struk_page():
    struk = session.get("struk")
    if not struk:
        return redirect(url_for("index"))
    return render_template("struk.html", struk=struk, pembeli=session.get("pembeli_nama"))

@app.route("/notifikasi-midtrans", methods=["POST"])
def notifikasi_midtrans():
    """Webhook dari server Midtrans — TIDAK ADA session di sini."""
    data = request.get_json()
    if not data:
        return jsonify({"status": "ignored"}), 200

    oid = data.get("order_id", "")
    sig = hashlib.sha512((
        oid +
        str(data.get("status_code",   "")) +
        str(data.get("gross_amount",  "")) +
        MIDTRANS_SERVER_KEY
    ).encode()).hexdigest()

    if sig != data.get("signature_key", ""):
        return jsonify({"status": "invalid"}), 403

    status = data.get("transaction_status")
    if status in ["settlement", "capture"]:
        pending = pop_pending_order(oid)
        if not pending:
            print(f"⚠️  Webhook: pending order {oid} tidak ditemukan.")
            return jsonify({"status": "ok"}), 200

        keranjang = pending.get("keranjang", [])
        pelanggan = pending.get("pelanggan", "Guest")

        # ✅ Batch stok update
        kurangi_stok_batch(keranjang)

        order = {
            "order_id": oid,
            "pelanggan": pelanggan,
            "produk":   keranjang,
            "total":    float(data.get("gross_amount", 0)),
            "metode":   data.get("payment_type", "Midtrans"),
            "status":   "LUNAS",
            "tanggal":  datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        }
        add_order(order)
        print(f"✅ Webhook Midtrans: Order {oid} LUNAS — {pelanggan}.")

    return jsonify({"status": "ok"}), 200

# ===================== ADMIN (OPTIMIZED) =====================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        input_hash = hashlib.sha256(request.form.get("password", "").encode()).hexdigest()
        if input_hash == ADMIN_PASSWORD_HASH:
            session["admin_logged_in"] = True
            flash("Login admin berhasil! ✅", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Password salah!", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("index"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    qris = get_qris()
    return render_template("admin_dashboard.html", barang=get_barang(),
                           default_img=DEFAULT_IMG, qris_url=qris)

@app.route("/admin/orders")
def admin_orders():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    return render_template("admin_orders.html", orders=get_orders())

@app.route("/admin/set-qris", methods=["POST"])
def admin_set_qris():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    qris_url  = request.form.get("qris_url", "").strip()
    qris_file = request.files.get("qris_file")
    if qris_file and qris_file.filename:
        raw  = qris_file.read()
        ext  = qris_file.filename.rsplit(".", 1)[-1].lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        b64  = "" + mime + ";base64," + base64.b64encode(raw).decode()
        set_qris(b64)
        flash("✅ QRIS berhasil diupload dan disimpan permanen!", "success")
    elif qris_url:
        set_qris(qris_url)
        flash("✅ QRIS berhasil disimpan permanen!", "success")
    else:
        flash("Masukkan URL atau upload file QRIS!", "error")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/tambah", methods=["POST"])
def admin_tambah():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    nama   = request.form.get("nama",   "").strip()
    gambar = request.form.get("gambar", "").strip()
    try:
        harga = int(request.form.get("harga", 0))
        stok  = int(request.form.get("stok",  0))
        if harga < 0 or stok < 0:
            flash("Harga/stok tidak boleh negatif!", "error")
            return redirect(url_for("admin_dashboard"))
    except ValueError:
        flash("Harga/stok harus angka!", "error")
        return redirect(url_for("admin_dashboard"))
    if not nama:
        flash("Nama tidak boleh kosong!", "error")
        return redirect(url_for("admin_dashboard"))

    nid  = get_next_id()
    data = jsonbin_get()
    data.setdefault("barang", []).append({"id": nid, "nama": nama, "harga": harga, "gambar": gambar, "stok": stok})
    jsonbin_set(data)
    flash("✅ '" + nama + "' ditambahkan!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:item_id>", methods=["GET", "POST"])
def admin_edit(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    data = jsonbin_get()
    item = next((b for b in data.get("barang", []) if b.get("id") == item_id), None)
    if not item:
        flash("Barang tidak ditemukan.", "error")
        return redirect(url_for("admin_dashboard"))

    if request.method == "POST":
        nama   = request.form.get("nama",   "").strip()
        gambar = request.form.get("gambar", "").strip()
        try:
            harga = int(request.form.get("harga", 0))
            stok  = int(request.form.get("stok",  item.get("stok", 0)))
            if harga < 0 or stok < 0:
                flash("Harga/stok tidak boleh negatif!", "error")
                return redirect(url_for("admin_edit", item_id=item_id))
        except ValueError:
            flash("Harga/stok harus angka!", "error")
            return redirect(url_for("admin_edit", item_id=item_id))
        if not nama:
            flash("Nama tidak boleh kosong!", "error")
            return redirect(url_for("admin_edit", item_id=item_id))

        item["nama"]  = nama
        item["harga"] = harga
        item["stok"]  = stok
        if gambar:
            item["gambar"] = gambar
        jsonbin_set(data)
        flash("✅ Berhasil diperbarui!", "success")
        return redirect(url_for("admin_dashboard"))

    return render_template("admin_edit.html", item=item, default_img=DEFAULT_IMG)

@app.route("/admin/hapus/<int:item_id>")
def admin_hapus(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    data  = jsonbin_get()
    awal  = len(data.get("barang", []))
    data["barang"] = [b for b in data.get("barang", []) if b["id"] != item_id]
    hapus = len(data["barang"]) < awal
    jsonbin_set(data)
    flash("🗑️ Dihapus." if hapus else "Tidak ditemukan.", "success" if hapus else "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=False)
