"""
mikroskop_core.py
------------------
CLI ve GUI'nin ortak kullandığı çekirdek fonksiyonlar:
  - ön işleme (ışık eşitleme / vinyet düzeltme)
  - stitching (hazır cv2.Stitcher + manuel afin/feather yedek yöntem)
  - farklı objektiflerden (büyütmelerden) gelen görüntüleri otomatik ayırma
"""

import glob
import os

import cv2
import numpy as np


# --------------------------------------------------------------------------
# ÖN İŞLEME
# --------------------------------------------------------------------------
def isik_esitle(img, clahe_clip=2.0, clahe_grid=8):
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=clahe_clip, tileGridSize=(clahe_grid, clahe_grid))
    l2 = clahe.apply(l)
    lab2 = cv2.merge((l2, a, b))
    return cv2.cvtColor(lab2, cv2.COLOR_LAB2BGR)


def vinyet_duzelt(img, blur_ksize=None):
    h, w = img.shape[:2]
    if blur_ksize is None:
        blur_ksize = (w // 2) | 1
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    flat = cv2.GaussianBlur(gray, (blur_ksize, blur_ksize), 0)
    flat = np.clip(flat, 10, 255)
    gain = np.mean(flat) / flat
    gain = np.clip(gain, 0.7, 1.6)
    out = img.astype(np.float32) * gain[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def on_isle(img, vinyet=True, isik=True):
    out = img.copy()
    if vinyet:
        out = vinyet_duzelt(out)
    if isik:
        out = isik_esitle(out)
    return out


# --------------------------------------------------------------------------
# YÖNTEM A: cv2.Stitcher (SCANS = afin/düzlemsel, PANORAMA = perspektif)
# --------------------------------------------------------------------------
def opencv_stitcher_ile_birlestir(images, mod="SCANS", efor="normal"):
    mode = cv2.Stitcher_SCANS if mod == "SCANS" else cv2.Stitcher_PANORAMA
    stitcher = cv2.Stitcher_create(mode)
    # Güven eşiğini düşürmek, zayıf örtüşen çiftlerde de birleştirmeyi kabul
    # etmesini sağlar (varsayılan ~1.0 oldukça katıdır).
    guven_esigi = {"hizli": 1.0, "normal": 0.6, "yuksek": 0.3}[efor]
    try:
        stitcher.setPanoConfidenceThresh(guven_esigi)
    except AttributeError:
        pass
    status, pano = stitcher.stitch(images)
    return status, pano


# --------------------------------------------------------------------------
# ÖZELLİK EŞLEŞTİRME (hem stitching hem büyütme/ölçek tespiti için ortak)
# --------------------------------------------------------------------------
# Efor seviyesine göre ayarlar: daha yüksek efor = daha büyük görüntü, daha
# fazla/daha hassas özellik noktası, daha gevşek eşikler -> zayıf örtüşen /
# düşük kontrastlı (doku) alanlarda daha fazla gerçek eşleşme yakalar,
# ama daha yavaştır.
EFOR_AYARLARI = {
    "hizli":  dict(max_boyut=500,  min_inlier=10, oran_esik=0.70, ransac_esik=3.0,
                    on_clahe=False, ikinci_deneme=False,
                    sift=dict(nfeatures=0, contrastThreshold=0.04, edgeThreshold=10, nOctaveLayers=3)),
    "normal": dict(max_boyut=900,  min_inlier=8,  oran_esik=0.75, ransac_esik=4.0,
                    on_clahe=True,  ikinci_deneme=False,
                    sift=dict(nfeatures=0, contrastThreshold=0.03, edgeThreshold=12, nOctaveLayers=3)),
    "yuksek": dict(max_boyut=1600, min_inlier=6,  oran_esik=0.80, ransac_esik=5.0,
                    on_clahe=True,  ikinci_deneme=True,
                    sift=dict(nfeatures=0, contrastThreshold=0.015, edgeThreshold=18, nOctaveLayers=4)),
}


def varsayilan_detector(efor="normal", tip="sift"):
    if tip == "orb":
        nfeat = {"hizli": 1500, "normal": 4000, "yuksek": 8000}[efor]
        return cv2.ORB_create(nfeat)
    if hasattr(cv2, "SIFT_create"):
        return cv2.SIFT_create(**EFOR_AYARLARI[efor]["sift"])
    return cv2.ORB_create({"hizli": 1500, "normal": 4000, "yuksek": 8000}[efor])


def _tespit_gorseli_hazirla(img, on_clahe):
    """Özellik tespiti için gri tona çevirir; on_clahe=True ise düşük
    kontrastlı doku alanlarında daha fazla köşe/nokta ortaya çıkarmak için
    kontrastı yerel olarak artırır (yalnızca tespit için, çıktı görüntüsünü
    etkilemez)."""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if on_clahe:
        g = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8)).apply(g)
    return g


