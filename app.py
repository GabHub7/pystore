import os
import hashlib
import base64
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "pystore-vercel-secret-2024")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")
DEFAULT_IMG = "https://placehold.co/400x300?text=No+Image"

# Midtrans Config
MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "").strip()
MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY", "").strip()
MIDTRANS_SNAP_URL = "https://app.sandbox.midtrans.com/snap/snap.js"
MIDTRANS_API_URL = "https://app.sandbox.midtrans.com/snap/v1/transactions"

# JSONBin Config
JSONBIN_BIN_ID = os.environ.get("JSONBIN_BIN_ID", "")
JSONBIN_API_KEY = os.environ.get("JSONBIN_API_KEY", "")
JSONBIN_URL = f"https://api.jsonbin.io/v3/b/{JSONBIN_BIN_ID}"

# Default Store Data
DEFAULT_STORE = {
    "barang": [
        {"id": 1, "nama": "Indomie Goreng", "harga": 3000, "gambar": "", "stok": 100},
        {"id": 2, "nama": "Air Mineral", "harga": 2000, "gambar": "", "stok": 100},
        {"id": 3, "nama": "Roti Tawar", "harga": 7000, "gambar": "", "stok": 100},
        {"id": 4, "nama": "Telur (1 butir)", "harga": 1500, "gambar": "", "stok": 100},
        {"id": 5, "nama": "Susu UHT", "harga": 5000, "gambar": "", "stok": 100},
    ],
    "next_id": 6,
    "orders": [],
    "qris_url": ""
}

# ==========================================
# ✅ FIX: JSONBIN PERSISTENCE (Mencegah Data/Gambar Hilang)
# ==========================================
def jsonbin_get_bin():
    try:
        resp = requests.get(JSONBIN_URL + "/latest", headers={"X-Master-Key": JSONBIN_API_KEY}, timeout=5)
        if resp.status_code == 200:
            return resp.json().get("record", DEFAULT_STORE)
    except Exception:
        pass
    return DEFAULT_STORE.copy()

def jsonbin_set_bin(data):
    try:
        requests.put(JSONBIN_URL, json=data, headers={"X-Master-Key": JSONBIN_API_KEY, "Content-Type": "application/json"}, timeout=5)
    except Exception as e:
        print(f"❌ Gagal simpan ke JSONBin: {e}")

# Load data saat startup
STORE = jsonbin_get_bin()
if "next_id" not in STORE: STORE["next_id"] = len(STORE["barang"]) + 1
if "orders" not in STORE: STORE["orders"] = []
if "qris_url" not in STORE: STORE["qris_url"] = ""

def save_store():
    """Simpan seluruh state ke JSONBin"""
    jsonbin_set_bin(STORE)

# ==========================================
# HELPERS
# ==========================================
def get_barang(): return STORE["barang"]
def get_next_id():
    nid = STORE["next_id"]; STORE["next_id"] += 1; save_store(); return nid
def add_order(o): STORE["orders"].append(o); save_store()
def get_orders(): return STORE["orders"]
def item_by_id(iid): return next((b for b in STORE["barang"] if b["id"] == iid), None)

def safe_gambar(gambar, item_id):
    if gambar and gambar.startswith("data:"): return f"b64_{item_id}"
    return gambar

def restore_gambar(keranjang):
    result = []
    for k in keranjang:
        item = dict(k)
        if str(item.get("gambar", "")).startswith("b64_"):
            b = item_by_id(item["id"])
            item["gambar"] = b.get("gambar", "") if b else ""
        result.append(item)
    return result

def produk_for_order(keranjang):
    return [{"id": k["id"], "nama": k["nama"], "harga": k["harga"],
             "jumlah": k["jumlah"], "subtotal": k["subtotal"]} for k in keranjang]

# ==========================================
# PUBLIC ROUTES
# ==========================================
@app.route("/")
def index():
    return render_template("index.html", barang=get_barang(),
                           pembeli=session.get("pembeli_nama"), default_img=DEFAULT_IMG)

@app.route("/login-pembeli", methods=["GET", "POST"])
def login_pembeli():
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        if not nama:
            flash("Nama tidak boleh kosong!", "error")
            return redirect(url_for("login_pembeli"))
        session["pembeli_nama"] = nama
        session["keranjang"] = session.get("keranjang", [])
        flash(f"Selamat datang, {nama}! 👋", "success")
        return redirect(url_for("index"))
    return render_template("login_pembeli.html")

