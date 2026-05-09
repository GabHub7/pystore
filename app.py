from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from datetime import datetime
import os, json, base64, hashlib

app = Flask(__name__)
app.secret_key = 'rahasia_pystore_2026'

SEED_FILE = os.path.join(os.path.dirname(__file__), 'data.json')
TMP_FILE  = '/tmp/pystore_data.json'

def load_data():
    for path in [TMP_FILE, SEED_FILE]:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    return json.load(f)
            except: pass
    return {'barang':[],'pesanan':[],'rekening_bank':[],'qris_image':'','next_id':1,'users':[],'kategori_list':['Makanan','Minuman','Lainnya']}

def save_data(data):
    for path in [TMP_FILE, SEED_FILE]:
        try:
            with open(path, 'w') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return True
        except: continue
    return False

def hash_pw(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

# ── INDEX ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    data     = load_data()
    barang   = data.get('barang', [])
    kategori = data.get('kategori_list', [])
    q        = request.args.get('q', '').strip().lower()
    kat      = request.args.get('kategori', '').strip()
    if q:
        barang = [b for b in barang if q in b['nama'].lower()]
    if kat:
        barang = [b for b in barang if b.get('kategori','') == kat]
    return render_template('index.html', barang=barang, pembeli=session.get('pembeli_nama'),
                           kategori_list=kategori, q=q, kat_aktif=kat)

# ── AUTH PEMBELI ──────────────────────────────────────────────────────────────
@app.route('/login-pembeli', methods=['GET','POST'])
def login_pembeli():
    if request.method == 'POST':
        aksi = request.form.get('aksi','login')
        data = load_data()

        if aksi == 'register':
            nama    = request.form.get('nama','').strip()
            akun    = request.form.get('akun','').strip()
            pw      = request.form.get('password','')
            pw2     = request.form.get('konfirmasi_password','')
            telepon = request.form.get('telepon','').strip()
            alamat  = request.form.get('alamat','').strip()
            lat     = request.form.get('lat','')
            lng     = request.form.get('lng','')

            if not all([nama, akun, pw, telepon, alamat]):
                flash('Semua field wajib diisi.','error')
                return render_template('login_pembeli.html', tab='register')
            if pw != pw2:
                flash('Konfirmasi password tidak cocok.','error')
                return render_template('login_pembeli.html', tab='register')
            users = data.get('users', [])
            if any(u['akun'] == akun for u in users):
                flash('Akun sudah terdaftar, silakan login.','error')
                return render_template('login_pembeli.html', tab='register')

            users.append({
                'nama': nama, 'akun': akun,
                'password': hash_pw(pw),
                'telepon': telepon, 'alamat': alamat,
                'lat': lat, 'lng': lng,
                'created': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            })
            data['users'] = users
            save_data(data)
            flash(f'Registrasi berhasil! Silakan login, {nama}.','success')
            return render_template('login_pembeli.html', tab='login')

        else:  # login
            akun = request.form.get('akun','').strip()
            pw   = request.form.get('password','')
            users = data.get('users', [])
            user  = next((u for u in users if u['akun']==akun and u['password']==hash_pw(pw)), None)
            if not user:
                flash('Akun atau password salah.','error')
                return render_template('login_pembeli.html', tab='login')
            session['pembeli_nama']    = user['nama']
            session['pembeli_akun']    = user['akun']
            session['pembeli_telepon'] = user.get('telepon','')
            session['pembeli_alamat']  = user.get('alamat','')
            session['pembeli_lat']     = user.get('lat','')
            session['pembeli_lng']     = user.get('lng','')
            session['keranjang']       = []
            flash(f'Selamat datang, {user["nama"]}! 🎉','success')
            return redirect(url_for('index'))

    return render_template('login_pembeli.html', tab='login')

@app.route('/logout-pembeli')
def logout_pembeli():
    for k in ['pembeli_nama','pembeli_akun','pembeli_telepon','pembeli_alamat','pembeli_lat','pembeli_lng','keranjang']:
        session.pop(k, None)
    flash('Berhasil keluar.','info')
    return redirect(url_for('index'))

# ── KERANJANG ─────────────────────────────────────────────────────────────────
@app.route('/tambah-keranjang', methods=['POST'])
def tambah_keranjang():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    data   = load_data()
    id_str = request.form.get('id_barang','')
    qty    = max(1, int(request.form.get('qty', 1)))
    produk = next((b for b in data.get('barang',[]) if str(b['id'])==id_str), None)
    if not produk:
        flash('Produk tidak ditemukan.','error')
        return redirect(url_for('index'))
    keranjang = session.get('keranjang',[])
    for item in keranjang:
        if str(item['id'])==id_str:
            item['jumlah']  += qty
            item['subtotal'] = item['harga'] * item['jumlah']
            session['keranjang'] = keranjang
            flash(f'Qty {produk["nama"]} diperbarui.','success')
            return redirect(request.referrer or url_for('index'))
    gambar = produk.get('gambar','')
    keranjang.append({
        'id': produk['id'], 'nama': produk['nama'], 'harga': produk['harga'],
        'gambar': gambar if not gambar.startswith('data:') else '',
        'jumlah': qty, 'subtotal': produk['harga']*qty
    })
    session['keranjang'] = keranjang
    flash(f'{produk["nama"]} ditambahkan ke keranjang! 🛒','success')
    return redirect(request.referrer or url_for('index'))

@app.route('/keranjang')
def keranjang():
    if 'pembeli_nama' not in session:
        return redirect(url_for('login_pembeli'))
    data      = load_data()
    keranjang = session.get('keranjang',[])
    total     = sum(i['subtotal'] for i in keranjang)
    return render_template('keranjang.html', keranjang=keranjang,
                           pembeli=session['pembeli_nama'], total=total,
                           qris_tersedia=bool(data.get('qris_image','')))

@app.route('/hapus-keranjang/<int:item_id>')
def hapus_keranjang(item_id):
    if 'keranjang' in session:
        session['keranjang']=[i for i in session['keranjang'] if i['id']!=item_id]
    return redirect(url_for('keranjang'))

# ── PILIH BAYAR ───────────────────────────────────────────────────────────────
@app.route('/pilih-bayar', methods=['POST'])
def pilih_bayar():
    if 'pembeli_nama' not in session: return redirect(url_for('login_pembeli'))
    metode = request.form.get('metode','cod')
    if   metode=='qris':     return redirect(url_for('bayar_qris'))
    elif metode=='transfer': return redirect(url_for('bayar_transfer'))
    else:                    return redirect(url_for('bayar_cod'))

@app.route('/bayar-qris')
def bayar_qris():
    if 'pembeli_nama' not in session: return redirect(url_for('login_pembeli'))
    keranjang = session.get('keranjang',[])
    if not keranjang:
        flash('Keranjang kosong.','error'); return redirect(url_for('keranjang'))
    total    = sum(i['subtotal'] for i in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data     = load_data()
    session['order_id']    = order_id
    session['total_bayar'] = total
    return render_template('bayar_qris.html', pembeli=session['pembeli_nama'],
                           total=total, order_id=order_id, qris_url=data.get('qris_image',''))

@app.route('/bayar-transfer')
def bayar_transfer():
    if 'pembeli_nama' not in session: return redirect(url_for('login_pembeli'))
    keranjang = session.get('keranjang',[])
    if not keranjang:
        flash('Keranjang kosong.','error'); return redirect(url_for('keranjang'))
    total    = sum(i['subtotal'] for i in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    data     = load_data()
    session['order_id']    = order_id
    session['total_bayar'] = total
    return render_template('bayar_transfer.html', pembeli=session['pembeli_nama'],
                           total=total, order_id=order_id, rekening=data.get('rekening_bank',[]))

@app.route('/bayar-cod')
def bayar_cod():
    if 'pembeli_nama' not in session: return redirect(url_for('login_pembeli'))
    keranjang = session.get('keranjang',[])
    if not keranjang:
        flash('Keranjang kosong.','error'); return redirect(url_for('keranjang'))
    total    = sum(i['subtotal'] for i in keranjang)
    order_id = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    session['order_id']    = order_id
    session['total_bayar'] = total
    return render_template('bayar_cod.html', pembeli=session['pembeli_nama'],
                           total=total, order_id=order_id,
                           alamat_user=session.get('pembeli_alamat',''),
                           telepon_user=session.get('pembeli_telepon',''),
                           lat_user=session.get('pembeli_lat',''),
                           lng_user=session.get('pembeli_lng',''))

def _simpan_pesanan(metode, extra=None):
    data = load_data()
    data.setdefault('pesanan',[])
    items = [{'id':i['id'],'nama':i['nama'],'harga':i['harga'],
              'jumlah':i['jumlah'],'subtotal':i['subtotal']}
             for i in session.get('keranjang',[])]
    pesanan = {
        'order_id': session.get('order_id','ORD-?'),
        'pembeli':  session.get('pembeli_nama','?'),
        'akun':     session.get('pembeli_akun',''),
        'total':    session.get('total_bayar',0),
        'metode':   metode,
        'status':   'Menunggu Verifikasi' if metode!='COD' else 'Menunggu Konfirmasi',
        'tanggal':  datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'produk':   items
    }
    if extra: pesanan.update(extra)
    data['pesanan'].append(pesanan)
    ok = save_data(data)
    session['last_order_id'] = pesanan['order_id']
    session['last_pesanan']  = pesanan
    session.pop('keranjang', None)
    return ok

@app.route('/konfirmasi-qris', methods=['POST'])
def konfirmasi_qris():
    _simpan_pesanan('QRIS'); return redirect(url_for('struk'))

@app.route('/konfirmasi-transfer', methods=['POST'])
def konfirmasi_transfer():
    _simpan_pesanan('Transfer Bank',{'bank_pengirim':request.form.get('bank_pengirim','')})
    return redirect(url_for('struk'))

@app.route('/konfirmasi-cod', methods=['POST'])
def konfirmasi_cod():
    _simpan_pesanan('COD',{
        'nama_penerima': request.form.get('nama_penerima',''),
        'telepon':       request.form.get('telepon',''),
        'alamat':        request.form.get('alamat',''),
        'lat':           request.form.get('lat',''),
        'lng':           request.form.get('lng',''),
        'catatan':       request.form.get('catatan','')
    })
    return redirect(url_for('struk'))

@app.route('/struk')
def struk():
    data     = load_data()
    order_id = session.get('last_order_id') or session.get('order_id')
    pesanan  = next((p for p in data.get('pesanan',[]) if p['order_id']==order_id), None)
    if not pesanan: pesanan = session.get('last_pesanan')
    if not pesanan:
        flash('Struk tidak ditemukan.','error'); return redirect(url_for('index'))
    return render_template('struk.html', struk={
        'order_id':      pesanan['order_id'],
        'pelanggan':     pesanan['pembeli'],
        'total':         pesanan['total'],
        'metode':        pesanan['metode'],
        'status':        pesanan['status'],
        'tanggal':       pesanan['tanggal'],
        'produk':        pesanan.get('produk',[]),
        'nama_penerima': pesanan.get('nama_penerima',''),
        'telepon':       pesanan.get('telepon',''),
        'alamat':        pesanan.get('alamat',''),
        'lat':           pesanan.get('lat',''),
        'lng':           pesanan.get('lng',''),
        'catatan':       pesanan.get('catatan',''),
    })

# ── PESANAN SAYA ──────────────────────────────────────────────────────────────
@app.route('/pesanan-saya')
def pesanan_saya():
    if 'pembeli_nama' not in session: return redirect(url_for('login_pembeli'))
    data      = load_data()
    pembeli   = session['pembeli_nama']
    my_orders = list(reversed([p for p in data.get('pesanan',[]) if p.get('pembeli')==pembeli]))
    return render_template('pesanan_saya.html', pesanan=my_orders, pembeli=pembeli)

@app.route('/ajukan-batal/<order_id>', methods=['POST'])
def ajukan_batal(order_id):
    if 'pembeli_nama' not in session: return redirect(url_for('login_pembeli'))
    data    = load_data()
    pembeli = session['pembeli_nama']
    alasan  = request.form.get('alasan_pilihan','')
    chat    = request.form.get('alasan_chat','').strip()
    alasan_final = f"{alasan} — {chat}" if chat else alasan
    for p in data.get('pesanan',[]):
        if p.get('order_id')==order_id and p.get('pembeli')==pembeli:
            if p.get('status') in ['Dikirim','Selesai','Dibatalkan']:
                flash('Tidak bisa dibatalkan pada status ini.','error')
                return redirect(url_for('pesanan_saya'))
            p['status']='Permintaan Batal'
            p['alasan_batal']=alasan_final
            p['waktu_minta_batal']=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            p['keputusan_batal']=''; p['alasan_tolak_batal']=''; break
    save_data(data)
    flash('Permintaan pembatalan terkirim ke admin.','success')
    return redirect(url_for('pesanan_saya'))

# ── ADMIN ─────────────────────────────────────────────────────────────────────
ADMIN_PASSWORD = 'admin123'

@app.route('/admin', methods=['GET','POST'])
def admin():
    if session.get('admin_logged_in'): return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        if request.form.get('password')==ADMIN_PASSWORD:
            session['admin_logged_in']=True
            return redirect(url_for('admin_dashboard'))
        flash('Password salah.','error')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in',None); return redirect(url_for('admin'))

@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data = load_data()
    return render_template('admin_dashboard.html',
                           barang=data.get('barang',[]),
                           qris_url=data.get('qris_image',''),
                           kategori_list=data.get('kategori_list',[]),
                           data=data)

@app.route('/admin/set-qris', methods=['POST'])
def set_qris():
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data     = load_data()
    qris_url = request.form.get('qris_url','').strip()
    file     = request.files.get('qris_file')
    if file and file.filename:
        try:
            raw=file.read(); mime=file.content_type or 'image/jpeg'
            qris_url=f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        except Exception as e:
            flash(f'Gagal baca file: {e}','error'); return redirect(url_for('admin_dashboard'))
    if qris_url:
        data['qris_image']=qris_url; save_data(data)
        flash('QRIS berhasil disimpan! ✅','success')
    else:
        flash('Pilih file atau masukkan URL.','error')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tambah-rekening', methods=['POST'])
def tambah_rekening():
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data = load_data()
    data.setdefault('rekening_bank',[]).append({
        'bank':request.form.get('bank','').strip(),
        'nomor':request.form.get('nomor','').strip(),
        'atas_nama':request.form.get('atas_nama','').strip()
    })
    save_data(data); flash('Rekening ditambahkan! ✅','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/hapus-rekening/<int:idx>')
def hapus_rekening(idx):
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); rek=data.get('rekening_bank',[])
    if 0<=idx<len(rek): rek.pop(idx); data['rekening_bank']=rek; save_data(data)
    flash('Rekening dihapus.','info'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/tambah-kategori', methods=['POST'])
def tambah_kategori():
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data = load_data()
    kat  = request.form.get('kategori','').strip()
    if kat and kat not in data.get('kategori_list',[]):
        data.setdefault('kategori_list',[]).append(kat)
        save_data(data); flash(f'Kategori "{kat}" ditambahkan! ✅','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/hapus-kategori/<kat>')
def hapus_kategori(kat):
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); kl=data.get('kategori_list',[])
    if kat in kl: kl.remove(kat); data['kategori_list']=kl; save_data(data)
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/tambah', methods=['POST'])
def admin_tambah():
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); barang=data.get('barang',[]); next_id=data.get('next_id',1)
    nama=request.form.get('nama','').strip()
    harga=int(request.form.get('harga',0) or 0)
    stok=int(request.form.get('stok',100) or 100)
    gambar=request.form.get('gambar','').strip()
    kategori=request.form.get('kategori','Lainnya')
    file=request.files.get('gambar_file')
    if file and file.filename:
        raw=file.read(); mime=file.content_type or 'image/jpeg'
        gambar=f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    if nama:
        barang.append({'id':next_id,'nama':nama,'harga':harga,'stok':stok,'gambar':gambar,'kategori':kategori})
        data['barang']=barang; data['next_id']=next_id+1; save_data(data)
        flash(f'Barang "{nama}" ditambahkan! ✅','success')
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/edit/<int:item_id>', methods=['GET','POST'])
def admin_edit(item_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); barang=data.get('barang',[])
    item=next((b for b in barang if b['id']==item_id),None)
    if not item:
        flash('Barang tidak ditemukan.','error'); return redirect(url_for('admin_dashboard'))
    if request.method=='POST':
        item['nama']=request.form.get('nama','').strip() or item['nama']
        item['harga']=int(request.form.get('harga',item['harga']) or item['harga'])
        item['stok']=int(request.form.get('stok',item['stok']) or item['stok'])
        item['kategori']=request.form.get('kategori',item.get('kategori','Lainnya'))
        gambar=request.form.get('gambar','').strip()
        file=request.files.get('gambar_file')
        if file and file.filename:
            raw=file.read(); mime=file.content_type or 'image/jpeg'
            gambar=f"data:{mime};base64,{base64.b64encode(raw).decode()}"
        if gambar: item['gambar']=gambar
        save_data(data); flash(f'Barang "{item["nama"]}" diupdate! ✅','success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin_edit.html', item=item, kategori_list=data.get('kategori_list',[]))

@app.route('/admin/hapus/<int:item_id>')
def admin_hapus(item_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); data['barang']=[b for b in data.get('barang',[]) if b['id']!=item_id]
    save_data(data); flash('Barang dihapus.','info'); return redirect(url_for('admin_dashboard'))

@app.route('/admin/orders')
def admin_orders():
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data()
    return render_template('admin_orders.html', pesanan=data.get('pesanan',[]))

@app.route('/admin/update-status/<order_id>', methods=['POST'])
def update_status(order_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); status=request.form.get('status','')
    for p in data.get('pesanan',[]):
        if p['order_id']==order_id: p['status']=status; break
    save_data(data); flash(f'Status diperbarui: {status}','success')
    return redirect(url_for('admin_orders'))

@app.route('/admin/keputusan-batal/<order_id>', methods=['POST'])
def keputusan_batal(order_id):
    if not session.get('admin_logged_in'): return redirect(url_for('admin'))
    data=load_data(); keputusan=request.form.get('keputusan','')
    alasan_tolak=request.form.get('alasan_tolak','').strip()
    for p in data.get('pesanan',[]):
        if p['order_id']==order_id:
            if keputusan=='setuju':
                p['status']='Dibatalkan'; p['keputusan_batal']='setuju'; p['alasan_tolak_batal']=''
            elif keputusan=='tolak':
                p['status']='Diproses'; p['keputusan_batal']='tolak'
                p['alasan_tolak_batal']=alasan_tolak or 'Permintaan ditolak.'
            break
    save_data(data); flash('Keputusan tersimpan.','success')
    return redirect(url_for('admin_orders'))

if __name__ == '__main__':
    app.run(debug=True)
