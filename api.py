from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
import sqlite3
import speech_recognition as sr
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
import os
from fuzzywuzzy import fuzz
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'supersifre'

# Resimlerin yükleneceği klasör
UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# İzin verilen dosya uzantıları
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Dosya uzantısı kontrolü
def izin_verilen_dosya(dosya_adi):
    return '.' in dosya_adi and dosya_adi.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Veritabanı ve tabloları oluştur
def veritabani_olustur():
    conn = sqlite3.connect('school.db')
    cursor = conn.cursor()
    
    # Dersler tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS dersler (
            ders_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ders_adi TEXT NOT NULL
        )
    ''')
    
    # Öğrenciler tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS ogrenciler (
            ogrenci_id INTEGER PRIMARY KEY AUTOINCREMENT,
            tam_adi TEXT NOT NULL,
            ogrenci_numarasi TEXT,
            foto_yolu TEXT,
            ders_id INTEGER,
            FOREIGN KEY (ders_id) REFERENCES dersler (ders_id)
        )
    ''')
    
    # Yoklama tablosu
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS yoklama (
            yoklama_id INTEGER PRIMARY KEY AUTOINCREMENT,
            ogrenci_id INTEGER,
            ders_id INTEGER,
            katildi BOOLEAN DEFAULT FALSE,
            FOREIGN KEY (ogrenci_id) REFERENCES ogrenciler (ogrenci_id),
            FOREIGN KEY (ders_id) REFERENCES dersler (ders_id)
        )
    ''')
    
    conn.commit()
    conn.close()

veritabani_olustur()

# Ana sayfa
@app.route('/')
def ana_sayfa():
    conn = sqlite3.connect('school.db')
    cursor = conn.cursor()
    
    # Dersleri getir
    cursor.execute('SELECT ders_id, ders_adi FROM dersler')
    dersler = cursor.fetchall()
    
    # Öğrencileri ve ders adlarını getir
    cursor.execute('''
        SELECT o.ogrenci_id, o.tam_adi, o.ogrenci_numarasi, o.foto_yolu, o.ders_id, d.ders_adi
        FROM ogrenciler o
        JOIN dersler d ON o.ders_id = d.ders_id
    ''')
    ogrenciler = cursor.fetchall()
    
    conn.close()
    return render_template('index.html', dersler=dersler, ogrenciler=ogrenciler)

# Ders ekle
@app.route('/ders_ekle', methods=['POST'])
def ders_ekle():
    ders_adi = request.form['ders_adi']
    if ders_adi:
        conn = sqlite3.connect('school.db')
        cursor = conn.cursor()
        cursor.execute('INSERT INTO dersler (ders_adi) VALUES (?)', (ders_adi,))
        conn.commit()
        conn.close()
        flash("Ders başarıyla eklendi", "success")
    else:
        flash("Lütfen ders adını girin", "error")
    return redirect(url_for('ana_sayfa'))

# Öğrenci ekle
@app.route('/ogrenci_ekle', methods=['POST'])
def ogrenci_ekle():
    tam_adi = request.form['tam_adi']
    ogrenci_numarasi = request.form['ogrenci_numarasi']
    ders_id = request.form['ders_id']
    
    # Fotoğraf yükleme
    if 'foto' not in request.files:
        flash("Fotoğraf yüklenmedi", "error")
        return redirect(url_for('ana_sayfa'))
    
    foto = request.files['foto']
    if foto.filename == '':
        flash("Fotoğraf seçilmedi", "error")
        return redirect(url_for('ana_sayfa'))
    
    if foto and izin_verilen_dosya(foto.filename):
        dosya_adi = secure_filename(foto.filename)
        foto_yolu = os.path.join(app.config['UPLOAD_FOLDER'], dosya_adi)
        foto.save(foto_yolu)
        
        # Öğrenciyi veritabanına ekle
        conn = sqlite3.connect('school.db')
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO ogrenciler (tam_adi, ogrenci_numarasi, foto_yolu, ders_id)
            VALUES (?, ?, ?, ?)
        ''', (tam_adi, ogrenci_numarasi, foto_yolu, ders_id))
        conn.commit()
        conn.close()
        
        flash("Öğrenci başarıyla eklendi", "success")
    else:
        flash("Geçersiz dosya uzantısı", "error")
    
    return redirect(url_for('ana_sayfa'))

# Öğrenci sil
@app.route('/ogrenci_sil/<int:ogrenci_id>')
def ogrenci_sil(ogrenci_id):
    conn = sqlite3.connect('school.db')
    cursor = conn.cursor()
    cursor.execute('DELETE FROM ogrenciler WHERE ogrenci_id = ?', (ogrenci_id,))
    cursor.execute('DELETE FROM yoklama WHERE ogrenci_id = ?', (ogrenci_id,))
    conn.commit()
    conn.close()
    flash("Öğrenci başarıyla silindi", "success")
    return redirect(url_for('ana_sayfa'))

