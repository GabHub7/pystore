import os
import hashlib
import base64
import requests
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, template_folder=os.path.join(BASE_DIR, 'templates'))
app.secret_key = "pystore-vercel-secret-2024"

ADMIN_PASSWORD = "admin1234"
DEFAULT_IMG = "https://placehold.co/400x300?text=No+Image"

MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "")
MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY", "")
MIDTRANS_SNAP_URL = "https://app.sandbox.midtrans.com/snap/snap.js"
MIDTRANS_API_URL = "https://app.sandbox.midtrans.com/snap/v1/transactions"

# QRIS statis — ganti dengan URL gambar QRIS kamu
QRIS_IMAGE_URL = os.environ.get("QRIS_IMAGE_URL", "")

STORE = {
    "barang": [
        {"id": 1, "nama": "Indomie Goreng", "harga": 3000, "gambar": ""},
        {"id": 2, "nama": "Air Mineral", "harga": 2000, "gambar": ""},
        {"id": 3, "nama": "Roti Tawar", "harga": 7000, "gambar": ""},
        {"id": 4, "nama": "Telur (1 butir)", "harga": 1500, "gambar": ""},
        {"id": 5, "nama": "Susu UHT", "harga": 5000, "gambar": ""},
    ],
    "next_id": 6,
    "orders": [],
    "qris_url": ""
}

def get_barang(): return STORE["barang"]
def get_next_id():
    nid = STORE["next_id"]; STORE["next_id"] += 1; return nid
def add_order(o): STORE["orders"].append(o)
def get_orders(): return STORE["orders"]
def get_qris(): return STORE.get("qris_url") or QRIS_IMAGE_URL

# ===================== PUBLIC =====================

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
        session["keranjang"] = []
        flash("Selamat datang, " + nama + "! 👋", "success")
        return redirect(url_for("index"))
    return render_template("login_pembeli.html")

@app.route("/logout-pembeli")
def logout_pembeli():
    session.pop("pembeli_nama", None)
    session.pop("keranjang", None)
    flash("Berhasil keluar dari panel pembeli.", "info")
    return redirect(url_for("index"))

# ===================== KERANJANG =====================

@app.route("/keranjang")
def keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    return render_template("keranjang.html",
                           keranjang=session.get("keranjang", []),
                           pembeli=session["pembeli_nama"],
                           default_img=DEFAULT_IMG,
                           qris_tersedia=bool(get_qris()))

@app.route("/tambah-keranjang", methods=["POST"])
def tambah_keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    try:
        id_beli = int(request.form.get("id_barang"))
        qty = int(request.form.get("qty", 1))
        if qty <= 0:
            flash("Jumlah minimal 1.", "error"); return redirect(url_for("index"))
    except (ValueError, TypeError):
        flash("Input tidak valid.", "error"); return redirect(url_for("index"))
    item = next((b for b in get_barang() if b["id"] == id_beli), None)
    if not item:
        flash("Barang tidak ditemukan.", "error"); return redirect(url_for("index"))
    keranjang = session.get("keranjang", [])
    existing = next((k for k in keranjang if k["id"] == id_beli), None)
    if existing:
        existing["jumlah"] += qty
        existing["subtotal"] = existing["harga"] * existing["jumlah"]
    else:
        keranjang.append({
            "id": item["id"], "nama": item["nama"], "harga": item["harga"],
            "gambar": item.get("gambar", ""), "jumlah": qty,
            "subtotal": item["harga"] * qty
        })
    session["keranjang"] = keranjang
    flash("✅ " + item["nama"] + " x" + str(qty) + " ditambahkan ke keranjang.", "success")
    return redirect(url_for("index"))

@app.route("/hapus-keranjang/<int:item_id>")
def hapus_keranjang(item_id):
    session["keranjang"] = [k for k in session.get("keranjang", []) if k["id"] != item_id]
    flash("Item dihapus dari keranjang.", "info")
    return redirect(url_for("keranjang"))

# ===================== PILIH METODE BAYAR =====================

@app.route("/pilih-bayar", methods=["POST"])
def pilih_bayar():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    if not session.get("keranjang"):
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    metode = request.form.get("metode", "midtrans")
    if metode == "cod": return redirect(url_for("form_cod"))
    if metode == "qris": return redirect(url_for("bayar_qris"))
    return redirect(url_for("bayar"))

