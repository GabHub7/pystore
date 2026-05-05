from flask import Flask, render_template, request, redirect, url_for, session, flash
from datetime import datetime
import os, json, base64

app = Flask(__name__)
app.secret_key = 'rahasia_pystore_2026'

DATA_FILE = os.path.join(os.path.dirname(__file__), 'data.json')

def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

@app.route('/')
def index():
    data    = load_data()
    barang  = data.get('barang', [])
    pembeli = session.get('pembeli_nama')
    return render_template('index.html', barang=barang, pembeli=pembeli)

@app.route('/login-pembeli', methods=['GET', 'POST'])
def login_pembeli():
    if request.method == 'POST':
        nama = request.form.get('nama', '').strip()
        if nama:
            session['pembeli_nama'] = nama
            session['keranjang']    = []
            flash(f'Selamat datang, {nama}! 🎉', 'success')
            return redirect(url_for('index'))
        flash('Nama tidak boleh kosong.', 'error')
    return render_template('login_pembeli.html')

@app.route('/logout-pembeli')
def logout_pembeli():
    session.pop('pembeli_nama', None)
    session.pop('keranjang', None)
    flash('Berhasil keluar.', 'info')
    return redirect(url_for('index'))

@app.route('/tambah-keranjang', methods=['POST'])
def tambah_keranjang():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    data   = load_data()
    barang = data.get('barang', [])
    id_str = request.form.get('id_barang', '')
    qty    = int(request.form.get('qty', 1))
    produk = next((b for b in barang if str(b['id']) == id_str), None)
    if not produk:
        flash('Produk tidak ditemukan.', 'error')
        return redirect(url_for('index'))
    keranjang = session.get('keranjang', [])
    for item in keranjang:
        if str(item['id']) == id_str:
            item['jumlah']  += qty
            item['subtotal'] = item['harga'] * item['jumlah']
            session['keranjang'] = keranjang
            flash(f'Qty {produk["nama"]} diperbarui.', 'success')
            return redirect(request.referrer or url_for('index'))
    keranjang.append({
        'id': produk['id'], 'nama': produk['nama'], 'harga': produk['harga'],
        'gambar': produk.get('gambar',''), 'jumlah': qty,
        'subtotal': produk['harga'] * qty
    })
    session['keranjang'] = keranjang
    flash(f'{produk["nama"]} ditambahkan ke keranjang! 🛒', 'success')
    return redirect(request.referrer or url_for('index'))

@app.route('/keranjang')
def keranjang():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    data = load_data()
    keranjang   = session.get('keranjang', [])
    pembeli     = session.get('pembeli_nama')
    qris_url    = data.get('qris_image', '')
    total       = sum(i['subtotal'] for i in keranjang)
    return render_template('keranjang.html', keranjang=keranjang, pembeli=pembeli,
                           total=total, qris_tersedia=bool(qris_url))

@app.route('/hapus-keranjang/<int:item_id>')
def hapus_keranjang(item_id):
    if 'keranjang' in session:
        session['keranjang'] = [i for i in session['keranjang'] if i['id'] != item_id]
    return redirect(url_for('keranjang'))

@app.route('/pilih-bayar', methods=['POST'])
def pilih_bayar():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    metode = request.form.get('metode', 'cod')
    if metode == 'qris':
        return redirect(url_for('bayar_qris'))
    elif metode == 'transfer':
        return redirect(url_for('bayar_transfer'))
    else:
        return redirect(url_for('bayar_cod'))

