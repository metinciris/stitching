#!/usr/bin/env python3
"""
mikroskop_gui.py
------------------
mikroskop_birlestir.py'nin görsel (fare ile dosya seçilebilen) arayüzü.
Görüntüleri klasör yolu yazmadan, standart "Dosya Aç" penceresinden çoklu
seçim yaparak yükleyebilirsiniz.

Çalıştırma:
    python3 mikroskop_gui.py

Gereksinimler:
    pip install opencv-contrib-python numpy Pillow --break-system-packages
    (python3-tk sisteminizde kurulu olmalı; Linux'ta: sudo apt install python3-tk)
"""

import os
import sys
import threading
import traceback

import cv2

import mikroskop_core as core

try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:
    sys.exit("HATA: tkinter bulunamadı. Linux'ta 'sudo apt install python3-tk' ile kurabilirsiniz.")

try:
    from PIL import Image, ImageTk
    PIL_VAR = True
except ImportError:
    PIL_VAR = False


KUCUK_ONIZLEME = (110, 110)


class MikroskopArayuzu(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Mikroskop Alan Birleştirici")
        self.geometry("780x620")
        self.minsize(680, 520)

        self.secili_dosyalar = []
        self.onizleme_referanslari = []  # PhotoImage'ler GC'ye gitmesin diye

        self._arayuz_kur()

    # ------------------------------------------------------------------
    def _arayuz_kur(self):
        ust = ttk.Frame(self, padding=10)
        ust.pack(fill="x")

        ttk.Button(ust, text="📁 Fotoğraf Seç...", command=self._dosya_sec).pack(side="left")
        ttk.Button(ust, text="Temizle", command=self._temizle).pack(side="left", padx=(8, 0))
        self.sayi_etiketi = ttk.Label(ust, text="0 görüntü seçildi")
        self.sayi_etiketi.pack(side="left", padx=12)

        # Önizleme alanı (kaydırılabilir)
        onizleme_cerceve = ttk.LabelFrame(self, text="Seçilen Fotoğraflar", padding=6)
        onizleme_cerceve.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.canvas = tk.Canvas(onizleme_cerceve, borderwidth=0, highlightthickness=0)
        yscroll = ttk.Scrollbar(onizleme_cerceve, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.ic_cerceve = ttk.Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.ic_cerceve, anchor="nw")
        self.ic_cerceve.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))

        # Seçenekler
        secenek_cerceve = ttk.LabelFrame(self, text="Seçenekler", padding=8)
        secenek_cerceve.pack(fill="x", padx=10, pady=(0, 6))

        self.var_isik = tk.BooleanVar(value=True)
        self.var_vinyet = tk.BooleanVar(value=True)
        self.var_oto_grup = tk.BooleanVar(value=True)
        self.var_kenar_kirp = tk.BooleanVar(value=True)

        ttk.Checkbutton(secenek_cerceve, text="Işık/pozlama farklarını eşitle (CLAHE)",
                         variable=self.var_isik).grid(row=0, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(secenek_cerceve, text="Vinyet (kenar kararması) düzelt",
                         variable=self.var_vinyet).grid(row=1, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(secenek_cerceve, text="Farklı objektif/büyütmeleri otomatik ayır",
                         variable=self.var_oto_grup).grid(row=2, column=0, sticky="w", padx=4, pady=2)
        ttk.Checkbutton(secenek_cerceve, text="Siyah çevre kenarlığını (oküler dışı) otomatik kırp",
                         variable=self.var_kenar_kirp).grid(row=3, column=0, sticky="w", padx=4, pady=2)

        ttk.Label(secenek_cerceve, text="Eşleştirme eforu:").grid(row=0, column=1, sticky="e", padx=(20, 4))
        self.var_efor = tk.StringVar(value="normal")
        efor_secici = ttk.Combobox(secenek_cerceve, textvariable=self.var_efor, state="readonly",
                                    values=["hizli", "normal", "yuksek"], width=10)
        efor_secici.grid(row=0, column=2, sticky="w")
        ttk.Label(secenek_cerceve, text="(üst üste binmeler kaçıyorsa 'yuksek' seçin; daha yavaştır)",
                  foreground="#666").grid(row=1, column=1, columnspan=2, sticky="w", padx=(20, 0))

        # Çıktı
        cikti_cerceve = ttk.Frame(self)
        cikti_cerceve.pack(fill="x", padx=10, pady=(0, 6))
        ttk.Label(cikti_cerceve, text="Kayıt klasörü:").pack(side="left")
        self.cikti_klasoru = tk.StringVar(value=os.path.abspath("."))
        ttk.Entry(cikti_cerceve, textvariable=self.cikti_klasoru).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(cikti_cerceve, text="Seç...", command=self._klasor_sec).pack(side="left")

        # Çalıştır
        alt = ttk.Frame(self, padding=10)
        alt.pack(fill="x")
        self.birlestir_btn = ttk.Button(alt, text="▶ Birleştir", command=self._birlestir_baslat)
        self.birlestir_btn.pack(side="left")
        self.ilerleme = ttk.Progressbar(alt, mode="determinate")
        self.ilerleme.pack(side="left", fill="x", expand=True, padx=10)

        # Log
        log_cerceve = ttk.LabelFrame(self, text="Kayıt / Durum", padding=6)
        log_cerceve.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log_kutusu = tk.Text(log_cerceve, height=8, state="disabled", wrap="word")
        self.log_kutusu.pack(fill="both", expand=True)

    # ------------------------------------------------------------------
    def _log(self, mesaj):
        self.log_kutusu.configure(state="normal")
        self.log_kutusu.insert("end", mesaj + "\n")
        self.log_kutusu.see("end")
        self.log_kutusu.configure(state="disabled")
        self.update_idletasks()

    def _dosya_sec(self):
        yollar = filedialog.askopenfilenames(
            title="Birleştirilecek fotoğrafları seçin",
            filetypes=[("Görüntü dosyaları", "*.jpg *.jpeg *.png *.JPG *.JPEG *.PNG"), ("Tüm dosyalar", "*.*")],
        )
        if not yollar:
            return
        for y in yollar:
            if y not in self.secili_dosyalar:
                self.secili_dosyalar.append(y)
        self._onizlemeleri_yenile()

    def _temizle(self):
        self.secili_dosyalar = []
        self._onizlemeleri_yenile()

    def _klasor_sec(self):
        klasor = filedialog.askdirectory(title="Kayıt klasörünü seçin")
        if klasor:
            self.cikti_klasoru.set(klasor)

    def _onizlemeleri_yenile(self):
        for w in self.ic_cerceve.winfo_children():
            w.destroy()
        self.onizleme_referanslari.clear()

        self.sayi_etiketi.configure(text=f"{len(self.secili_dosyalar)} görüntü seçildi")

        sutun = 0
        satir = 0
        maks_sutun = 5
        for yol in self.secili_dosyalar:
            hucre = ttk.Frame(self.ic_cerceve, padding=4)
            hucre.grid(row=satir, column=sutun, sticky="n")

            if PIL_VAR:
                try:
                    im = Image.open(yol)
                    im.thumbnail(KUCUK_ONIZLEME)
                    foto = ImageTk.PhotoImage(im)
                    self.onizleme_referanslari.append(foto)
                    ttk.Label(hucre, image=foto).pack()
                except Exception:
                    ttk.Label(hucre, text="[önizleme yok]").pack()
            else:
                ttk.Label(hucre, text="[Pillow yok]").pack()

            ttk.Label(hucre, text=os.path.basename(yol), wraplength=110, justify="center").pack()
            sutun += 1
            if sutun >= maks_sutun:
                sutun = 0
                satir += 1

    # ------------------------------------------------------------------
    def _birlestir_baslat(self):
        if len(self.secili_dosyalar) < 2:
            messagebox.showwarning("Eksik seçim", "En az 2 fotoğraf seçmelisiniz.")
            return
        self.birlestir_btn.configure(state="disabled")
        self.ilerleme.configure(value=0, maximum=100)
        threading.Thread(target=self._birlestir_calistir, daemon=True).start()

    def _ilerleme_guncelle(self, yapilan, toplam):
        yuzde = 0 if toplam == 0 else int(100 * yapilan / toplam)
        self.after(0, lambda: self.ilerleme.configure(value=yuzde))

    def _birlestir_calistir(self):
        try:
            self._log(f"{len(self.secili_dosyalar)} görüntü yükleniyor...")
            imgs, gecerli_yollar = core.dosyalari_yukle(self.secili_dosyalar)
            if len(imgs) < 2:
                self._log("HATA: Yeterli sayıda okunabilir görüntü yok.")
                return

            if self.var_kenar_kirp.get():
                onceki = [im.shape[:2] for im in imgs]
                imgs = [core.daire_alanini_kirp(im) for im in imgs]
                kirpilan = sum(1 for once, im in zip(onceki, imgs) if im.shape[:2] != once)
                if kirpilan:
                    self._log(f"Siyah çevre kenarlığı {kirpilan}/{len(imgs)} görüntüde otomatik kırpıldı.")

            if self.var_isik.get() or self.var_vinyet.get():
                imgs = [core.on_isle(im, vinyet=self.var_vinyet.get(), isik=self.var_isik.get()) for im in imgs]
                self._log("Ön işleme (ışık/vinyet) uygulandı.")

            efor = self.var_efor.get()
            if self.var_oto_grup.get():
                self._log(f"Farklı objektif/büyütme grupları aranıyor (efor={efor}, biraz sürebilir)...")
                gruplar, oran_tablosu = core.objektif_gruplarini_bul(
                    imgs, efor=efor, ilerleme_callback=self._ilerleme_guncelle)
                if len(gruplar) == 1:
                    self._log("Tüm görüntüler aynı büyütmede görünüyor -> tek kompozit üretilecek.")
                else:
                    self._log(f"{len(gruplar)} farklı büyütme grubu tespit edildi:")
                    for gi, grup in enumerate(gruplar, 1):
                        isimler = ", ".join(os.path.basename(gecerli_yollar[i]) for i in grup)
                        self._log(f"  Grup {gi} ({len(grup)} görüntü): {isimler}")
            else:
                gruplar = [list(range(len(imgs)))]

            self.ilerleme.configure(value=0)
            cikti_klasor = self.cikti_klasoru.get() or "."
            os.makedirs(cikti_klasor, exist_ok=True)
            tek_grup_var = len(gruplar) == 1
            uretilen_dosyalar = []

            for gi, grup in enumerate(gruplar, 1):
                grup_imgs = [imgs[i] for i in grup]
                if len(grup_imgs) == 1:
                    ad = "sonuc.png" if tek_grup_var else f"sonuc_grup{gi}_tek.png"
                    yol = os.path.join(cikti_klasor, ad)
                    cv2.imwrite(yol, grup_imgs[0])
                    self._log(f"[Grup {gi}] Tek görüntü (eşleşme bulunamadı) -> {yol}")
                    uretilen_dosyalar.append(yol)
                    continue

                self._log(f"[Grup {gi}] Birleştiriliyor ({len(grup_imgs)} görüntü)...")
                sonuc, yontem = core.grup_birlestir(grup_imgs, efor=efor)
                ad = "sonuc.png" if tek_grup_var else f"sonuc_grup{gi}.png"
                yol = os.path.join(cikti_klasor, ad)
                cv2.imwrite(yol, sonuc)
                self._log(f"[Grup {gi}] Yöntem: {yontem} -> {yol} ({sonuc.shape[1]}x{sonuc.shape[0]})")
                uretilen_dosyalar.append(yol)
                self.ilerleme.configure(value=int(100 * gi / len(gruplar)))

            self._log("Tamamlandı.")
            self.after(0, lambda: messagebox.showinfo(
                "Tamamlandı", "Oluşturulan dosyalar:\n" + "\n".join(uretilen_dosyalar)))
        except Exception as e:
            self._log("HATA: " + str(e))
            self._log(traceback.format_exc())
        finally:
            self.after(0, lambda: self.birlestir_btn.configure(state="normal"))


def main():
    # Otomatik test modu: pencereyi kurup hemen kapatır (CI/self-test amaçlı)
    self_test = "--self-test" in sys.argv
    app = MikroskopArayuzu()

    if "--onizle" in sys.argv:
        idx = sys.argv.index("--onizle")
        app.secili_dosyalar = sys.argv[idx + 1:]
        app._onizlemeleri_yenile()

    if self_test:
        app.after(600, app.destroy)
    app.mainloop()


if __name__ == "__main__":
    main()