# ===================== COD =====================

@app.route("/cod", methods=["GET", "POST"])
def form_cod():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    keranjang = session.get("keranjang", [])
    if not keranjang:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        telepon = request.form.get("telepon", "").strip()
        alamat = request.form.get("alamat", "").strip()
        catatan = request.form.get("catatan", "").strip()
        if not nama or not telepon or not alamat:
            flash("Nama, telepon, dan alamat wajib diisi!", "error")
            return redirect(url_for("form_cod"))
        total = sum(k["subtotal"] for k in keranjang)
        order_id = "COD-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
        order = {
            "order_id": order_id, "pelanggan": session["pembeli_nama"],
            "nama_penerima": nama, "telepon": telepon, "alamat": alamat, "catatan": catatan,
            "produk": list(keranjang), "total": total, "metode": "COD",
            "status": "Menunggu Konfirmasi", "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
        }
        add_order(order)
        session["struk"] = {**order, "bayar": 0, "kembalian": 0}
        session["keranjang"] = []
        return redirect(url_for("struk_page"))
    total = sum(k["subtotal"] for k in keranjang)
    return render_template("cod.html", keranjang=keranjang, total=total, pembeli=session["pembeli_nama"])

# ===================== QRIS STATIS =====================

@app.route("/bayar-qris")
def bayar_qris():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    keranjang = session.get("keranjang", [])
    if not keranjang:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    qris = get_qris()
    if not qris:
        flash("QRIS belum tersedia. Pilih metode lain.", "warning")
        return redirect(url_for("keranjang"))
    total = sum(k["subtotal"] for k in keranjang)
    order_id = "QRIS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
    session["order_id"] = order_id
    session["order_total"] = total
    session["keranjang_backup"] = list(keranjang)
    return render_template("bayar_qris.html", qris_url=qris, total=total,
                           order_id=order_id, pembeli=session["pembeli_nama"])

@app.route("/konfirmasi-qris", methods=["POST"])
def konfirmasi_qris():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    keranjang = session.get("keranjang_backup", session.get("keranjang", []))
    total = session.get("order_total", 0)
    order_id = session.get("order_id", "QRIS-" + datetime.now().strftime("%Y%m%d%H%M%S"))
    order = {
        "order_id": order_id, "pelanggan": session["pembeli_nama"],
        "produk": keranjang, "total": total, "metode": "QRIS",
        "status": "Menunggu Verifikasi", "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S")
    }
    add_order(order)
    session["struk"] = {**order, "bayar": total, "kembalian": 0}
    session["keranjang"] = []
    session.pop("keranjang_backup", None)
    return redirect(url_for("struk_page"))

# ===================== MIDTRANS =====================