# Öğrenciyi dersten sil
@app.route('/ogrenciyi_dersten_sil/<int:ogrenci_id>/<int:ders_id>')
def ogrenciyi_dersten_sil(ogrenci_id, ders_id):
    conn = sqlite3.connect('school.db')
    cursor = conn.cursor()
    
    # Öğrenciyi dersten sil
    cursor.execute('DELETE FROM ogrenciler WHERE ogrenci_id = ? AND ders_id = ?', (ogrenci_id, ders_id))
    
    # Öğrencinin yoklama kayıtlarını sil
    cursor.execute('DELETE FROM yoklama WHERE ogrenci_id = ? AND ders_id = ?', (ogrenci_id, ders_id))
    
    conn.commit()
    conn.close()
    flash("Öğrenci dersten başarıyla silindi", "success")
    return redirect(url_for('ana_sayfa'))

# Yoklama al
@app.route('/yoklama_al', methods=['POST'])
def yoklama_al():
    ders_id = request.form['ders_id']
    recognizer = sr.Recognizer()

    # Başlangıç mesajı
    initial_message = "İsminizi söyleyin..."
    response_data = {
        "status": "listening",
        "message": initial_message
    }

    with sr.Microphone() as source:
        try:
            audio = recognizer.listen(source)
            isim = recognizer.recognize_google(audio, language="tr-TR")
            print(f"Tanınan isim: {isim}")
            
            # Bulanık eşleme ile öğrenci bul
            ogrenci = ogrenci_bul(isim, ders_id)
            
            if ogrenci:
                ogrenci_id = ogrenci[0]
                conn = sqlite3.connect('school.db')
                cursor = conn.cursor()
                # Yoklamayı kaydet
                cursor.execute('''
                    INSERT INTO yoklama (ogrenci_id, ders_id, katildi)
                    VALUES (?, ?, ?)
                ''', (ogrenci_id, ders_id, True))
                conn.commit()
                conn.close()

                response_data = {
                    "status": "success",
                    "ogrenci_adi": ogrenci[1],
                    "message": f"{ogrenci[1]} öğrencisinin yoklaması kaydedildi"
                }
            else:
                response_data = {
                    "status": "error",
                    "message": "Bu öğrenci derse kayıtlı değil"
                }
            
        except sr.UnknownValueError:
            response_data = {
                "status": "error",
                "message": "Ses anlaşılamadı"
            }
        except sr.RequestError:
            response_data = {
                "status": "error",
                "message": "Ses tanıma servisinde hata"
            }
    
    return jsonify(response_data)

# Rapor oluştur
@app.route('/rapor_olustur/<int:ders_id>')
def rapor_olustur(ders_id):
    conn = sqlite3.connect('school.db')
    cursor = conn.cursor()
    
    # Ders adını getir
    cursor.execute('SELECT ders_adi FROM dersler WHERE ders_id = ?', (ders_id,))
    ders_adi = cursor.fetchone()[0]
    
    # Öğrenci ve yoklama bilgilerini getir
    cursor.execute('''
        SELECT o.tam_adi, o.ogrenci_numarasi, o.foto_yolu, y.katildi
        FROM ogrenciler o 
        LEFT JOIN yoklama y ON o.ogrenci_id = y.ogrenci_id 
        WHERE o.ders_id = ?
    ''', (ders_id,))
    
    ogrenciler = cursor.fetchall()
    conn.close()
    
    # PDF oluştur
    pdf_yolu = f"yoklama_raporu_ders_{ders_id}.pdf"
    c = canvas.Canvas(pdf_yolu, pagesize=letter)
    
    # Rapor başlığı
    c.drawString(100, 750, f"Yoklama Raporu - Ders: {ders_adi}")
    
    y = 700
    for ogrenci in ogrenciler:
        tam_adi, ogrenci_numarasi, foto_yolu, katildi = ogrenci
        durum = "Var" if katildi else "Yok"
        c.drawString(100, y, f"{tam_adi} ({ogrenci_numarasi}): {durum}")
        if foto_yolu and os.path.exists(foto_yolu):
            c.drawImage(foto_yolu, 300, y - 20, width=50, height=50)
        y -= 60
    
    c.save()
    flash(f"Rapor başarıyla oluşturuldu: {pdf_yolu}", "success")
    return redirect(url_for('ana_sayfa'))

# Bulanık eşleme ile öğrenci bul
def ogrenci_bul(isim, ders_id):
    conn = sqlite3.connect('school.db')
    cursor = conn.cursor()
    cursor.execute('SELECT ogrenci_id, tam_adi FROM ogrenciler WHERE ders_id = ?', (ders_id,))
    ogrenciler = cursor.fetchall()
    conn.close()
    
    en_iyi_eslesme = None
    en_iyi_puan = 0
    
    for ogrenci in ogrenciler:
        ogrenci_adi = ogrenci[1]
        puan = fuzz.ratio(isim.lower(), ogrenci_adi.lower())
        if puan > en_iyi_puan:
            en_iyi_puan = puan
            en_iyi_eslesme = ogrenci
    
    if en_iyi_puan > 70:  # Minimum eşleşme puanı
        return en_iyi_eslesme
    else:
        return None

if __name__ == '__main__':
    # Uploads klasörünü oluştur
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    
    app.run(debug=True)