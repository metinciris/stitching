# MicroStitch Studio — AI & Developer Guide

Bu dosya, MicroStitch Studio üzerinde ileride çalışacak geliştiriciler ve yapay zeka tabanlı kodlama araçları için teknik yönlendirme belgesidir.

> Amaç: Telefonla mikroskop okülerinden çekilmiş, kısmen örtüşen histopatoloji görüntülerini mümkün olduğunca yüksek geometrik ve renk doğruluğuyla tek bir whole-slide-benzeri mozaik görüntüye dönüştürmek.

---

## 1. Projenin temel ilkesi

Bu proje klasik bir manzara panoraması oluşturucu değildir. Histopatoloji görüntülerinde küçük geometrik hatalar bile tanısal yapıları bozabilir.

Bu nedenle geliştirme sırasında öncelik sırası şudur:

1. **Doku geometrisini korumak**
2. **Nükleusların çift görünmesini / üst üste binmesini önlemek**
3. **H&E renklerini korumak**
4. **Arka plan beyazlığını tutarlı hale getirmek**
5. **Mümkün olan en yüksek gerçek çözünürlüğü korumak**
6. **Kullanıcı arayüzünü basit ve okunabilir tutmak**

Görsel olarak daha “yumuşak” fakat histolojik yapıyı bozan bir sonuç, daha keskin ama doğru hizalanmış bir sonuçtan iyi kabul edilmemelidir.

---

## 2. Ana kullanım senaryosu

Tipik girdi:

- Akıllı telefon ile mikroskop okülerinden çekilmiş JPEG/PNG görüntüler
- Aynı kesitin farklı alanlarını kapsayan kareler
- Kareler arasında yaklaşık %20–50 örtüşme
- Aynı seri içinde küçük dönme, kayma ve pozlama farkları
- Bazı veri setlerinde farklı objektif/büyütme ile çekilmiş görüntüler
- Oküler kaynaklı siyah dairesel kenarlar
- Alan boyunca değişen parlaklık / vinyet

Tipik çıktı:

- Yüksek çözünürlüklü birleşik PNG/TIFF
- Whole-slide-benzeri genel görünüm
- Mümkün olduğunca tekil, çiftlenmemiş nükleuslar
- Homojen beyaz arka plan
- Korunmuş hematoksilen/eozin renk ilişkisi

---

## 3. Değiştirilmemesi gereken temel davranışlar

Yeni geliştirmeler aşağıdaki prensipleri bozmamalıdır.

### 3.1 Farklı objektifleri körlemesine harmanlamayın

Farklı büyütmedeki kareleri aynı çözünürlük katmanında doğrudan alpha blending ile birleştirmek nükleus çiftlenmesine ve lokal çözünürlük değişimine neden olabilir.

Tercih edilen yaklaşım:

- aynı büyütmedeki kareleri ayrı grup olarak çözmek,
- en yüksek çözünürlüklü grubu ana mozaik olarak kullanmak,
- düşük büyütmeyi yalnızca overview veya eksik alan doldurma amacıyla değerlendirmek.

### 3.2 Serbest homografiyi varsayılan yapmayın

Mikroskop görüntülerinde agresif perspective/homography dönüşümleri dokuyu esnetebilir.

Varsayılan dönüşüm modeli mümkün olduğunca:

- translation,
- rotation,
- uniform scale

ile sınırlı **similarity / partial affine** olmalıdır.

Homografi ancak açıkça gerekli olduğu gösterilirse ve kalite kontrollerini geçerse kullanılmalıdır.

### 3.3 Geniş alpha averaging kullanmayın

Örtüşen bölgelerde iki görüntüyü geniş bir alanda %50/%50 karıştırmak, küçük kayıt hatalarını bulanık veya çift nükleus şeklinde görünür hale getirir.

Tercih edilen yöntemler:

- graph-cut seam,
- minimum-error seam,
- dar feathering,
- sınırlı multiband blend.

### 3.4 H&E rengini “güzelleştirmek” için otomatik yeniden boyamayın

Renk düzeltme tanısal yapıyı korumalıdır.

Varsayılan hedef:

- görüntüler arası white balance uyumu,
- aydınlatma/vinyet düzeltmesi,
- lokal parlaklık eşitleme,
- mümkün olduğunca düşük chroma değişimi.

AI tabanlı yeniden renklendirme veya stain transfer uygulanacaksa bu özellik açıkça opsiyonel olmalı ve ham/orijinal renkli çıktı da korunmalıdır.

