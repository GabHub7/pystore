import os
import json
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

MIDTRANS_SERVER_KEY = os.environ.get("MIDTRANS_SERVER_KEY", "Mid-server-uwVe-TFTn0XJrZSg0sjriPiV")
MIDTRANS_CLIENT_KEY = os.environ.get("MIDTRANS_CLIENT_KEY", "Mid-client-R-das4Yrdavuv3Ld")
MIDTRANS_IS_PRODUCTION = False
MIDTRANS_SNAP_URL = "https://app.midtrans.com/snap/snap.js"
MIDTRANS_API_URL = "https://app.midtrans.com/snap/v1/transactions"

STORE = {
    "barang": [
        {"id": 1, "nama": "Indomie Goreng", "harga": 3000, "gambar": ""},
        {"id": 2, "nama": "Air Mineral", "harga": 2000, "gambar": ""},
        {"id": 3, "nama": "Roti Tawar", "harga": 7000, "gambar": ""},
        {"id": 4, "nama": "Telur (1 butir)", "harga": 1500, "gambar": ""},
        {"id": 5, "nama": "Susu UHT", "harga": 5000, "gambar": ""},
    ],
    "next_id": 6
}

def get_barang():
    return STORE["barang"]

def get_next_id():
    nid = STORE["next_id"]
    STORE["next_id"] += 1
    return nid

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

@app.route("/keranjang")
def keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    return render_template("keranjang.html",
                           keranjang=session.get("keranjang", []),
                           pembeli=session["pembeli_nama"],
                           default_img=DEFAULT_IMG)

@app.route("/tambah-keranjang", methods=["POST"])
def tambah_keranjang():
    if not session.get("pembeli_nama"):
        flash("Silakan masuk sebagai pembeli terlebih dahulu.", "warning")
        return redirect(url_for("login_pembeli"))
    try:
        id_beli = int(request.form.get("id_barang"))
        qty = int(request.form.get("qty", 1))
        if qty <= 0:
            flash("Jumlah minimal 1.", "error")
            return redirect(url_for("index"))
    except (ValueError, TypeError):
        flash("Input tidak valid.", "error")
        return redirect(url_for("index"))

    item = next((b for b in get_barang() if b["id"] == id_beli), None)
    if not item:
        flash("Barang tidak ditemukan.", "error")
        return redirect(url_for("index"))

    keranjang = session.get("keranjang", [])
    existing = next((k for k in keranjang if k["id"] == id_beli), None)
    if existing:
        existing["jumlah"] += qty
        existing["subtotal"] = existing["harga"] * existing["jumlah"]
    else:
        keranjang.append({
            "id": item["id"],
            "nama": item["nama"],
            "harga": item["harga"],
            "gambar": item.get("gambar", ""),
            "jumlah": qty,
            "subtotal": item["harga"] * qty
        })
    session["keranjang"] = keranjang
    flash("✅ " + item["nama"] + " x" + str(qty) + " ditambahkan ke keranjang.", "success")
    return redirect(url_for("index"))

@app.route("/hapus-keranjang/<int:item_id>")
def hapus_keranjang(item_id):
    keranjang = session.get("keranjang", [])
    session["keranjang"] = [k for k in keranjang if k["id"] != item_id]
    flash("Item dihapus dari keranjang.", "info")
    return redirect(url_for("keranjang"))

