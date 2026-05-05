from flask import Flask, render_template, request, redirect, url_for, session
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = 'rahasia123'

# Load & Save Data
def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)

# ===== ROUTE UTAMA =====
@app.route('/')
def index():
    data = load_data()
    return render_template('index.html', produk=data.get('produk', []))

@app.route('/login', methods=['GET', 'POST'])
def login_pembeli():
    if request.method == 'POST':
        session['pembeli'] = request.form.get('nama')
        return redirect(url_for('index'))
    return render_template('login_pembeli.html')

# ===== KERANJANG =====
@app.route('/tambah-keranjang', methods=['POST'])
def tambah_keranjang():
    if 'keranjang' not in session:
        session['keranjang'] = []
    
    produk_id = request.form.get('produk_id')
    keranjang = session['keranjang']
    
    # Cek apakah sudah ada
    for item in keranjang:
        if item['produk_id'] == produk_id:
            item['qty'] += int(request.form.get('qty', 1))
            session['keranjang'] = keranjang
            return redirect(request.referrer)
    
    # Tambah baru    keranjang.append({
        'produk_id': produk_id,
        'nama_produk': request.form.get('nama_produk'),
        'harga': int(request.form.get('harga', 0)),
        'qty': int(request.form.get('qty', 1)),
        'gambar': request.form.get('gambar', '')
    })
    
    session['keranjang'] = keranjang
    return redirect(request.referrer)

@app.route('/keranjang')
def keranjang():
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    return render_template('keranjang.html', keranjang=keranjang, total=total)

@app.route('/hapus-keranjang/<produk_id>')
def hapus_keranjang(produk_id):
    if 'keranjang' in session:
        session['keranjang'] = [i for i in session['keranjang'] if i['produk_id'] != produk_id]
    return redirect(url_for('keranjang'))

# ===== PEMBAYARAN =====
@app.route('/bayar')
def bayar():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    return render_template('bayar.html', pembeli=session['pembeli'], total=total)

# Route QRIS
@app.route('/bayar-qris')
def bayar_qris():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = load_data()
    qris_url = data.get('qris_image', '/static/images/qris.jpg')
    
    session['order_id'] = order_id
    session['total_bayar'] = total
    
    return render_template('bayar_qris.html',                          pembeli=session['pembeli'], 
                         total=total, 
                         order_id=order_id, 
                         qris_url=qris_url)

# Route Transfer Bank
@app.route('/bayar-transfer')
def bayar_transfer():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    data = load_data()
    rekening = data.get('rekening_bank', [])
    
    session['order_id'] = order_id
    session['total_bayar'] = total
    
    return render_template('bayar_transfer.html', 
                         pembeli=session['pembeli'], 
                         total=total, 
                         order_id=order_id, 
                         rekening=rekening)

# Route COD
@app.route('/bayar-cod')
def bayar_cod():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item['harga'] * item['qty'] for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    session['order_id'] = order_id
    session['total_bayar'] = total
    
    return render_template('cod.html', 
                         pembeli=session['pembeli'], 
                         total=total, 
                         order_id=order_id)

# ===== KONFIRMASI PEMBAYARAN =====
@app.route('/konfirmasi-qris', methods=['POST'])
def konfirmasi_qris():
    data = load_data()
    if 'pesanan' not in data:        data['pesanan'] = []
    
    data['pesanan'].append({
        'order_id': session.get('order_id'),
        'pembeli': session.get('pembeli'),
        'total': session.get('total_bayar', 0),
        'metode': 'QRIS',
        'status': 'Menunggu Verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    })
    
    save_data(data)
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

@app.route('/konfirmasi-transfer', methods=['POST'])
def konfirmasi_transfer():
    data = load_data()
    if 'pesanan' not in data:
        data['pesanan'] = []
    
    data['pesanan'].append({
        'order_id': session.get('order_id'),
        'pembeli': session.get('pembeli'),
        'total': session.get('total_bayar', 0),
        'metode': 'Transfer Bank',
        'bank_pengirim': request.form.get('bank_pengirim'),
        'status': 'Menunggu Verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    })
    
    save_data(data)
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

@app.route('/konfirmasi-cod', methods=['POST'])
def konfirmasi_cod():
    data = load_data()
    if 'pesanan' not in data:
        data['pesanan'] = []
    
    data['pesanan'].append({
        'order_id': session.get('order_id'),
        'pembeli': session.get('pembeli'),
        'total': session.get('total_bayar', 0),
        'metode': 'COD',
        'status': 'Menunggu Konfirmasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),        'items': session.get('keranjang', [])
    })
    
    save_data(data)
    session.pop('keranjang', None)
    return redirect(url_for('struk'))

@app.route('/struk')
def struk():
    return render_template('struk.html', 
                         order_id=session.get('order_id'),
                         metode=session.get('last_method', 'Pembayaran'))

# ===== ADMIN =====
@app.route('/admin')
def admin():
    data = load_data()
    return render_template('admin_dashboard.html', data=data)

@app.route('/admin/upload-qris', methods=['POST'])
def upload_qris():
    file = request.files.get('qris_image')
    if file:
        os.makedirs('static/uploads', exist_ok=True)
        file.save('static/uploads/qris.jpg')
        data = load_data()
        data['qris_image'] = '/static/uploads/qris.jpg'
        save_data(data)
    return redirect(url_for('admin'))

@app.route('/admin/tambah-rekening', methods=['POST'])
def tambah_rekening():
    data = load_data()
    if 'rekening_bank' not in data:
        data['rekening_bank'] = []
    
    data['rekening_bank'].append({
        'bank': request.form.get('bank'),
        'nomor': request.form.get('nomor'),
        'atas_nama': request.form.get('atas_nama')
    })
    
    save_data(data)
    return redirect(url_for('admin'))

if __name__ == '__main__':
    app.run(debug=True)