@app.route("/logout-pembeli")
def logout_pembeli():
    session.pop("pembeli_nama", None)
    session.pop("keranjang", None)
    flash("Berhasil keluar.", "info")
    return redirect(url_for("index"))

# ==========================================
# KERANJANG
# ==========================================
@app.route("/keranjang")
def keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    restored = restore_gambar(session.get("keranjang", []))
    return render_template("keranjang.html", keranjang=restored,
                           pembeli=session["pembeli_nama"], default_img=DEFAULT_IMG,
                           qris_tersedia=bool(STORE.get("qris_url")))

@app.route("/tambah-keranjang", methods=["POST"])
def tambah_keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    try:
        id_beli = int(request.form.get("id_barang"))
        qty = int(request.form.get("qty", 1))
        if qty <= 0: raise ValueError()
    except (ValueError, TypeError):
        flash("Input tidak valid.", "error"); return redirect(url_for("index"))
    
    b = item_by_id(id_beli)
    if not b:
        flash("Barang tidak ditemukan.", "error"); return redirect(url_for("index"))

    stok = b.get("stok", 0)
    keranjang = session.get("keranjang", [])
    existing = next((k for k in keranjang if k["id"] == id_beli), None)
    sudah = existing["jumlah"] if existing else 0

    if stok < sudah + qty:
        flash(f"Stok tidak mencukupi! Sisa: {max(0, stok - sudah)}", "error")
        return redirect(url_for("index"))

    if existing:
        existing["jumlah"] += qty
        existing["subtotal"] = existing["harga"] * existing["jumlah"]
    else:
        keranjang.append({
            "id": b["id"], "nama": b["nama"], "harga": b["harga"],
            "gambar": safe_gambar(b.get("gambar", ""), b["id"]),
            "jumlah": qty, "subtotal": b["harga"] * qty
        })
    session["keranjang"] = keranjang
    flash(f"✅ {b['nama']} x{qty} ditambahkan ke keranjang.", "success")
    return redirect(url_for("index"))

@app.route("/hapus-keranjang/<int:item_id>")
def hapus_keranjang(item_id):
    session["keranjang"] = [k for k in session.get("keranjang", []) if k["id"] != item_id]
    flash("Item dihapus dari keranjang.", "info")
    return redirect(url_for("keranjang"))

# ==========================================
# PILIH METODE & COD & QRIS
# ==========================================
@app.route("/pilih-bayar", methods=["POST"])
def pilih_bayar():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    if not session.get("keranjang"):
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    metode = request.form.get("metode", "midtrans")
    if metode == "cod": return redirect(url_for("form_cod"))
    if metode == "qris": return redirect(url_for("bayar_qris"))
    return redirect(url_for("bayar"))