@app.route("/bayar", methods=["GET", "POST"])
def bayar():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    keranjang = session.get("keranjang", [])
    if not keranjang:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    total = sum(k["subtotal"] for k in keranjang)
    order_id = "PYSTORE-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
    session["order_id"] = order_id
    session["order_total"] = total
    session["keranjang_backup"] = list(keranjang)
    item_details = [{"id": str(k["id"]), "price": k["harga"],
                     "quantity": k["jumlah"], "name": k["nama"][:50]} for k in keranjang]
    payload = {
        "transaction_details": {"order_id": order_id, "gross_amount": total},
        "item_details": item_details,
        "customer_details": {"first_name": session["pembeli_nama"]},
        "callbacks": {
            "finish": url_for("struk_page", _external=True),
            "error": url_for("keranjang", _external=True),
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
            session["keranjang"] = []
            return render_template("bayar.html", snap_token=result["token"],
                                   client_key=MIDTRANS_CLIENT_KEY, snap_url=MIDTRANS_SNAP_URL,
                                   total=total, pembeli=session["pembeli_nama"])
        else:
            flash("Gagal membuat transaksi: " + str(result.get("error_messages", result)), "error")
            return redirect(url_for("keranjang"))
    except Exception as e:
        flash("Error koneksi ke Midtrans: " + str(e), "error")
        return redirect(url_for("keranjang"))

@app.route("/payment-success", methods=["POST"])
def payment_success():
    data = request.get_json() or {}
    keranjang = session.get("keranjang_backup", [])
    total = session.get("order_total", 0)
    order_id = session.get("order_id", "-")
    struk = {
        "pelanggan": session.get("pembeli_nama", "Tamu"),
        "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "produk": keranjang, "total": total, "bayar": total, "kembalian": 0,
        "order_id": order_id,
        "metode": "Midtrans - " + data.get("payment_type", "-"),
        "status": data.get("transaction_status", "settlement")
    }
    session["struk"] = struk
    add_order({"order_id": order_id, "pelanggan": session.get("pembeli_nama", "Tamu"),
               "produk": keranjang, "total": total,
               "metode": "Midtrans - " + data.get("payment_type", "-"),
               "status": data.get("transaction_status", "settlement"),
               "tanggal": struk["tanggal"]})
    session.pop("keranjang_backup", None)
    return jsonify({"status": "ok"})

@app.route("/struk")
def struk_page():
    struk = session.get("struk")
    if not struk: return redirect(url_for("index"))
    return render_template("struk.html", struk=struk, pembeli=session.get("pembeli_nama"))

@app.route("/notifikasi-midtrans", methods=["POST"])
def notifikasi_midtrans():
    data = request.get_json()
    if not data: return jsonify({"status": "ignored"}), 200
    order_id = data.get("order_id", "")
    sig = hashlib.sha512((order_id + data.get("status_code", "") + data.get("gross_amount", "") + MIDTRANS_SERVER_KEY).encode()).hexdigest()
    if sig != data.get("signature_key", ""): return jsonify({"status": "invalid"}), 403
    return jsonify({"status": "ok"}), 200

# ===================== ADMIN =====================

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"): return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        if request.form.get("password", "") == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Login admin berhasil! ✅", "success")
            return redirect(url_for("admin_dashboard"))
        flash("Password salah! Akses ditolak.", "error")
    return render_template("admin_login.html")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    flash("Berhasil keluar dari panel admin.", "info")
    return redirect(url_for("index"))

@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        flash("Akses ditolak.", "warning"); return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html", barang=get_barang(),
                           default_img=DEFAULT_IMG, qris_url=get_qris())

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
        b64 = "data:" + mime + ";base64," + base64.b64encode(data).decode()
        STORE["qris_url"] = b64
        flash("✅ QRIS berhasil diupload dari file!", "success")
    elif qris_url:
        STORE["qris_url"] = qris_url
        flash("✅ QRIS berhasil disimpan dari URL!", "success")
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
        if harga < 0:
            flash("Harga tidak boleh negatif!", "error"); return redirect(url_for("admin_dashboard"))
    except ValueError:
        flash("Harga harus berupa angka!", "error"); return redirect(url_for("admin_dashboard"))
    if not nama:
        flash("Nama barang tidak boleh kosong!", "error"); return redirect(url_for("admin_dashboard"))
    STORE["barang"].append({"id": get_next_id(), "nama": nama, "harga": harga, "gambar": gambar})
    flash("✅ '" + nama + "' berhasil ditambahkan!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:item_id>", methods=["GET", "POST"])
def admin_edit(item_id):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    item = next((b for b in STORE["barang"] if b["id"] == item_id), None)
    if not item:
        flash("Barang tidak ditemukan.", "error"); return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
        gambar = request.form.get("gambar", "").strip()
        try:
            harga = int(request.form.get("harga", 0))
            if harga < 0:
                flash("Harga tidak boleh negatif!", "error")
                return redirect(url_for("admin_edit", item_id=item_id))
        except ValueError:
            flash("Harga harus berupa angka!", "error")
            return redirect(url_for("admin_edit", item_id=item_id))
        if not nama:
            flash("Nama tidak boleh kosong!", "error")
            return redirect(url_for("admin_edit", item_id=item_id))
        item["nama"] = nama; item["harga"] = harga; item["gambar"] = gambar
        flash("✅ Barang berhasil diperbarui!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", item=item, default_img=DEFAULT_IMG)

@app.route("/admin/hapus/<int:item_id>")
def admin_hapus(item_id):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    awal = len(STORE["barang"])
    STORE["barang"] = [b for b in STORE["barang"] if b["id"] != item_id]
    flash("🗑️ Barang berhasil dihapus." if len(STORE["barang"]) < awal else "Barang tidak ditemukan.",
          "success" if len(STORE["barang"]) < awal else "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=False)