---

## 4. Önerilen stitching mimarisi

Yeni kod veya refactor sırasında aşağıdaki mimari tercih edilir.

### A. Pre-processing

Her görüntü için:

1. Görüntüyü güvenli şekilde yükle.
2. EXIF orientation varsa uygula.
3. Siyah oküler çevresini tespit et.
4. Geçerli görüş alanı maskesi oluştur.
5. Doku içermeyen saf beyaz alanlarda feature üretimini azalt.
6. Aydınlatma/vinyet modelini tahmin et.
7. Gerekirse yalnızca matching için downsample edilmiş kopya üret.

Orijinal tam çözünürlük görüntüsü final render için saklanmalıdır.

### B. Feature detection

Tercih edilen başlangıç yöntemi:

- SIFT

Alternatifler benchmark edilerek eklenebilir:

- AKAZE
- ORB
- learned local features

Feature seçimi özellikle gerçek doku bölgelerine ağırlık vermelidir. Beyaz arka plan, siyah oküler sınırı ve JPEG artefaktları eşleşme kaynağı haline gelmemelidir.

### C. Pairwise matching

Önerilen kontroller:

- k-NN matching
- Lowe ratio test
- mümkünse mutual/cross check
- RANSAC
- minimum inlier sayısı
- inlier ratio
- ölçek sınırı
- rotation sınırı
- reprojection error

Şüpheli edge'ler pose graph'e eklenmemelidir.

### D. Pose graph

Görüntüleri sırayla büyüyen bir canvas'a eklemek yerine önce global ilişki grafiği oluşturmak tercih edilir.

Her düğüm = bir görüntü

Her edge = güvenilir pairwise transform

Global optimization ile tüm pozlar birlikte çözülmelidir.

Faydaları:

- drift azalır,
- loop closure kullanılabilir,
- tek bir yanlış eşleşmenin tüm mozaiği kaydırması zorlaşır.

### E. Objective / magnification grouping

Pairwise transform ölçekleri ve görüntü ilişkileri kullanılarak olası büyütme grupları belirlenebilir.

Gruplama sonucu kullanıcıya gösterilmelidir.

Otomatik karar belirsizse kullanıcı manuel olarak grubu değiştirebilmelidir.

### F. Full-resolution rendering

Matching düşük çözünürlükte yapılabilir; final render mutlaka mümkün olduğunca orijinal piksel verisinden yapılmalıdır.

Geometrik dönüşümlerde yüksek kaliteli interpolation kullanılmalıdır.

Öneri:

- `cv2.INTER_LANCZOS4`

Ancak tekrar tekrar resampling yapılmamalıdır. Her kaynak kare ideal olarak yalnızca bir kez final canvas koordinatlarına warp edilmelidir.

### G. Seam selection

Örtüşme bölgesinde seam maliyeti hesaplarken değerlendirilebilecek bileşenler:

- gradient farkı
- intensity farkı
- stain/color farkı
- local sharpness
- tissue probability

Seam mümkün olduğunca belirgin nükleusların içinden geçmemelidir.

### H. Background normalization

Amaç “her şeyi beyaza çevirmek” değildir.

Yalnızca gerçekten lam/boş arka plan olduğu düşünülen bölgelerde:

- vinyet düzeltme,
- low-frequency illumination correction,
- white point normalization

uygulanmalıdır.

Doku içindeki açık stromal alanların yanlışlıkla silinmemesine dikkat edilmelidir.

---

## 5. Kalite metrikleri

Bir geliştirme yalnızca görsel olarak değerlendirilmemelidir.

Mümkün olduğunda rapora şu değerler eklenmelidir:

- toplam görüntü sayısı
- eşleşen / eşleşmeyen görüntü sayısı
- objective group sayısı
- güvenilir graph edge sayısı
- median registration error
- 90/95 percentile registration error
- rejected pair count
- final canvas width/height
- toplam megapiksel
- her kaynak görüntünün finalde kullanılıp kullanılmadığı
- tahmini overlap oranları
- global scale dağılımı

İleride otomatik kalite uyarıları eklenebilir.

Örnek:

- `Registration warning`
- `Possible wrong magnification group`
- `Insufficient overlap`
- `Large illumination mismatch`
- `Disconnected image component`

---

## 6. GUI geliştirme kuralları

Arayüz patoloji laboratuvarında uzun süre kullanılabileceği için okunabilirlik önemlidir.

