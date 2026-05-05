from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os
import json

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Ganti dengan secret key Anda

# Helper function untuk load data
def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        return {}

# Helper function untuk save data
def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)

# Route halaman pilih metode pembayaran
@app.route('/bayar', methods=['GET'])
def halaman_bayar():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    # Hitung total dari keranjang
    keranjang = session.get('keranjang', [])
    total = sum(item.get('harga', 0) * item.get('qty', 1) for item in keranjang)
    
    return render_template('bayar.html', 
                         pembeli=session['pembeli'],
                         total=total)

# Route pembayaran QRIS
@app.route('/bayar-qris', methods=['GET'])
def bayar_qris():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item.get('harga', 0) * item.get('qty', 1) for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Ambil gambar QRIS dari data.json atau config admin
    data = load_data()
    qris_url = data.get('qris_image', '/static/images/qris-default.jpg')
    
    # Simpan order_id sementara di session
    session['current_order_id'] = order_id
    session['current_total'] = total
    
    return render_template('bayar_qris.html',
                         pembeli=session['pembeli'],
                         total=total,
                         order_id=order_id,
                         qris_url=qris_url)

# Route pembayaran Transfer Bank
@app.route('/bayar-transfer', methods=['GET'])
def bayar_transfer():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item.get('harga', 0) * item.get('qty', 1) for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Ambil data rekening bank dari data.json
    data = load_data()
    rekening = data.get('rekening_bank', [])
    
    # Simpan order_id sementara di session
    session['current_order_id'] = order_id
    session['current_total'] = total
    
    return render_template('bayar_transfer.html',
                         pembeli=session['pembeli'],
                         total=total,
                         order_id=order_id,
                         rekening=rekening)

# Route pembayaran COD
@app.route('/bayar-cod', methods=['GET'])
def bayar_cod():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    keranjang = session.get('keranjang', [])
    total = sum(item.get('harga', 0) * item.get('qty', 1) for item in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    # Simpan order_id sementara di session
    session['current_order_id'] = order_id
    session['current_total'] = total
    
    return render_template('cod.html',
                         pembeli=session['pembeli'],
                         total=total,
                         order_id=order_id)

# Konfirmasi pembayaran QRIS
@app.route('/konfirmasi-qris', methods=['POST'])
def konfirmasi_qris():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    order_id = request.form.get('order_id')
    total = request.form.get('total')
    
    # Load data
    data = load_data()
    
    # Buat pesanan baru
    pesanan_baru = {
        'order_id': order_id,
        'pembeli': session['pembeli'],
        'total': int(total),
        'metode_pembayaran': 'qris',
        'status': 'menunggu_verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    # Simpan ke data.json
    if 'pesanan' not in data:
        data['pesanan'] = []
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    
    # Clear keranjang
    session.pop('keranjang', None)
    session.pop('current_order_id', None)
    session.pop('current_total', None)
    
    # Simpan info untuk halaman struk
    session['last_order_id'] = order_id
    session['last_payment_method'] = 'QRIS'
    
    return redirect(url_for('struk'))

# Konfirmasi pembayaran Transfer
@app.route('/konfirmasi-transfer', methods=['POST'])
def konfirmasi_transfer():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    order_id = request.form.get('order_id')
    total = request.form.get('total')
    bank_pengirim = request.form.get('bank_pengirim')
    
    # Handle upload bukti transfer
    bukti_transfer = request.files.get('bukti_transfer')
    bukti_path = None
    if bukti_transfer and bukti_transfer.filename:
        upload_folder = 'static/uploads/bukti_transfer'
        os.makedirs(upload_folder, exist_ok=True)
        filename = f"{order_id}_{bukti_transfer.filename}"
        bukti_path = os.path.join(upload_folder, filename)
        bukti_transfer.save(bukti_path)
    
    # Load data
    data = load_data()
    
    # Buat pesanan baru
    pesanan_baru = {
        'order_id': order_id,
        'pembeli': session['pembeli'],
        'total': int(total),
        'metode_pembayaran': 'transfer',
        'bank_pengirim': bank_pengirim,
        'bukti_transfer': bukti_path,
        'status': 'menunggu_verifikasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    # Simpan ke data.json
    if 'pesanan' not in data:
        data['pesanan'] = []
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    
    # Clear keranjang
    session.pop('keranjang', None)
    session.pop('current_order_id', None)
    session.pop('current_total', None)
    
    # Simpan info untuk halaman struk
    session['last_order_id'] = order_id
    session['last_payment_method'] = 'Transfer Bank'
    
    return redirect(url_for('struk'))

# Konfirmasi pembayaran COD
@app.route('/konfirmasi-cod', methods=['POST'])
def konfirmasi_cod():
    if 'pembeli' not in session:
        return redirect(url_for('login_pembeli'))
    
    order_id = request.form.get('order_id')
    total = request.form.get('total')
    
    # Load data
    data = load_data()
    
    # Buat pesanan baru
    pesanan_baru = {
        'order_id': order_id,
        'pembeli': session['pembeli'],
        'total': int(total),
        'metode_pembayaran': 'cod',
        'status': 'menunggu_konfirmasi',
        'tanggal': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items': session.get('keranjang', [])
    }
    
    # Simpan ke data.json
    if 'pesanan' not in data:
        data['pesanan'] = []
    data['pesanan'].append(pesanan_baru)
    save_data(data)
    
    # Clear keranjang
    session.pop('keranjang', None)
    session.pop('current_order_id', None)
    session.pop('current_total', None)
    
    # Simpan info untuk halaman struk
    session['last_order_id'] = order_id
    session['last_payment_method'] = 'COD'
    
    return redirect(url_for('struk'))

# Admin upload QRIS
@app.route('/admin/upload-qris', methods=['GET', 'POST'])
def admin_upload_qris():
    if request.method == 'POST':
        qris_file = request.files.get('qris_image')
        if qris_file:
            # Simpan file
            upload_folder = 'static/uploads/qris'
            os.makedirs(upload_folder, exist_ok=True)
            filename = 'qris_merchant.jpg'
            filepath = os.path.join(upload_folder, filename)
            qris_file.save(filepath)
            
            # Update data.json
            data = load_data()
            data['qris_image'] = '/' + filepath
            save_data(data)
            
            flash('QRIS berhasil diupload!', 'success')
            return redirect(url_for('admin_dashboard'))
    
    return render_template('admin_dashboard.html')

# Admin update rekening bank
@app.route('/admin/update-rekening', methods=['POST'])
def admin_update_rekening():
    nama_bank = request.form.get('nama_bank')
    nomor_rekening = request.form.get('nomor_rekening')
    atas_nama = request.form.get('atas_nama')
    
    # Load data
    data = load_data()
    
    # Tambah rekening baru
    if 'rekening_bank' not in data:
        data['rekening_bank'] = []
    
    data['rekening_bank'].append({
        'nama_bank': nama_bank,
        'nomor_rekening': nomor_rekening,
        'atas_nama': atas_nama
    })
    
    save_data(data)
    flash('Rekening bank berhasil ditambahkan!', 'success')
    
    return redirect(url_for('admin_dashboard'))

if __name__ == '__main__':
    app.run(debug=True)
