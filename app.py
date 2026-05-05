from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = 'rahasia123'

# Fungsi baca data dari JSON
def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        return {}

# Fungsi simpan data ke JSON
def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)

# Halaman Utama
@app.route('/')
def index():
    data = load_data()
    produk = data.get('produk', [])
    return render_template('index.html', produk=produk)

# Login Pembeli
@app.route('/login', methods=['GET', 'POST'])
def login_pembeli():
    if request.method == 'POST':
        nama = request.form.get('nama')
        session['pembeli'] = nama
        return redirect(url_for('index'))
    return render_template('login_pembeli.html')

# Tambah ke Keranjang
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
    
    for item in keranjang:
        if item['produk_id'] == produk_id:
            item['qty'] += qty
            ada = True
            break
    
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

# Lihat Keranjang
@app.route('/keranjang')
def keranjang():
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    return render_template('keranjang.html', keranjang=keranjang, total=total)

# Halaman Bayar (Pilih Metode)
@app.route('/bayar')
def bayar():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    return render_template('bayar.html', pembeli=session['pembeli'], total=total)

# Bayar QRIS
@app.route('/bayar-qris')
def bayar_qris():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = load_data()
    qris_url = data.get('qris_image', '/static/images/qris.jpg')
    
    session['order_id'] = order_id
    session['total_bayar'] = total
    
    return render_template('bayar_qris.html', pembeli=session['pembeli'], total=total, order_id=order_id, qris_url=qris_url)

# Bayar Transfer
@app.route('/bayar-transfer')
def bayar_transfer():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = load_data()
    rekening = data.get('rekening', [])
    
    session['order_id'] = order_id
    session['total_bayar'] = total
    
    return render_template('bayar_transfer.html', pembeli=session['pembeli'], total=total, order_id=order_id, rekening=rekening)

# Bayar COD
@app.route('/bayar-cod')
def bayar_cod():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    session['order_id'] = order_id
    session['total_bayar'] = total
    
    return render_template('cod.html', pembeli=session['pembeli'], total=total, order_id=order_id)

# Konfirmasi QRIS
@app.route('/konfirmasi-qris', methods=['POST'])
def konfirmasi_qris():
    data = load_data()
    if 'pesanan' not in data:
        data['pesanan'] = []
    
    pesanan_baru = {
        'order_id': session.get('order_id'),
        'pembeli': session.get('pembeli'),
        'total': session.get('total_bayar', 0),
        'metode': 'QRIS',
        'status': 'Menunggu Verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

# Konfirmasi Transfer
@app.route('/konfirmasi-transfer', methods=['POST'])
def konfirmasi_transfer():
    data = load_data()
    if 'pesanan' not in data:
        data['pesanan'] = []
    
    pesanan_baru = {
        'order_id': session.get('order_id'),
        'pembeli': session.get('pembeli'),
        'total': session.get('total_bayar', 0),
        'metode': 'Transfer Bank',
        'status': 'Menunggu Verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

# Konfirmasi COD
@app.route('/konfirmasi-cod', methods=['POST'])
def konfirmasi_cod():
    data = load_data()
    if 'pesanan' not in data:
        data['pesanan'] = []
    
    pesanan_baru = {
        'order_id': session.get('order_id'),
        'pembeli': session.get('pembeli'),
        'total': session.get('total_bayar', 0),
        'metode': 'COD',
        'status': 'Menunggu Konfirmasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

# Struk/Nota
@app.route('/struk')
def struk():
    return render_template('struk.html')

# Admin Dashboard
@app.route('/admin')
def admin_dashboard():
    data = load_data()
    return render_template('admin_dashboard.html', data=data)

# Admin Login
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == 'admin' and password == 'admin123':
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
    return render_template('admin_login.html')

# Tambah Produk (Admin)
@app.route('/admin/tambah-produk', methods=['POST'])
def tambah_produk():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    data = load_data()
    if 'produk' not in data:
        data['produk'] = []
    
    produk_baru = {
        'id': str(len(data['produk']) + 1),
        'nama': request.form.get('nama'),
        'harga': int(request.form.get('harga')),
        'gambar': request.form.get('gambar', '')
    }
    
    data['produk'].append(produk_baru)
    save_data(data)
    return redirect(url_for('admin_dashboard'))

# Upload QRIS (Admin)
@app.route('/admin/upload-qris', methods=['POST'])
def upload_qris():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    file = request.files.get('qris_image')
    if file:
        os.makedirs('static/uploads', exist_ok=True)
        file.save('static/uploads/qris.jpg')
        
        data = load_data()
        data['qris_image'] = '/static/uploads/qris.jpg'
        save_data(data)
    
    return redirect(url_for('admin_dashboard'))

# Tambah Rekening (Admin)
@app.route('/admin/tambah-rekening', methods=['POST'])
def tambah_rekening():
    if not session.get('admin'):
        return redirect(url_for('admin_login'))
    
    data = load_data()
    if 'rekening' not in data:
        data['rekening'] = []
    
    rekening_baru = {
        'bank': request.form.get('bank'),
        'nomor': request.form.get('nomor'),
        'atas_nama': request.form.get('atas_nama')
    }
    
    data['rekening'].append(rekening_baru)
    save_data(data)
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