### Görsel öncelikler

- küçük fontlardan kaçının
- düşük kontrastlı gri metin kullanmayın
- ana eylemler belirgin olmalı
- sol panel gereğinden dar olmamalı
- dosya adları mümkünse tooltip ile tam gösterilmeli
- progress log monospace olabilir ancak minimum okunabilir font boyutu korunmalı
- Preview / Settings / Process log sekmeleri açıkça ayrılmalı
- durum bilgileri tek bakışta anlaşılmalı

### Önerilen temel ekranlar

**Input panel**

- Add images
- Add folder
- Remove
- Clear
- drag & drop
- thumbnail list

**Workspace**

- Preview
- Settings
- Process log

**Summary cards**

- Images
- Objective groups
- Median registration
- Final canvas

**Output controls**

- output directory
- PNG
- TIFF / pyramidal TIFF
- report JSON

### Uzun işlemler

GUI thread'i bloklanmamalıdır.

- stitching worker thread içinde çalışmalı
- progress signal göndermeli
- Cancel güvenli biçimde desteklenmeli
- hata traceback'i mümkünse kullanıcı dostu özet ile log'a yazılmalı

---

## 7. Kaynak kod organizasyonu için öneri

Proje büyüdükçe tek Python dosyasından şu yapıya geçilebilir:

```text
stitching/
├─ app.py
├─ requirements.txt
├─ README.md
├─ AGENTS.md
├─ microstitch/
│  ├─ __init__.py
│  ├─ io.py
│  ├─ preprocessing.py
│  ├─ features.py
│  ├─ matching.py
│  ├─ pose_graph.py
│  ├─ grouping.py
│  ├─ photometric.py
│  ├─ seams.py
│  ├─ renderer.py
│  ├─ quality.py
│  └─ gui/
│     ├─ main_window.py
│     ├─ widgets.py
│     └─ theme.py
├─ tests/
│  ├─ test_transforms.py
│  ├─ test_matching.py
│  └─ test_rendering.py
└─ examples/
```

Bu refactor davranışı değiştirmeden, küçük adımlarla yapılmalıdır.

---

## 8. Test stratejisi

Her ciddi değişiklikten sonra en az şu senaryolar denenmelidir.

### Geometrik test

Sentetik görüntüden bilinen:

- translation
- rotation
- scale

üretilir ve tahmin edilen transform gerçek değerle karşılaştırılır.

### Histoloji overlap testi

Aynı H&E görüntüsünden iki kısmi crop oluşturulur.

Başarı kriterleri:

- nükleus kenarlarında çift kontur oluşmaması
- seam boyunca belirgin bulanıklık olmaması
- renk sıçramasının minimum olması

### Exposure testi

Aynı görüntünün biri daha açık biri daha koyu kopyası oluşturulur.

Stitch sonrası seam mümkün olduğunca görünmez olmalıdır.

### Black ocular test

Siyah dairesel sınır feature matching'i bozmamalı ve final mozaiğe taşınmamalıdır.

### Different magnification test

2x veya 2.5x farklı ölçekli iki grup aynı dosya setine konur.

Algoritma bunları yanlışlıkla tek homojen grup olarak harmanlamamalıdır.

---

## 9. Örnek görseller hakkında

Repo kökündeki örnek görseller kullanıcı tarafından manuel olarak güncellenebilir.

Özellikle:

- `screen.PNG`
- `sonuc.png`
- `sonuc_AI_ile.png`

AI veya otomatik geliştirme araçları bu dosyaları gerekli olmadıkça değiştirmemeli, yeniden sıkıştırmamalı veya silmemelidir.

README içindeki görsel bağlantıları korunmalıdır.

---

## 10. Performans

Çok sayıda yüksek çözünürlüklü görüntü RAM kullanımını hızla artırabilir.

Tercihler:

- feature matching için downsample
- final render için full resolution
- mümkünse tile/chunk rendering
- gereksiz image copy'lerinden kaçınma
- büyük array'leri işlem sonrası serbest bırakma
- devasa canvas'larda memory estimate gösterme

İleri aşamada OpenSlide-benzeri tile pyramid üretimi değerlendirilebilir.

---

## 11. Renk ve görüntü bütünlüğü

Histopatoloji görüntülerinde aşağıdaki işlemler varsayılan olarak **kapalı** olmalıdır:

