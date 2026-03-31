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
QRIS_IMAGE_URL = os.environ.get("QRIS_IMAGE_URL", "")

STORE = {
    "barang": [
        {"id": 1, "nama": "Indomie Goreng",  "harga": 3000, "gambar": "", "stok": 100},
        {"id": 2, "nama": "Air Mineral",     "harga": 2000, "gambar": "", "stok": 100},
        {"id": 3, "nama": "Roti Tawar",      "harga": 7000, "gambar": "", "stok": 100},
        {"id": 4, "nama": "Telur (1 butir)", "harga": 1500, "gambar": "", "stok": 100},
        {"id": 5, "nama": "Susu UHT",        "harga": 5000, "gambar": "", "stok": 100},
    ],
    "next_id": 6, "orders": [], "qris_url": ""
}

def get_barang(): return STORE["barang"]
def get_next_id():
    nid = STORE["next_id"]; STORE["next_id"] += 1; return nid
def add_order(o): STORE["orders"].append(o)
def get_orders(): return STORE["orders"]
def get_qris(): return STORE.get("qris_url") or QRIS_IMAGE_URL
def item_by_id(iid): return next((b for b in STORE["barang"] if b["id"] == iid), None)

def safe_gambar(gambar, item_id):
    """Jangan simpan base64 di session, tandai dengan marker saja."""
    if gambar and gambar.startswith("data:"):
        return "__b64__" + str(item_id)
    return gambar

def restore_gambar(keranjang):
    """Pulihkan gambar base64 dari STORE saat ditampilkan."""
    result = []
    for k in keranjang:
        item = dict(k)
        if item.get("gambar", "").startswith("__b64__"):
            b = item_by_id(item["id"])
            item["gambar"] = b.get("gambar", "") if b else ""
        result.append(item)
    return result

def produk_for_order(keranjang):
    """Versi produk tanpa gambar untuk disimpan di order."""
    return [{"id": k["id"], "nama": k["nama"], "harga": k["harga"],
             "jumlah": k["jumlah"], "subtotal": k["subtotal"]} for k in keranjang]

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
    flash("Berhasil keluar.", "info")
    return redirect(url_for("index"))

# ===================== KERANJANG =====================

@app.route("/keranjang")
def keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    restored = restore_gambar(session.get("keranjang", []))
    return render_template("keranjang.html", keranjang=restored,
                           pembeli=session["pembeli_nama"], default_img=DEFAULT_IMG,
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

    b = item_by_id(id_beli)
    if not b:
        flash("Barang tidak ditemukan.", "error"); return redirect(url_for("index"))

    stok = b.get("stok", 0)
    keranjang = session.get("keranjang", [])
    existing = next((k for k in keranjang if k["id"] == id_beli), None)
    sudah_di_keranjang = existing["jumlah"] if existing else 0

    if stok < sudah_di_keranjang + qty:
        flash("Stok tidak mencukupi! Sisa stok: " + str(stok - sudah_di_keranjang), "error")
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
        order_id = "COD-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
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
        return redirect(url_for("struk_page"))
    total = sum(k["subtotal"] for k in keranjang)
    return render_template("cod.html", keranjang=keranjang, total=total, pembeli=session["pembeli_nama"])

# ===================== QRIS =====================

@app.route("/bayar-qris")
def bayar_qris():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    qris = get_qris()
    if not qris:
        flash("QRIS belum tersedia.", "warning"); return redirect(url_for("keranjang"))
    keranjang = restore_gambar(raw)
    total = sum(k["subtotal"] for k in keranjang)
    order_id = "QRIS-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
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
    order_id = session.get("order_id", "QRIS-" + datetime.now().strftime("%Y%m%d%H%M%S"))
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
    return redirect(url_for("struk_page"))

# ===================== MIDTRANS =====================

@app.route("/bayar", methods=["GET", "POST"])
def bayar():
    if not session.get("pembeli_nama"): return redirect(url_for("login_pembeli"))
    raw = session.get("keranjang", [])
    if not raw:
        flash("Keranjang kosong!", "error"); return redirect(url_for("keranjang"))
    keranjang = restore_gambar(raw)
    total = sum(k["subtotal"] for k in keranjang)
    order_id = "PYSTORE-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]
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
            for k in keranjang:
                b = item_by_id(k["id"])
                if b: b["stok"] = max(0, b.get("stok", 0) - k["jumlah"])
            session["keranjang"] = []
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
    data = request.get_json() or {}
    struk = {
        "pelanggan": session.get("pembeli_nama", "Tamu"),
        "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "produk": [], "total": session.get("order_total", 0),
        "bayar": session.get("order_total", 0), "kembalian": 0,
        "order_id": session.get("order_id", "-"),
        "metode": "Midtrans - " + data.get("payment_type", "-"),
        "status": data.get("transaction_status", "settlement")
    }
    session["struk"] = struk
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
    oid = data.get("order_id", "")
    sig = hashlib.sha512((oid + data.get("status_code", "") +
                          data.get("gross_amount", "") + MIDTRANS_SERVER_KEY).encode()).hexdigest()
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
        STORE["qris_url"] = "data:" + mime + ";base64," + base64.b64encode(data).decode()
        flash("✅ QRIS berhasil diupload!", "success")
    elif qris_url:
        STORE["qris_url"] = qris_url
        flash("✅ QRIS disimpan!", "success")
    else:
        flash("Masukkan URL atau upload file!", "error")
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
    flash("✅ '" + nama + "' ditambahkan!", "success")
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
        item["nama"] = nama; item["harga"] = harga; item["stok"] = stok
        if gambar: item["gambar"] = gambar
        flash("✅ Berhasil diperbarui!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", item=item, default_img=DEFAULT_IMG)

@app.route("/admin/hapus/<int:item_id>")
def admin_hapus(item_id):
    if not session.get("admin_logged_in"): return redirect(url_for("admin_login"))
    awal = len(STORE["barang"])
    STORE["barang"] = [b for b in STORE["barang"] if b["id"] != item_id]
    flash("🗑️ Dihapus." if len(STORE["barang"]) < awal else "Tidak ditemukan.",
          "success" if len(STORE["barang"]) < awal else "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=False)