@app.route('/bayar-qris')
def bayar_qris():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    keranjang = session.get('keranjang', [])
    if not keranjang:
        flash('Keranjang masih kosong.', 'error')
        return redirect(url_for('keranjang'))
    total    = sum(i['subtotal'] for i in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data     = load_data()
    qris_url = data.get('qris_image', '')
    session['order_id']    = order_id
    session['total_bayar'] = total
    return render_template('bayar_qris.html', pembeli=session['pembeli_nama'],
                           total=total, order_id=order_id, qris_url=qris_url)

@app.route('/bayar-transfer')
def bayar_transfer():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    keranjang = session.get('keranjang', [])
    if not keranjang:
        flash('Keranjang masih kosong.', 'error')
        return redirect(url_for('keranjang'))
    total    = sum(i['subtotal'] for i in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data     = load_data()
    session['order_id']    = order_id
    session['total_bayar'] = total
    return render_template('bayar_transfer.html', pembeli=session['pembeli_nama'],
                           total=total, order_id=order_id,
                           rekening=data.get('rekening_bank', []))

@app.route('/bayar-cod')
def bayar_cod():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    keranjang = session.get('keranjang', [])
    if not keranjang:
        flash('Keranjang masih kosong.', 'error')
        return redirect(url_for('keranjang'))
    total    = sum(i['subtotal'] for i in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    session['order_id']    = order_id
    session['total_bayar'] = total
    return render_template('bayar_cod.html', pembeli=session['pembeli_nama'],
                           total=total, order_id=order_id)

def _simpan_pesanan(metode, extra=None):
    data = load_data()
    if 'pesanan' not in data:
        data['pesanan'] = []
    pesanan = {
        'order_id': session.get('order_id'),
        'pembeli':  session.get('pembeli_nama'),
        'total':    session.get('total_bayar', 0),
        'metode':   metode,
        'status':   'Menunggu Verifikasi' if metode != 'COD' else 'Menunggu Konfirmasi',
        'tanggal':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'items':    session.get('keranjang', [])
    }
    if extra:
        pesanan.update(extra)
    data['pesanan'].append(pesanan)
    save_data(data)
    session['last_order_id'] = session.get('order_id')
    session.pop('keranjang', None)

@app.route('/konfirmasi-qris', methods=['POST'])
def konfirmasi_qris():
    _simpan_pesanan('QRIS')
    return redirect(url_for('struk'))

@app.route('/konfirmasi-transfer', methods=['POST'])
def konfirmasi_transfer():
    _simpan_pesanan('Transfer Bank', {'bank_pengirim': request.form.get('bank_pengirim')})
    return redirect(url_for('struk'))

@app.route('/konfirmasi-cod', methods=['POST'])
def konfirmasi_cod():
    _simpan_pesanan('COD', {
        'nama_penerima': request.form.get('nama_penerima'),
        'telepon':       request.form.get('telepon'),
        'alamat':        request.form.get('alamat'),
        'catatan':       request.form.get('catatan', '')
    })
    return redirect(url_for('struk'))

@app.route('/struk')
def struk():
    data         = load_data()
    order_id     = session.get('last_order_id') or session.get('order_id')
    pesanan      = next((p for p in data.get('pesanan', []) if p['order_id'] == order_id), None)
    if not pesanan:
        flash('Struk tidak ditemukan.', 'error')
        return redirect(url_for('index'))
    struk_data = {
        'order_id':      pesanan['order_id'],
        'pelanggan':     pesanan['pembeli'],
        'total':         pesanan['total'],
        'metode':        pesanan['metode'],
        'status':        pesanan['status'],
        'tanggal':       pesanan['tanggal'],
        'produk':        pesanan['items'],
        'nama_penerima': pesanan.get('nama_penerima',''),
        'telepon':       pesanan.get('telepon',''),
        'alamat':        pesanan.get('alamat',''),
        'catatan':       pesanan.get('catatan',''),
    }
    return render_template('struk.html', struk=struk_data)

# ── ADMIN ─────────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = 'admin123'

@app.route('/admin', methods=['GET','POST'])
def admin():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Password salah.', 'error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data = load_data()
    return render_template('admin_dashboard.html',
                           barang=data.get('barang',[]),
                           qris_url=data.get('qris_image',''),
                           data=data)

@app.route('/admin/set-qris', methods=['POST'])
def set_qris():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data     = load_data()
    qris_url = request.form.get('qris_url','').strip()
    file     = request.files.get('qris_file')
    if file and file.filename:
        raw  = file.read()
        mime = file.content_type or 'image/jpeg'
        qris_url = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    if qris_url:
        data['qris_image'] = qris_url
        save_data(data)
        flash('Gambar QRIS berhasil disimpan! ✅', 'success')
    else:
        flash('Pilih file atau masukkan URL gambar QRIS.', 'error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tambah-rekening', methods=['POST'])
def tambah_rekening():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data = load_data()
    if 'rekening_bank' not in data:
        data['rekening_bank'] = []
    data['rekening_bank'].append({
        'bank': request.form.get('bank','').strip(),
        'nomor': request.form.get('nomor','').strip(),
        'atas_nama': request.form.get('atas_nama','').strip()
    })
    save_data(data)
    flash('Rekening berhasil ditambahkan! ✅', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/hapus-rekening/<int:idx>')
def hapus_rekening(idx):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data = load_data()
    rek  = data.get('rekening_bank',[])
    if 0 <= idx < len(rek):
        rek.pop(idx)
        data['rekening_bank'] = rek
        save_data(data)
        flash('Rekening dihapus.', 'info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tambah', methods=['POST'])
def admin_tambah():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data    = load_data()
    barang  = data.get('barang',[])
    next_id = data.get('next_id',1)
    nama    = request.form.get('nama','').strip()
    harga   = int(request.form.get('harga',0))
    stok    = int(request.form.get('stok',100))
    gambar  = request.form.get('gambar','').strip()
    file    = request.files.get('gambar_file')
    if file and file.filename:
        raw    = file.read()
        mime   = file.content_type or 'image/jpeg'
        gambar = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    if nama:
        barang.append({'id':next_id,'nama':nama,'harga':harga,'stok':stok,'gambar':gambar})
        data['barang']  = barang
        data['next_id'] = next_id + 1
        save_data(data)
        flash(f'Barang "{nama}" berhasil ditambahkan! ✅', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<int:item_id>', methods=['GET','POST'])
def admin_edit(item_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data   = load_data()
    barang = data.get('barang',[])
    item   = next((b for b in barang if b['id']==item_id), None)
    if not item:
        flash('Barang tidak ditemukan.','error')
        return redirect(url_for('admin_dashboard'))
    if request.method == 'POST':
        item['nama']  = request.form.get('nama','').strip() or item['nama']
        item['harga'] = int(request.form.get('harga', item['harga']))
        item['stok']  = int(request.form.get('stok',  item['stok']))
        gambar = request.form.get('gambar','').strip()
        file   = request.files.get('gambar_file')
        if file and file.filename:
            raw    = file.read()
            mime   = file.content_type or 'image/jpeg'
            gambar = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        if gambar:
            item['gambar'] = gambar
        save_data(data)
        flash(f'Barang "{item["nama"]}" berhasil diupdate! ✅','success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_edit.html', item=item)

@app.route('/admin/hapus/<int:item_id>')
def admin_hapus(item_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data = load_data()
    data['barang'] = [b for b in data.get('barang',[]) if b['id'] != item_id]
    save_data(data)
    flash('Barang berhasil dihapus.','info')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/orders')
def admin_orders():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data = load_data()
    return render_template('admin_orders.html', pesanan=data.get('pesanan',[]))

@app.route('/admin/update-status/<order_id>', methods=['POST'])
def update_status(order_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin'))
    data    = load_data()
    status  = request.form.get('status','')
    for p in data.get('pesanan',[]):
        if p['order_id'] == order_id:
            p['status'] = status
            break
    save_data(data)
    flash(f'Status diperbarui ke: {status}','success')
    return redirect(url_for('admin_orders'))

if __name__ == '__main__':
    app.run(debug=True)