- AI hallucination tabanlı detail enhancement
- generative super-resolution
- otomatik stain replacement
- agresif sharpening
- lokal yapı değiştiren denoise

Bunlar eklenirse kullanıcıya açıkça “görüntüyü değiştiren işlem” olarak gösterilmeli ve orijinal birleşik çıktı ayrıca saklanmalıdır.

---

## 12. Kod kalitesi

Yeni kod:

- Python 3.11+ ile uyumlu tutulmaya çalışılmalı
- type hint kullanmalı
- path işlemlerinde mümkünse `pathlib` kullanmalı
- kullanıcıya görünen hatalar anlaşılır olmalı
- uzun işlemlerde progress callback desteklemeli
- algoritma parametreleri magic number yerine ayar sınıfında tutulmalı
- UI ile stitching engine mümkün olduğunca ayrılmalı

OpenCV API farklılıkları ve Windows ortamı özellikle dikkate alınmalıdır.

---

## 13. Bağımlılık politikası

Yeni bağımlılık eklerken şu sorular sorulmalıdır:

1. Aynı iş mevcut NumPy/SciPy/OpenCV ile yapılabiliyor mu?
2. Windows'ta kolay kuruluyor mu?
3. Python'un güncel sürümlerinde wheel mevcut mu?
4. Lisansı açık kaynak dağıtıma uygun mu?
5. Programın kurulumunu gereksiz yere zorlaştırıyor mu?

Özellikle GPU zorunlu kütüphaneler varsayılan bağımlılık yapılmamalıdır.

---

## 14. GitHub katkı kuralları

Önerilen commit biçimi:

```text
Improve graph matching robustness
Fix white background normalization
Improve GUI readability
Add objective grouping diagnostics
```

Büyük değişiklikler mümkünse ayrı commit/PR halinde yapılmalıdır.

Bir algoritma değişikliği yapılırken PR açıklamasına şunlar eklenmelidir:

- ne değişti
- neden değişti
- hangi problem çözüldü
- örnek dataset üzerindeki etkisi
- registration metriği değişti mi
- renk / geometri etkisi var mı

---

## 15. Roadmap fikirleri

Katkı yapmak isteyenler için olası geliştirmeler:

- daha iyi automatic objective clustering
- sparse graph matching ile O(n²) pair matching maliyetini azaltma
- thumbnail tabanlı hızlı komşuluk tahmini
- graph loop-closure diagnostics
- lokal non-rigid correction'ın yalnızca çok kontrollü opsiyonel sürümü
- tissue-aware graph-cut cost
- Laplacian pyramid blending iyileştirmesi
- automatic focus/sharpness scoring
- blurry-frame rejection
- exposure quality warnings
- duplicate-frame detection
- WSI pyramid / tiled TIFF output
- OpenSlide uyumlu export
- zoomable Deep Zoom / web preview
- dataset/session save-load
- CLI mode
- batch processing
- unit/integration tests
- benchmark dataset

---

## 16. AI coding agent için kısa talimat

Bu repoda çalışan bir AI agent şu sırayı izlemelidir:

1. Önce `README.md` ve bu `AGENTS.md` dosyasını oku.
2. Mevcut davranışı anlamadan stitching algoritmasını baştan yazma.
3. Örnek görselleri değiştirme.
4. Geometriyi etkileyen her değişikliği registration testi ile doğrula.
5. Renk işlemlerinde H&E bütünlüğünü koru.
6. Farklı magnification gruplarını zorla birleştirme.
7. Full-resolution görüntüleri gereksiz yere tekrar tekrar resample etme.
8. Yeni özelliği mümkünse opsiyonel ve geriye uyumlu ekle.
9. GUI değişikliklerinde okunabilirliği ve Windows kullanımını test et.
10. Bir değişikliğin histolojik ayrıntıyı yapay olarak üretmesine izin verme.

---

## 17. Başarı kriteri

MicroStitch Studio'nun amacı yalnızca “panorama üretmek” değildir.

Başarılı bir çıktı:

- doku geometrisini korur,
- aynı yapıyı iki kez göstermez,
- seam'i mümkün olduğunca görünmez tutar,
- H&E rengini bozmaz,
- telefon/mikroskop aydınlatma farklarını azaltır,
- kaynak görüntünün gerçek ayrıntısını korur,
- hangi görüntülerin nasıl birleştirildiğini kalite raporuyla açıklayabilir.

Bu kriterlerden biri görsel estetik uğruna feda edilmemelidir.
