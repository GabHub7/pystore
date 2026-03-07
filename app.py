import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import json

app = Flask(__name__, template_folder=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
app.secret_key = "pystore-secret-key-2024"

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
ADMIN_PASSWORD = "admin1234"

# ===================== DATA HELPERS =====================

def load_data():
    if not os.path.exists(DATA_FILE):
        default = {
            "barang": [
                {"id": 1, "nama": "Indomie Goreng", "harga": 3000},
                {"id": 2, "nama": "Air Mineral", "harga": 2000},
                {"id": 3, "nama": "Roti Tawar", "harga": 7000},
                {"id": 4, "nama": "Telur (1 butir)", "harga": 1500},
                {"id": 5, "nama": "Susu UHT", "harga": 5000},
            ],
            "next_id": 6
        }
        save_data(default)
        return default
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# ===================== PUBLIC / BERANDA =====================

@app.route("/")
def index():
    data = load_data()
    logged_in = session.get("pembeli_nama")
    return render_template("index.html", barang=data["barang"], pembeli=logged_in)

# ===================== PEMBELI AUTH =====================

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
                           pembeli=session["pembeli_nama"])

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

    data = load_data()
    item = next((b for b in data["barang"] if b["id"] == id_beli), None)
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
    try:
        uang = int(request.form.get("uang", 0))
    except ValueError:
        flash("Masukkan jumlah uang yang valid.", "error")
        return redirect(url_for("keranjang"))

    total = sum(k["subtotal"] for k in keranjang)
    if uang < total:
        flash("Uang kurang! Kekurangan Rp" + str(total - uang), "error")
        return redirect(url_for("keranjang"))

    kembalian = uang - total
    struk = {
        "pelanggan": session["pembeli_nama"],
        "tanggal": datetime.now().strftime("%d-%m-%Y %H:%M:%S"),
        "items": list(keranjang),
        "total": total,
        "bayar": uang,
        "kembalian": kembalian
    }
    session["struk"] = struk
    session["keranjang"] = []
    return redirect(url_for("struk_page"))

@app.route("/struk")
def struk_page():
    struk = session.get("struk")
    if not struk:
        return redirect(url_for("index"))
    return render_template("struk.html", struk=struk, pembeli=session.get("pembeli_nama"))

# ===================== ADMIN =====================

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
    data = load_data()
    return render_template("admin_dashboard.html", barang=data["barang"])

@app.route("/admin/tambah", methods=["POST"])
def admin_tambah():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    nama = request.form.get("nama", "").strip()
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
    data = load_data()
    data["barang"].append({"id": data["next_id"], "nama": nama, "harga": harga})
    data["next_id"] += 1
    save_data(data)
    flash("✅ '" + nama + "' berhasil ditambahkan!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/edit/<int:item_id>", methods=["GET", "POST"])
def admin_edit(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    data = load_data()
    item = next((b for b in data["barang"] if b["id"] == item_id), None)
    if not item:
        flash("Barang tidak ditemukan.", "error")
        return redirect(url_for("admin_dashboard"))
    if request.method == "POST":
        nama = request.form.get("nama", "").strip()
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
        save_data(data)
        flash("✅ Barang berhasil diperbarui!", "success")
        return redirect(url_for("admin_dashboard"))
    return render_template("admin_edit.html", item=item)

@app.route("/admin/hapus/<int:item_id>")
def admin_hapus(item_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    data = load_data()
    awal = len(data["barang"])
    data["barang"] = [b for b in data["barang"] if b["id"] != item_id]
    if len(data["barang"]) < awal:
        save_data(data)
        flash("🗑️ Barang berhasil dihapus.", "success")
    else:
        flash("Barang tidak ditemukan.", "error")
    return redirect(url_for("admin_dashboard"))

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