@app.route("/bayar", methods=["POST"])
def bayar():
    if not session.get("pembeli_nama"):
        return redirect(url_for("login_pembeli"))
    keranjang = session.get("keranjang", [])
    if not keranjang:
        flash("Keranjang kosong!", "error")
        return redirect(url_for("keranjang"))

    total = sum(k["subtotal"] for k in keranjang)
    order_id = "PYSTORE-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + session["pembeli_nama"].replace(" ", "")[:8]

    session["order_id"] = order_id
    session["order_total"] = total
    session["keranjang_backup"] = list(keranjang)

    item_details = []
    for k in keranjang:
        item_details.append({
            "id": str(k["id"]),
            "price": k["harga"],
            "quantity": k["jumlah"],
            "name": k["nama"][:50]
        })

    payload = {
        "transaction_details": {
            "order_id": order_id,
            "gross_amount": total
        },
        "item_details": item_details,
        "customer_details": {
            "first_name": session["pembeli_nama"]
        },
        "callbacks": {
            "finish": url_for("struk_page", _external=True),
            "error": url_for("keranjang", _external=True),
            "pending": url_for("struk_page", _external=True)
        }
    }

    try:
        auth = base64.b64encode((MIDTRANS_SERVER_KEY + ":").encode()).decode()
        resp = requests.post(
            MIDTRANS_API_URL,
            json=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Basic " + auth
            },
            timeout=15
        )
        result = resp.json()
        if "token" in result:
            session["keranjang"] = []
            return render_template("bayar.html",
                                   snap_token=result["token"],
                                   client_key=MIDTRANS_CLIENT_KEY,
                                   snap_url=MIDTRANS_SNAP_URL,
                                   total=total,
                                   pembeli=session["pembeli_nama"])
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
    struk = {
        "pelanggan": session.get("pembeli_nama", "Tamu"),
        "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "produk": keranjang,
        "total": total,
        "bayar": total,
        "kembalian": 0,
        "order_id": session.get("order_id", "-"),
        "payment_type": data.get("payment_type", "-"),
        "transaction_status": data.get("transaction_status", "-")
    }
    session["struk"] = struk
    session.pop("keranjang_backup", None)
    return jsonify({"status": "ok"})

@app.route("/struk")
def struk_page():
    struk = session.get("struk")
    if not struk:
        return redirect(url_for("index"))
    return render_template("struk.html", struk=struk, pembeli=session.get("pembeli_nama"))

@app.route("/notifikasi-midtrans", methods=["POST"])
def notifikasi_midtrans():
    data = request.get_json()
    if not data:
        return jsonify({"status": "ignored"}), 200
    order_id = data.get("order_id", "")
    signature_raw = order_id + data.get("status_code", "") + data.get("gross_amount", "") + MIDTRANS_SERVER_KEY
    signature = hashlib.sha512(signature_raw.encode()).hexdigest()
    if signature != data.get("signature_key", ""):
        return jsonify({"status": "invalid signature"}), 403
    return jsonify({"status": "ok"}), 200

@app.route("/admin", methods=["GET", "POST"])
def admin_login():
    if session.get("admin_logged_in"):
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        pwd = request.form.get("password", "")
        if pwd == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            flash("Login admin berhasil! ✅", "success")
            return redirect(url_for("admin_dashboard"))
        else:
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
        flash("Akses ditolak. Silakan login sebagai admin.", "warning")
        return redirect(url_for("admin_login"))
    return render_template("admin_dashboard.html", barang=get_barang(), default_img=DEFAULT_IMG)

@app.route("/admin/tambah", methods=["POST"])
def admin_tambah():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    nama = request.form.get("nama", "").strip()
    gambar = request.form.get("gambar", "").strip()
    try:
        harga = int(request.form.get("harga", 0))
        if harga < 0:
            flash("Harga tidak boleh negatif!", "error")
            return redirect(url_for("admin_dashboard"))
    except ValueError:
        flash("Harga harus berupa angka!", "error")
        return redirect(url_for("admin_dashboard"))
    if not nama:
        flash("Nama barang tidak boleh kosong!", "error")
        return redirect(url_for("admin_dashboard"))
    nid = get_next_id()
    STORE["barang"].append({"id": nid, "nama": nama, "harga": harga, "gambar": gambar})
    flash("✅ '" + nama + "' berhasil ditambahkan!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:item_id>", methods=["GET", "POST"])
def admin_edit(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    item = next((b for b in STORE["barang"] if b["id"] == item_id), None)
    if not item:
        flash("Barang tidak ditemukan.", "error")
        return redirect(url_for("admin_dashboard"))
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
        item["nama"] = nama
        item["harga"] = harga
        item["gambar"] = gambar
        flash("✅ Barang berhasil diperbarui!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", item=item, default_img=DEFAULT_IMG)

@app.route("/admin/hapus/<int:item_id>")
def admin_hapus(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    awal = len(STORE["barang"])
    STORE["barang"] = [b for b in STORE["barang"] if b["id"] != item_id]
    if len(STORE["barang"]) < awal:
        flash("🗑️ Barang berhasil dihapus.", "success")
    else:
        flash("Barang tidak ditemukan.", "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=False)