@app.route("/cod", methods=["GET", "POST"])
def form_cod():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    keranjang = restore_gambar(raw)
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        telepon = request.form.get("telepon", "").strip()
        alamat = request.form.get("alamat", "").strip()
        catatan = request.form.get("catatan", "").strip()
        if not nama or not telepon or not alamat:
            flash("Nama, telepon, dan alamat wajib diisi!", "error")
            return redirect(url_for("form_cod"))
        total = sum(k["subtotal"] for k in keranjang)
        order_id = f"COD-{datetime.now().strftime('%Y%m%d%H%M%S')}-{session['pembeli_nama'].replace(' ', '')[:8]}"
        for k in keranjang:
            b = item_by_id(k["id"])
            if b: b["stok"] = max(0, b.get("stok", 0) - k["jumlah"])
        order = {
            "order_id": order_id, "pelanggan": session["pembeli_nama"],
            "nama_penerima": nama, "telepon": telepon, "alamat": alamat, "catatan": catatan,
            "produk": produk_for_order(keranjang), "total": total, "metode": "COD",
            "status": "Menunggu Konfirmasi", "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        }
        add_order(order)
        session["struk"] = {**order, "bayar": 0, "kembalian": 0}
        session["keranjang"] = []
        save_store()
        return redirect(url_for("struk_page"))
    total = sum(k["subtotal"] for k in keranjang)
    return render_template("cod.html", keranjang=keranjang, total=total, pembeli=session["pembeli_nama"])

@app.route("/bayar-qris")
def bayar_qris():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    qris = STORE.get("qris_url", "")
    if not qris:
        flash("QRIS belum tersedia. Pilih metode lain.", "warning")
        return redirect(url_for("keranjang"))
    keranjang = restore_gambar(raw)
    total = sum(k["subtotal"] for k in keranjang)
    order_id = f"QRIS-{datetime.now().strftime('%Y%m%d%H%M%S')}-{session['pembeli_nama'].replace(' ', '')[:8]}"
    session["order_id"] = order_id
    session["order_total"] = total
    return render_template("bayar_qris.html", qris_url=qris, total=total,
                           order_id=order_id, pembeli=session["pembeli_nama"])

@app.route("/konfirmasi-qris", methods=["POST"])
def konfirmasi_qris():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    keranjang = restore_gambar(raw)
    total = session.get("order_total", sum(k["subtotal"] for k in keranjang))
    order_id = session.get("order_id", f"QRIS-{datetime.now().strftime('%Y%m%d%H%M%S')}")
    for k in keranjang:
        b = item_by_id(k["id"])
        if b: b["stok"] = max(0, b.get("stok", 0) - k["jumlah"])
    order = {
        "order_id": order_id, "pelanggan": session["pembeli_nama"],
        "produk": produk_for_order(keranjang), "total": total, "metode": "QRIS",
        "status": "Menunggu Verifikasi", "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    }
    add_order(order)
    session["struk"] = {**order, "bayar": total, "kembalian": 0}
    session["keranjang"] = []
    save_store()
    return redirect(url_for("struk_page"))

# ==========================================
# ✅ MIDTRANS (FIXED: Premature Stock/Cart Clear Removed)
# ==========================================
@app.route("/bayar", methods=["GET", "POST"])
def bayar():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    keranjang = restore_gambar(raw)
    total = sum(k["subtotal"] for k in keranjang)
    order_id = f"PYSTORE-{datetime.now().strftime('%Y%m%d%H%M%S')}-{session['pembeli_nama'].replace(' ', '')[:8]}"
    
    session["order_id"] = order_id
    session["order_total"] = total

    item_details = [{"id": str(k["id"]), "price": k["harga"],
                     "quantity": k["jumlah"], "name": k["nama"][:50]} for k in keranjang]
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": total},
        "item_details": item_details,
        "customer_details": {"first_name": session["pembeli_nama"]},
        "callbacks": {
            "finish": url_for("struk_page", _external=True),
            "error": url_for("keranjang", _external=True),
            "pending": url_for("keranjang", _external=True)
        }
    }
    try:
        auth = base64.b64encode((MIDTRANS_SERVER_KEY + ":").encode()).decode()
        resp = requests.post(MIDTRANS_API_URL, json=payload, headers={
            "Accept": "application/json", "Content-Type": "application/json",
            "Authorization": "Basic " + auth}, timeout=15)
        result = resp.json()
        if "token" in result:
            # ✅ FIX: TIDAK mengurangi stok & TIDAK mengosongkan keranjang di sini
            return render_template("bayar.html", snap_token=result["token"],
                                   client_key=MIDTRANS_CLIENT_KEY, snap_url=MIDTRANS_SNAP_URL,
                                   total=total, pembeli=session["pembeli_nama"])
        else:
            flash("Gagal: " + str(result.get("error_messages", result)), "error")
            return redirect(url_for("keranjang"))
    except Exception as e:
        flash("Error Midtrans: " + str(e), "error")
        return redirect(url_for("keranjang"))

@app.route("/notifikasi-midtrans", methods=["POST"])
def notifikasi_midtrans():
    data = request.get_json()
    if not data: return jsonify({"status": "ignored"}), 200

    oid = data.get("order_id", "")
    sig = hashlib.sha512((oid + data.get("status_code", "") +
                          str(data.get("gross_amount", "")) + MIDTRANS_SERVER_KEY).encode()).hexdigest()
    
    if sig != data.get("signature_key", ""):
        return jsonify({"status": "invalid"}), 403

    status = data.get("transaction_status")
    fraud = data.get("fraud_status")

    # ✅ FIX: Hanya proses jika pembayaran BERHASIL (settlement/capture)
    if status in ['settlement', 'capture']:
        # Kurangi stok & simpan order ke database
        raw_cart = session.get("keranjang", [])
        keranjang = restore_gambar(raw_cart)
        
        for k in keranjang:
            b = item_by_id(k["id"])
            if b: b["stok"] = max(0, b.get("stok", 0) - k["jumlah"])
            
        order = {
            "order_id": oid, "pelanggan": session.get("pembeli_nama", "Guest"),
            "produk": produk_for_order(keranjang), "total": float(data.get("gross_amount", 0)),
            "metode": data.get("payment_type", "Midtrans"), "status": "LUNAS",
            "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        }
        add_order(order)
        save_store()
        print(f"✅ Webhook Midtrans: Order {oid} LUNAS. Stok dikurangi.")
    elif status in ['cancel', 'deny', 'expire']:
        print(f"⚠️ Webhook Midtrans: Order {oid} {status}. Stok & keranjang tetap aman.")
    else:
        print(f"ℹ️ Webhook Midtrans: Order {oid} status {status}. Menunggu aksi lanjut.")

    return jsonify({"status": "ok"}), 200

@app.route("/struk")
def struk_page():
    struk = session.get("struk")
    if not struk:
        # Jika belum ada struk di session, cek apakah order_id ada di orders & lunas
        oid = session.get("order_id")
        paid_order = next((o for o in get_orders() if o.get("order_id") == oid and o.get("status") == "LUNAS"), None)
        if paid_order:
            session["struk"] = paid_order
            session["keranjang"] = [] # ✅ Kosongkan keranjang HANYA setelah struk ditampilkan
            return render_template("struk.html", struk=paid_order, pembeli=session.get("pembeli_nama"))
        return redirect(url_for("index"))
    return render_template("struk.html", struk=struk, pembeli=session.get("pembeli_nama"))

# ==========================================
# ADMIN
# ==========================================
@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"): return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
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
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html", barang=get_barang(),
                           default_img=DEFAULT_IMG, qris_url=STORE.get("qris_url", ""))

@app.route("/admin/orders")
def admin_orders():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    return render_template("admin_orders.html", orders=get_orders())

@app.route("/admin/set-qris", methods=["POST"])
def admin_set_qris():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    qris_url = request.form.get("qris_url", "").strip()
    qris_file = request.files.get("qris_file")
    if qris_file and qris_file.filename:
        data = qris_file.read()
        ext = qris_file.filename.rsplit(".", 1)[-1].lower()
        mime = "image/png" if ext == "png" else "image/jpeg"
        b64 = f"data:{mime};base64," + base64.b64encode(data).decode()
        STORE["qris_url"] = b64
        save_store()
        flash("✅ QRIS berhasil diupload dan disimpan permanen!", "success")
    elif qris_url:
        STORE["qris_url"] = qris_url
        save_store()
        flash("✅ QRIS berhasil disimpan permanen!", "success")
    else:
        flash("Masukkan URL atau upload file QRIS!", "error")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/tambah", methods=["POST"])
def admin_tambah():
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    nama = request.form.get("nama", "").strip()
    gambar = request.form.get("gambar", "").strip()
    try:
        harga = int(request.form.get("harga", 0))
        stok = int(request.form.get("stok", 0))
        if harga < 0 or stok < 0:
            flash("Harga/stok tidak boleh negatif!", "error"); return redirect(url_for("admin_dashboard"))
    except ValueError:
        flash("Harga/stok harus angka!", "error"); return redirect(url_for("admin_dashboard"))
    if not nama:
        flash("Nama tidak boleh kosong!", "error"); return redirect(url_for("admin_dashboard"))
    STORE["barang"].append({"id": get_next_id(), "nama": nama, "harga": harga, "gambar": gambar, "stok": stok})
    save_store()
    flash(f"✅ '{nama}' ditambahkan!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:item_id>", methods=["GET", "POST"])
def admin_edit(item_id):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    item = item_by_id(item_id)
    if not item:
        flash("Barang tidak ditemukan.", "error"); return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        gambar = request.form.get("gambar", "").strip()
        try:
            harga = int(request.form.get("harga", 0))
            stok = int(request.form.get("stok", item.get("stok", 0)))
            if harga < 0 or stok < 0:
                flash("Harga/stok tidak boleh negatif!", "error")
                return redirect(url_for("admin_edit", item_id=item_id))
        except ValueError:
            flash("Harga/stok harus angka!", "error")
            return redirect(url_for("admin_edit", item_id=item_id))
        if not nama:
            flash("Nama tidak boleh kosong!", "error")
            return redirect(url_for("admin_edit", item_id=item_id))
        
        # ✅ FIX: Jangan timpa gambar jika form kosong
        item["nama"] = nama
        item["harga"] = harga
        item["stok"] = stok
        if gambar: item["gambar"] = gambar
        
        save_store()
        flash("✅ Berhasil diperbarui!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", item=item, default_img=DEFAULT_IMG)

@app.route("/admin/hapus/<int:item_id>")
def admin_hapus(item_id):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    awal = len(STORE["barang"])
    STORE["barang"] = [b for b in STORE["barang"] if b["id"] != item_id]
    if len(STORE["barang"]) < awal:
        save_store()
        flash("🗑️ Dihapus.", "success")
    else:
        flash("Tidak ditemukan.", "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=False, port=5000)
