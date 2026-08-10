# Mikroskop Alan Birleştirici

Microsoft Image Composite Editor'a (ICE) benzer şekilde, telefonla oküler
üzerinden farklı alanlardan çekilen fotoğrafları tek bir kompozit görüntüde
birleştirir. Farklı objektif/büyütmelerden gelen fotoğrafları **otomatik
tespit edip** ayrı kompozitler üretir.

## Kurulum

```bash
pip install opencv-contrib-python numpy Pillow --break-system-packages
```

Görsel arayüz (GUI) için `tkinter` gerekir:
- **Windows / macOS (python.org kurulumu):** genelde hazır gelir.
- **Linux:** `sudo apt install python3-tk`

## Dosyalar

| Dosya | Ne işe yarar |
|---|---|
| `mikroskop_core.py` | Ortak motor (ön işleme, stitching, büyütme tespiti). Diğer iki dosya bunu kullanır, tek başına çalıştırılmaz. |
| `mikroskop_gui.py` | **Görsel arayüz.** Fare ile "Fotoğraf Seç" penceresinden çoklu dosya seçip önizleyebilir, tek tuşla birleştirir. |
| `mikroskop_birlestir.py` | Komut satırı (CLI) sürümü, otomasyon/toplu işlem için. |

## Görsel arayüzü çalıştırma

```bash
python3 mikroskop_gui.py
```

1. **"📁 Fotoğraf Seç..."** ile bilgisayarınızdan istediğiniz kadar fotoğrafı
   fare ile seçin (küçük önizlemeleri görünür).
2. Işık eşitleme / vinyet düzeltme / otomatik objektif ayırma kutucuklarını
   isteğinize göre işaretleyin.
3. Kayıt klasörünü seçin, **"▶ Birleştir"** tuşuna basın.
4. Farklı büyütme grupları tespit edilirse her biri için ayrı bir dosya
   (`sonuc_grup1.png`, `sonuc_grup2.png`, ...) üretilir; tek grup varsa tek
   `sonuc.png` üretilir.

## Komut satırından çalıştırma

```bash
python3 mikroskop_birlestir.py --girdi ./fotograflar --cikti sonuc.png --isik-esitle --vinyet-duzelt
```

## Farklı objektif/büyütme tespiti nasıl çalışır?

SIFT özellik eşleştirmesi ölçekten bağımsız çalıştığı için, iki fotoğraf
farklı büyütmede çekilmiş olsa bile eşleşen noktalar bulunabilir. Program
eşleşen noktalardan aradaki **gerçek ölçek oranını** hesaplar:

- Oran ~1.0 civarındaysa (varsayılan tolerans 0.8–1.25) **aynı objektif**
  kabul edilir ve aynı grupta birleştirilir.
- Oran bu aralığın dışındaysa (örn. 2x, 2.5x, 4x gibi tipik objektif
  adımları) **farklı büyütme** kabul edilir, ayrı gruba ayrılır.

Bu eşiği CLI'da `--olcek-tolerans-dusuk` / `--olcek-tolerans-yuksek` ile
ayarlayabilirsiniz. Not: EXIF/meta veriye değil, doğrudan görüntü içeriğine
bakar; bu yüzden telefonun objektif/büyütme bilgisini kaydetmesine gerek yoktur.

## Gruplar gereksiz yere bölünüyorsa: "Eşleştirme eforu"

Gerçek fotoğraflarda (özellikle düşük kontrastlı doku alanlarında veya
örtüşme azsa) varsayılan ayarlar bazen aslında örtüşen görüntüleri
eşleştiremeyip gereksiz sayıda küçük/tekil grup üretebilir. Bunun için üç
efor seviyesi var:

| Efor | Hız | Ne yapar |
|---|---|---|
| `hizli` | En hızlı | Küçük çözünürlükte eşleştirme, sıkı eşikler |
| `normal` (varsayılan) | Orta | Biraz daha büyük çözünürlük, hafif kontrast artırma |
| `yuksek` | En yavaş, en kapsamlı | Yüksek çözünürlükte eşleştirme, kontrast artırma (CLAHE), gevşek eşikler, SIFT başarısız olursa ORB ile ikinci deneme, **ve** hem cv2.Stitcher hem de tüm görüntüleri kapsayan graf-tabanlı özel yöntemi deneyip hangisi daha eksiksizse onu seçer |

GUI'de "Eşleştirme eforu" açılır kutusundan, CLI'da `--efor yuksek` ile
seçilir. Gruplama hâlâ yanlışsa (fazla parçalanıyor ya da farklı objektifler
birleştiriliyor) `--olcek-tolerans-dusuk` / `--olcek-tolerans-yuksek`
değerlerini de birlikte ayarlayabiliriz; hatta hepsinin tek bir alandan
geldiğini biliyorsanız `--tek-grup` ile tespiti tamamen kapatıp zorla tek
kompozit üretebilirsiniz.

## Sınırlamalar

- Komşu fotoğraflar arasında en az %30-40 örtüşme önerilir.
- Çok homojen/tekstürsüz dokularda (özellik noktası az) eşleştirme
  zorlanabilir; dosya adlarını çekim sırasına göre numaralandırmak faydalı olur.
- Çok sayıda (>40) fotoğrafta otomatik büyütme tespiti (ikili karşılaştırma
  yaptığı için) biraz zaman alabilir.
