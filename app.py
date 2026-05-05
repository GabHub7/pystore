from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = 'kunci_rahasia_pystore_123'  # Ganti kalau mau

# ==========================================
# 1. FUNGSI HELPER (BACA & SIMPAN DATA.JSON)
# ==========================================
def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)

# ==========================================
# 2. ROUTE UTAMA & LOGIN
# ==========================================
@app.route('/')
def index():
    data = load_data()
    produk = data.get('produk', [])
    # Cek apakah user sudah login
    pembeli = session.get('pembeli', 'Tamu')
    return render_template('index.html', produk=produk, pembeli=pembeli)

@app.route('/login', methods=['GET', 'POST'])
def login_pembeli():
    if request.method == 'POST':
        nama = request.form.get('nama')
        if nama:
            session['pembeli'] = nama
            return redirect(url_for('index'))
    return render_template('login_pembeli.html')

# ==========================================
# 3. SISTEM KERANJANG BELANJA
# ==========================================
@app.route('/tambah-keranjang', methods=['POST'])
def tambah_keranjang():
    produk_id = request.form.get('produk_id')
    nama_produk = request.form.get('nama_produk')
    harga = int(request.form.get('harga', 0))
    qty = int(request.form.get('qty', 1))
    gambar = request.form.get('gambar', '')

    if 'keranjang' not in session:
        session['keranjang'] = []

    keranjang = session['keranjang']
    ada = False

    # Cek apakah produk sudah ada
    for item in keranjang:
        if item['produk_id'] == produk_id:
            item['qty'] += qty
            ada = True
            break

    # Jika belum ada, tambah baru
    if not ada:
        keranjang.append({
            'produk_id': produk_id,
            'nama_produk': nama_produk,
            'harga': harga,
            'qty': qty,
            'gambar': gambar
        })

    session['keranjang'] = keranjang
    return redirect(request.referrer or url_for('index'))

@app.route('/keranjang')
def keranjang():
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    return render_template('keranjang.html', keranjang=keranjang, total=total)

@app.route('/hapus-keranjang/<produk_id>')
def hapus_keranjang(produk_id):
    if 'keranjang' in session:
        session['keranjang'] = [item for item in session['keranjang'] if item['produk_id'] != produk_id]
    return redirect(url_for('keranjang'))

@app.route('/kosongkan-keranjang')
def kosongkan_keranjang():
    if 'keranjang' in session:
        session.pop('keranjang', None)
    return redirect(url_for('keranjang'))

# ==========================================
# 4. SISTEM PEMBAYARAN (3 METODE)
# ==========================================
@app.route('/bayar')
def bayar():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    return render_template('bayar.html', pembeli=session['pembeli'], total=total)

@app.route('/bayar-qris')
def bayar_qris():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = load_data()
    qris_url = data.get('qris_image', '/static/images/qris-default.jpg')
    
    session['current_order_id'] = order_id
    session['current_total'] = total
    
    return render_template('bayar_qris.html', pembeli=session['pembeli'], total=total, order_id=order_id, qris_url=qris_url)

@app.route('/bayar-transfer')
def bayar_transfer():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = load_data()
    rekening = data.get('rekening_bank', [])
    
    session['current_order_id'] = order_id
    session['current_total'] = total
    
    return render_template('bayar_transfer.html', pembeli=session['pembeli'], total=total, order_id=order_id, rekening=rekening)

@app.route('/bayar-cod')
def bayar_cod():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    session['current_order_id'] = order_id
    session['current_total'] = total
    
    return render_template('cod.html', pembeli=session['pembeli'], total=total, order_id=order_id)

# ==========================================
# 5. KONFIRMASI PEMBAYARAN
# ==========================================
@app.route('/konfirmasi-qris', methods=['POST'])
def konfirmasi_qris():
    order_id = request.form.get('order_id')
    total = request.form.get('total')
    data = load_data()
    if 'pesanan' not in data: data['pesanan'] = []
    
    pesanan_baru = {
        'order_id': order_id,
        'pembeli': session['pembeli'],
        'total': int(total),
        'metode': 'QRIS',
        'status': 'Menunggu Verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

@app.route('/konfirmasi-transfer', methods=['POST'])
def konfirmasi_transfer():
    order_id = request.form.get('order_id')
    total = request.form.get('total')
    bank = request.form.get('bank_pengirim')
    data = load_data()
    if 'pesanan' not in data: data['pesanan'] = []
    
    pesanan_baru = {
        'order_id': order_id,
        'pembeli': session['pembeli'],
        'total': int(total),
        'metode': 'Transfer Bank',
        'bank_pengirim': bank,
        'status': 'Menunggu Verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

@app.route('/konfirmasi-cod', methods=['POST'])
def konfirmasi_cod():
    order_id = request.form.get('order_id')
    total = request.form.get('total')
    data = load_data()
    if 'pesanan' not in data: data['pesanan'] = []
    
    pesanan_baru = {
        'order_id': order_id,
        'pembeli': session['pembeli'],
        'total': int(total),
        'metode': 'COD',
        'status': 'Menunggu Konfirmasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

@app.route('/struk')
def struk():
    # Ambil data terakhir dari session
    order_id = session.get('last_order_id', 'ORD-UNKNOWN')
    metode = session.get('last_payment_method', 'Unknown')
    return render_template('struk.html', order_id=order_id, metode=metode)

# ==========================================
# 6. PANEL ADMIN
# ==========================================
@app.route('/admin')
def admin_dashboard():
    data = load_data()
    return render_template('admin_dashboard.html', data=data)

@app.route('/admin/upload-qris', methods=['POST'])
def upload_qris():
    file = request.files.get('qris_image')
    if file:
        os.makedirs('static/uploads', exist_ok=True)
        filepath = 'static/uploads/qris_merchant.jpg'
        file.save(filepath)
        
        data = load_data()
        data['qris_image'] = '/static/uploads/qris_merchant.jpg'
        save_data(data)
        flash('QRIS Berhasil Diupload!', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tambah-rekening', methods=['POST'])
def tambah_rekening():
    data = load_data()
    if 'rekening_bank' not in data: data['rekening_bank'] = []
    
    data['rekening_bank'].append({
        'nama_bank': request.form.get('nama_bank'),
        'nomor_rekening': request.form.get('nomor_rekening'),
        'atas_nama': request.form.get('atas_nama')
    })
    save_data(data)
    flash('Rekening Berhasil Ditambahkan!', 'success')
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
