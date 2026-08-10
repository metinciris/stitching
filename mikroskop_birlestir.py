#!/usr/bin/env python3
"""
mikroskop_birlestir.py (CLI)
-----------------------------
Telefonla oküler üzerinden farklı alanlardan çekilmiş fotoğrafları tek bir
kompozit görüntüde birleştirir (Microsoft Image Composite Editor benzeri).
Görüntüler arasında farklı OBJEKTİF/BÜYÜTME varsa bunları otomatik ayırt
edip her büyütme için ayrı bir kompozit üretir.

Görsel (fare ile tıklayarak) dosya seçmek isterseniz: mikroskop_gui.py

Kullanım:
    python3 mikroskop_birlestir.py --girdi ./fotograflar --cikti sonuc.png

    # Belirli dosyaları elle listelemek isterseniz:
    python3 mikroskop_birlestir.py --dosyalar a.jpg b.jpg c.jpg --cikti sonuc.png

    # Farklı büyütmeleri otomatik ayırmadan hepsini tek grupta zorlamak için:
    python3 mikroskop_birlestir.py --girdi ./fotograflar --tek-grup

Gereksinimler:
    pip install opencv-contrib-python numpy --break-system-packages
"""

import argparse
import os
import sys

import cv2

import mikroskop_core as core


def gorseleri_yukle(args):
    if args.dosyalar:
        yollar = args.dosyalar
    elif args.girdi:
        yollar = core.klasorden_dosya_listele(args.girdi)
        if not yollar:
            sys.exit(f"HATA: '{args.girdi}' klasöründe görüntü bulunamadı.")
    else:
        sys.exit("HATA: --girdi (klasör) veya --dosyalar (dosya listesi) belirtmelisiniz.")

    imgs, gecerli_yollar = core.dosyalari_yukle(yollar)
    if not imgs:
        sys.exit("HATA: Hiçbir görüntü okunamadı.")
    return imgs, gecerli_yollar


def main():
    ap = argparse.ArgumentParser(description="Oküler/telefon alan fotoğraflarını tek görüntüde birleştir")
    kaynak = ap.add_mutually_exclusive_group()
    kaynak.add_argument("--girdi", help="Fotoğrafların olduğu klasör")
    kaynak.add_argument("--dosyalar", nargs="+", help="Birleştirilecek dosyaların tam listesi")

    ap.add_argument("--cikti", default="sonuc.png", help="Çıktı dosya adı (tabanı)")
    ap.add_argument("--stitcher-modu", choices=["SCANS", "PANORAMA"], default="SCANS",
                     help="cv2.Stitcher için: SCANS=afin/düzlemsel (önerilen), PANORAMA=perspektif")
    ap.add_argument("--vinyet-duzelt", action="store_true", help="Kenar kararmasını (vinyet) düzelt")
    ap.add_argument("--isik-esitle", action="store_true", help="CLAHE ile pozlama farklarını dengele")
    ap.add_argument("--kenar-kirp-kapat", action="store_true",
                     help="Oküler fotoğraflarındaki siyah çevre kenarlığını otomatik kırpmayı kapat "
                          "(varsayılan: açık -- siyah kenarlık yoksa zaten neredeyse hiçbir şey kırpmaz)")

    ap.add_argument("--tek-grup", action="store_true",
                     help="Farklı objektif/büyütme tespitini kapat, tüm görüntüleri tek grup say")
    ap.add_argument("--olcek-tolerans-dusuk", type=float, default=0.8,
                     help="Aynı büyütme kabul edilecek alt ölçek sınırı (varsayılan 0.8)")
    ap.add_argument("--olcek-tolerans-yuksek", type=float, default=1.25,
                     help="Aynı büyütme kabul edilecek üst ölçek sınırı (varsayılan 1.25)")
    ap.add_argument("--efor", choices=["hizli", "normal", "yuksek"], default="normal",
                     help="Eşleştirme titizliği. 'yuksek': daha büyük çözünürlükte eşleştirme + "
                          "kontrast artırma + gevşek eşikler -> zayıf örtüşen/düşük kontrastlı "
                          "gerçek fotoğraflarda gereksiz grup bölünmesini azaltır ama yavaştır.")
    args = ap.parse_args()

    imgs, yollar = gorseleri_yukle(args)
    print(f"{len(imgs)} görüntü yüklendi: " + ", ".join(os.path.basename(y) for y in yollar))

    if not args.kenar_kirp_kapat:
        onceki_boyutlar = [im.shape[:2] for im in imgs]
        imgs = [core.daire_alanini_kirp(im) for im in imgs]
        kirpilan = sum(1 for once, im in zip(onceki_boyutlar, imgs) if im.shape[:2] != once)
        if kirpilan:
            print(f"Siyah çevre kenarlığı {kirpilan}/{len(imgs)} görüntüde otomatik kırpıldı.")

    if args.vinyet_duzelt or args.isik_esitle:
        imgs = [core.on_isle(im, vinyet=args.vinyet_duzelt, isik=args.isik_esitle) for im in imgs]
        print("Ön işleme (vinyet/ışık eşitleme) uygulandı.")

    if args.tek_grup:
        gruplar = [list(range(len(imgs)))]
    else:
        print(f"Farklı objektif/büyütme grupları tespit ediliyor (efor={args.efor})...")
        gruplar, oran_tablosu = core.objektif_gruplarini_bul(
            imgs, tol_dusuk=args.olcek_tolerans_dusuk, tol_yuksek=args.olcek_tolerans_yuksek,
            efor=args.efor)

        if len(gruplar) == 1:
            print("Tüm görüntüler aynı büyütme/objektife ait görünüyor -> tek kompozit üretilecek.")
        else:
            print(f"{len(gruplar)} farklı büyütme/objektif grubu tespit edildi:")
            for gi, grup in enumerate(gruplar, 1):
                dosyalar = [os.path.basename(yollar[i]) for i in grup]
                print(f"  Grup {gi} ({len(grup)} görüntü): {', '.join(dosyalar)}")
            # Teşhis amaçlı: gruplar arası ölçüşülen ortalama oran varsa göster
            for (i, j), (oran, inlier) in oran_tablosu.items():
                if not (args.olcek_tolerans_dusuk <= oran <= args.olcek_tolerans_yuksek):
                    print(f"    [bilgi] {os.path.basename(yollar[i])} <-> {os.path.basename(yollar[j])}: "
                          f"~{oran:.2f}x ölçek farkı ({inlier} eşleşme)")

    taban, uzanti = os.path.splitext(args.cikti)
    tek_grup_var = len(gruplar) == 1

    for gi, grup in enumerate(gruplar, 1):
        grup_imgs = [imgs[i] for i in grup]
        if len(grup_imgs) == 1:
            cikti_adi = args.cikti if tek_grup_var else f"{taban}_grup{gi}_tek{uzanti}"
            cv2.imwrite(cikti_adi, grup_imgs[0])
            print(f"[Grup {gi}] Tek görüntü, eşleşme bulunamadığı için olduğu gibi kaydedildi: {cikti_adi}")
            continue

        sonuc, yontem = core.grup_birlestir(grup_imgs, stitcher_modu=args.stitcher_modu, efor=args.efor)
        cikti_adi = args.cikti if tek_grup_var else f"{taban}_grup{gi}{uzanti}"
        cv2.imwrite(cikti_adi, sonuc)
        print(f"[Grup {gi}] Birleştirme yöntemi: {yontem} -> {cikti_adi} "
              f"({sonuc.shape[1]}x{sonuc.shape[0]})")


if __name__ == "__main__":
    main()