def ozellik_bul_eslesir(img1, img2, detector, oran_esik=0.75, min_eslesme=8, on_clahe=False):
    g1 = _tespit_gorseli_hazirla(img1, on_clahe)
    g2 = _tespit_gorseli_hazirla(img2, on_clahe)
    kp1, des1 = detector.detectAndCompute(g1, None)
    kp2, des2 = detector.detectAndCompute(g2, None)
    if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
        return None

    norm = cv2.NORM_HAMMING if des1.dtype == np.uint8 else cv2.NORM_L2
    matcher = cv2.BFMatcher(norm)
    raw_matches = matcher.knnMatch(des1, des2, k=2)
    good = []
    for m_n in raw_matches:
        if len(m_n) != 2:
            continue
        m, n = m_n
        if m.distance < oran_esik * n.distance:
            good.append(m)
    if len(good) < min_eslesme:
        return None

    pts1 = np.float32([kp1[m.queryIdx].pt for m in good])
    pts2 = np.float32([kp2[m.trainIdx].pt for m in good])
    return pts1, pts2


def canvas_uzerine_harmanla(canvas, canvas_mask, warped, warped_mask):
    overlap = (canvas_mask > 0) & (warped_mask > 0)
    only_new = (warped_mask > 0) & (canvas_mask == 0)
    canvas[only_new] = warped[only_new]

    if np.any(overlap):
        dist_c = cv2.distanceTransform((canvas_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        dist_w = cv2.distanceTransform((warped_mask > 0).astype(np.uint8), cv2.DIST_L2, 5)
        with np.errstate(divide="ignore", invalid="ignore"):
            alpha = dist_w / (dist_c + dist_w + 1e-6)
        alpha3 = np.dstack([alpha] * 3)
        blended = canvas.astype(np.float32) * (1 - alpha3) + warped.astype(np.float32) * alpha3
        canvas[overlap] = blended[overlap].astype(np.uint8)

    return canvas, (canvas_mask > 0) | (warped_mask > 0)


# --------------------------------------------------------------------------
# YÖNTEM B: Manuel özellik-tabanlı GRAF birleştirme + feather blending
# --------------------------------------------------------------------------
# NOT: Görüntüler her zaman tek sıralı bir zincir (1-2-3-4-5) gibi örtüşmez;
# 2 boyutlu bir grid halinde çekilmiş fotoğraflarda (örn. sağ-üst ile sol-alt)
# ardışık olmayan çiftler hiç örtüşmeyebilir. Bu yüzden ÖNCE tüm ikili
# eşleşmeler bulunur, SONRA en güvenilir (en çok inlier'lı) bağlantılardan bir
# "maksimum yayılma ağacı" kurulur ve her görüntünün global konumu bu ağaç
# üzerinden (kökten BFS ile) hesaplanır. Bu, cv2.Stitcher'ın içeride yaptığı
# eşleşme-grafiği yaklaşımının basitleştirilmiş bir versiyonudur.
def _afin_uygula(pts, M):
    pts_h = np.hstack([pts, np.ones((pts.shape[0], 1), dtype=np.float32)])
    return (M.astype(np.float32) @ pts_h.T).T


def _ikili_kenarlari_bul(images, sift_det, orb_det, ayar):
    n = len(images)
    min_esl = min(8, ayar["min_inlier"])
    kenarlar = []
    for i in range(n):
        for j in range(i + 1, n):
            eslesme = ozellik_bul_eslesir(images[i], images[j], sift_det,
                                           oran_esik=ayar["oran_esik"], min_eslesme=min_esl,
                                           on_clahe=ayar["on_clahe"])
            if eslesme is None and orb_det is not None:
                eslesme = ozellik_bul_eslesir(images[i], images[j], orb_det,
                                               oran_esik=ayar["oran_esik"], min_eslesme=min_esl,
                                               on_clahe=ayar["on_clahe"])
            if eslesme is None:
                continue
            pts_i, pts_j = eslesme
            M, inliers = cv2.estimateAffinePartial2D(pts_j, pts_i, method=cv2.RANSAC,
                                                       ransacReprojThreshold=ayar["ransac_esik"])
            if M is None:
                continue
            inlier_sayisi = int(inliers.sum()) if inliers is not None else len(pts_i)
            if inlier_sayisi < ayar["min_inlier"]:
                continue
            kenarlar.append((i, j, M, inlier_sayisi))  # M: j koordinatlarını i'ye taşır
    return kenarlar


def manuel_birlestir(images, detector=None, efor="normal", ilerleme_callback=None):
    ayar = EFOR_AYARLARI[efor]
    sift_det = detector or varsayilan_detector(efor, tip="sift")
    orb_det = varsayilan_detector(efor, tip="orb") if ayar["ikinci_deneme"] else None
    n = len(images)

    kenarlar = _ikili_kenarlari_bul(images, sift_det, orb_det, ayar)
    if ilerleme_callback:
        ilerleme_callback(1, 1)

    if not kenarlar:
        # Hiçbir çift eşleşmedi; elden bir şey gelmez, en büyük görüntüyü döndür
        return max(images, key=lambda im: im.shape[0] * im.shape[1])

    # Maksimum yayılma ağacı: en güvenilir (en çok inlier'lı) bağlantılar önce
    uf = _BirlesikKume(n)
    agac = []
    for (i, j, M, inl) in sorted(kenarlar, key=lambda e: -e[3]):
        if uf.bul(i) != uf.bul(j):
            uf.birlestir(i, j)
            agac.append((i, j, M, inl))

    derece = {}
    for (i, j, _, _) in agac:
        derece[i] = derece.get(i, 0) + 1
        derece[j] = derece.get(j, 0) + 1
    kok = max(derece, key=derece.get) if derece else 0

    komsu = {}
    for (i, j, M, inl) in agac:
        komsu.setdefault(i, []).append((j, cv2.invertAffineTransform(M)))  # i -> j
        komsu.setdefault(j, []).append((i, M))                             # j -> i

    from collections import deque
    global_M = {kok: np.array([[1, 0, 0], [0, 1, 0]], dtype=np.float32)}
    ziyaret = {kok}
    kuyruk = deque([kok])
    while kuyruk:
        node = kuyruk.popleft()
        for kom, M_kom_to_node in komsu.get(node, []):
            if kom in ziyaret:
                continue
            ziyaret.add(kom)
            G_node_3 = np.vstack([global_M[node], [0, 0, 1]]).astype(np.float32)
            M_3 = np.vstack([M_kom_to_node, [0, 0, 1]]).astype(np.float32)
            global_M[kom] = (G_node_3 @ M_3)[:2, :]
            kuyruk.append(kom)

    izole = [k for k in range(n) if k not in ziyaret]
    if izole:
        print(f"[UYARI] {len(izole)} görüntü diğerleriyle eşleştirilemedi, "
              f"kompozite dahil edilemedi (indeksler: {izole}).")

    # Tuval boyutunu tüm dönüştürülmüş köşe noktalarına göre hesapla
    tum_kose = []
    for idx in ziyaret:
        h, w = images[idx].shape[:2]
        koseler = np.array([[0, 0], [w, 0], [w, h], [0, h]], dtype=np.float32)
        tum_kose.append(_afin_uygula(koseler, global_M[idx]))
    tum_kose = np.vstack(tum_kose)
    min_x, min_y = tum_kose.min(axis=0)
    max_x, max_y = tum_kose.max(axis=0)

    kaydir = np.array([[1, 0, -min_x], [0, 1, -min_y]], dtype=np.float32)
    canvas_w = max(1, int(np.ceil(max_x - min_x)) + 2)
    canvas_h = max(1, int(np.ceil(max_y - min_y)) + 2)

    # Aşırı büyük tuvali (kaçak/aykırı dönüşüm durumunda) sınırla
    if canvas_w * canvas_h > 8000 * 8000:
        print("[UYARI] Hesaplanan tuval anormal büyük, en büyük tekil görüntü döndürülüyor.")
        return max(images, key=lambda im: im.shape[0] * im.shape[1])

    canvas = np.zeros((canvas_h, canvas_w, 3), dtype=np.uint8)
    canvas_mask = np.zeros((canvas_h, canvas_w), dtype=np.uint8)

    # Kök en güvenilir referans olduğu için önce o yerleştirilir
    sira = [kok] + [k for k in ziyaret if k != kok]
    for idx in sira:
        h, w = images[idx].shape[:2]
        M3 = np.vstack([global_M[idx], [0, 0, 1]]).astype(np.float32)
        kaydir_3 = np.vstack([kaydir, [0, 0, 1]]).astype(np.float32)
        M_final = (kaydir_3 @ M3)[:2, :]
        warped = cv2.warpAffine(images[idx], M_final, (canvas_w, canvas_h))
        warped_mask = cv2.warpAffine(np.full((h, w), 255, dtype=np.uint8), M_final, (canvas_w, canvas_h))
        canvas, canvas_mask_bool = canvas_uzerine_harmanla(canvas, canvas_mask, warped, warped_mask)
        canvas_mask = canvas_mask_bool.astype(np.uint8) * 255

    ys, xs = np.where(canvas_mask > 0)
    if len(xs) == 0:
        return canvas
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    return canvas[y0:y1 + 1, x0:x1 + 1]


# --------------------------------------------------------------------------
# FARKLI OBJEKTİF / BÜYÜTME TESPİTİ
# --------------------------------------------------------------------------
def _kucult(img, max_boyut=600):
    h, w = img.shape[:2]
    olcek = max_boyut / max(h, w)
    if olcek < 1:
        return cv2.resize(img, (int(w * olcek), int(h * olcek)), interpolation=cv2.INTER_AREA), olcek
    return img, 1.0


def gorece_olcek_tahmin_et(img_i, img_j, detector, min_inlier=8, max_boyut=600,
                            oran_esik=0.75, ransac_esik=4.0, on_clahe=False):
    """img_j -> img_i eşleşmesinden GERÇEK (orijinal çözünürlükte) ölçek
    oranını tahmin eder. SIFT ölçekten bağımsız çalıştığı için farklı
    büyütmelerdeki (objektiflerdeki) görüntüler arasında da eşleşme
    bulabilir; dönen oran 1'den ne kadar uzaksa büyütme farkı o kadar fazladır.
    Dönüş: (oran, inlier_sayisi) ya da (None, 0)."""
    small_i, s_i = _kucult(img_i, max_boyut)
    small_j, s_j = _kucult(img_j, max_boyut)
    eslesme = ozellik_bul_eslesir(small_i, small_j, detector, oran_esik=oran_esik,
                                   min_eslesme=min(8, min_inlier), on_clahe=on_clahe)
    if eslesme is None:
        return None, 0
    pts_i, pts_j = eslesme
    M, inliers = cv2.estimateAffinePartial2D(pts_j, pts_i, method=cv2.RANSAC, ransacReprojThreshold=ransac_esik)
    if M is None:
        return None, 0
    inlier_sayisi = int(inliers.sum()) if inliers is not None else len(pts_i)
    if inlier_sayisi < min_inlier:
        return None, 0
    m = float(np.hypot(M[0, 0], M[1, 0]))  # küçültülmüş görüntüler arası ölçek
    gercek_oran = m * (s_j / s_i)          # orijinal çözünürlüğe geri taşı
    return gercek_oran, inlier_sayisi


class _BirlesikKume:
    """Union-Find: aynı büyütme grubuna giren görüntüleri kümelemek için."""

    def __init__(self, n):
        self.parent = list(range(n))

    def bul(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def birlestir(self, a, b):
        ra, rb = self.bul(a), self.bul(b)
        if ra != rb:
            self.parent[ra] = rb


def objektif_gruplarini_bul(images, tol_dusuk=0.8, tol_yuksek=1.25, efor="normal",
                             ilerleme_callback=None):
    """Görüntüleri, birbirine göre ~aynı ölçekte (aynı objektif/büyütme)
    olanları aynı grupta toplayacak şekilde otomatik kümeler.

    tol_dusuk / tol_yuksek: iki görüntü arasındaki ölçüşülen ölçek oranı bu
    aralıktaysa "aynı büyütme" kabul edilir. Patoloji objektiflerinde
    ardışık büyütme adımları (4x->10x, 10x->20x, 20x->40x) genelde >=2x
    ölçek farkı yarattığından varsayılan 0.8-1.25 aralığı güvenli bir eşiktir.

    efor: "hizli" | "normal" | "yuksek". Yüksek efor; daha büyük çözünürlükte
    eşleştirme, kontrast artırma (CLAHE) ve SIFT başarısız olursa ORB ile
    ikinci deneme yapar -> zayıf örtüşen/düşük kontrastlı gerçek fotoğraflarda
    gereksiz grup bölünmesini azaltır, ama daha uzun sürer.

    Dönüş: (gruplar, oran_tablosu)
        gruplar: [[idx, idx, ...], ...]  -- her biri bir büyütme grubunun indeksleri
        oran_tablosu: {(i,j): (oran, inlier_sayisi)} -- teşhis/loglama için
    """
    n = len(images)
    ayar = EFOR_AYARLARI[efor]
    sift_det = varsayilan_detector(efor, tip="sift")
    orb_det = varsayilan_detector(efor, tip="orb") if ayar["ikinci_deneme"] else None

    uf = _BirlesikKume(n)
    oran_tablosu = {}

    toplam = n * (n - 1) // 2
    yapilan = 0
    for i in range(n):
        for j in range(i + 1, n):
            oran, inlier = gorece_olcek_tahmin_et(
                images[i], images[j], sift_det, min_inlier=ayar["min_inlier"],
                max_boyut=ayar["max_boyut"], oran_esik=ayar["oran_esik"],
                ransac_esik=ayar["ransac_esik"], on_clahe=ayar["on_clahe"])
            if oran is None and orb_det is not None:
                oran, inlier = gorece_olcek_tahmin_et(
                    images[i], images[j], orb_det, min_inlier=ayar["min_inlier"],
                    max_boyut=ayar["max_boyut"], oran_esik=ayar["oran_esik"],
                    ransac_esik=ayar["ransac_esik"], on_clahe=ayar["on_clahe"])
            yapilan += 1
            if ilerleme_callback:
                ilerleme_callback(yapilan, toplam)
            if oran is None:
                continue
            oran_tablosu[(i, j)] = (oran, inlier)
            if tol_dusuk <= oran <= tol_yuksek:
                uf.birlestir(i, j)

    gruplar_dict = {}
    for i in range(n):
        k = uf.bul(i)
        gruplar_dict.setdefault(k, []).append(i)

    # Büyük gruptan küçüğe sırala (en çok görüntü içeren grup önce)
    gruplar = sorted(gruplar_dict.values(), key=len, reverse=True)
    return gruplar, oran_tablosu


# --------------------------------------------------------------------------
# DOSYA YÜKLEME
# --------------------------------------------------------------------------
DESTEKLENEN_UZANTILAR = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")


def klasorden_dosya_listele(klasor):
    yollar = []
    for desen in DESTEKLENEN_UZANTILAR:
        yollar.extend(glob.glob(os.path.join(klasor, desen)))
    return sorted(set(yollar))


def dosyalari_yukle(yollar):
    imgs, gecerli_yollar = [], []
    for y in yollar:
        im = cv2.imread(y)
        if im is None:
            print(f"[UYARI] okunamadı: {y}")
            continue
        imgs.append(im)
        gecerli_yollar.append(y)
    return imgs, gecerli_yollar


# --------------------------------------------------------------------------
# TEK BİR GRUP İÇİN TAM BİRLEŞTİRME AKIŞI (opencv -> başarısızsa manuel)
# --------------------------------------------------------------------------
def grup_birlestir(images, stitcher_modu="SCANS", efor="normal"):
    """Bir büyütme grubundaki görüntüleri birleştirir.
    Dönüş: (sonuc_img, yontem_str)

    NOT: cv2.Stitcher bazen -hatasız görünse de- örtüşmeyen/zayıf eşleşen
    görüntüleri sessizce dışarıda bırakabilir (çıktı, verilenden daha küçük
    olur). 'yuksek' eforda bu durum tespit edilip, tüm görüntüleri kapsayan
    graf-tabanlı manuel yöntemle karşılaştırılarak daha eksiksiz olan seçilir.
    """
    if len(images) == 1:
        return images[0], "tek-goruntu"

    status, pano_cv = opencv_stitcher_ile_birlestir(images, mod=stitcher_modu, efor=efor)
    cv_basarili = status == cv2.Stitcher_OK
    cv_alan = (pano_cv.shape[0] * pano_cv.shape[1]) if cv_basarili else 0

    if cv_basarili and efor != "yuksek":
        return pano_cv, "opencv-stitcher"

    sonuc_manuel = manuel_birlestir(images, efor=efor)
    manuel_alan = sonuc_manuel.shape[0] * sonuc_manuel.shape[1]

    # Girdi görüntülerin toplam alanına göre, çok daha küçük bir sonuç
    # muhtemelen bazı görüntülerin atlandığının işaretidir.
    if cv_basarili and cv_alan >= manuel_alan * 0.85:
        return pano_cv, "opencv-stitcher"
    return sonuc_manuel, "manuel(graf)"
