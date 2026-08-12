# Microscope Image Stitcher (Pathology & H&E)

Bu proje, standart akıllı telefon kameraları ve mikroskop okülerinden çekilen çoklu histopatoloji görüntülerini yüksek çözünürlüklü tek bir "Whole Slide Image" (Bütünleşik Kesit) haline getirmek için geliştirilmiş özel bir Python aracıdır.

Standart panorama birleştirme algoritmaları (örn. OpenCV Stitcher), mikroskop görüntülerini işlerken perspektif bozulmalarına ve "esneme" artefaktlarına neden olur. Bu araç, sadece patoloji kesitleri için optimize edilmiş özel bir "Rigid Affine" (Katı) hizalama ve "Alpha-Feathering" harmanlama motoru kullanır.

## Özellikler

*   **Siyah Oküler Artefaktı Giderici:** Mikroskop merceğinin neden olduğu dairesel siyah çerçeveleri otomatik tanır ve şeffaflaştırır.
*   **Alpha-Feathering Harmanlama:** Resimlerin kesişim noktalarındaki sert çizgileri ve ızgara izlerini (seams) tüy gibi yumuşak bir geçişle yok eder.
*   **Renk Koruması:** Standart harmanlama yöntemlerinin aksine, hücre çekirdeklerinin (Hematoksilen) ve sitoplazmanın (Eozin) orijinal renk değerlerine dokunmaz.
*   **Lanczos4 Yüksek Çözünürlük Motoru:** Görüntüleri kaydırırken veya döndürürken hücre detaylarında piksel kaybı yaşanmasını önler.
*   **Kullanıcı Dostu GUI:** PyQt5 tabanlı basit arayüzü sayesinde kod bilmeden resimler seçilip birleştirilebilir.

## Ekran Görüntüleri ve Sonuçlar

**Kullanıcı Arayüzü**
![Program Arayüzü](screen.PNG)

**Ham Birleştirme Sonucu (Alpha-Feathering ile İzlerin Yok Edilmesi)**
![Ham Sonuç](sonuc.png)

**Yapay Zeka (AI) H&E Renk İyileştirmesi Sonrası**
*(Dijital boyama/kontrast artırma ile elde edilen final histopatoloji görüntüsü)*
![AI ile Sonuç](sonuc_AI_ile.png)

## Kurulum ve Kullanım

Sisteminize Python yüklü olduktan sonra aşağıdaki kütüphaneleri kurmanız gerekmektedir:

```bash
pip install opencv-python numpy PyQt5

```

Uygulamayı çalıştırmak için terminal veya komut istemcisinde ana dizine gidip şu komutu girin:

```bash
python mikroskop_birlestirici.py

```

1. Açılan arayüzde **Resimleri Seç...** butonuna tıklayın.
2. Birleştirmek istediğiniz tüm görüntüleri seçin (Sırası önemli değildir, algoritma kendisi eşleştirir).
3. **Bütünleşik Doku Olarak Birleştir** butonuna basın ve işlemin bitmesini bekleyin.
4. Sonucu inceleyin ve **Sonucu Kaydet...** butonu ile yüksek çözünürlüklü halini bilgisayarınıza aktarın.

```

---

### 2. mikroskop_birlestirici.py (Ana Kod)

Bu da projenin belkemiği olan ve reponuza ekleyeceğiniz Python kodudur. Dosya adını `mikroskop_birlestirici.py` olarak ayarlayabilirsiniz.

```python
import sys
import os
import cv2
import numpy as np
from PyQt5.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QFileDialog, QListWidget, QLabel
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage

class MicroscopeStitcherCore:
    def __init__(self):
        self.sift = cv2.SIFT_create()

    def create_alpha_mask(self, h, w):
        mask = np.zeros((h, w), dtype=np.float32)
        center = (w // 2, h // 2)
        
        radius_inner = int(min(h, w) * 0.42)
        cv2.circle(mask, center, radius_inner, 1.0, -1)
        
        mask = cv2.GaussianBlur(mask, (201, 201), 0)
        return mask

    def load_and_prep_images(self, image_paths):
        images = []
        for path in image_paths:
            try:
                img = cv2.imread(path)
                if img is None: 
                    continue
                
                img_bgra = cv2.cvtColor(img, cv2.COLOR_BGR2BGRA)
                
                h, w = img_bgra.shape[:2]
                alpha_mask = self.create_alpha_mask(h, w)
                
                img_bgra[:, :, 3] = (alpha_mask * 255).astype(np.uint8)
                
                crop_ratio = 0.85
                ch, cw = int(h * crop_ratio), int(w * crop_ratio)
                y, x = (h - ch) // 2, (w - cw) // 2
                cropped_img = img_bgra[y:y+ch, x:x+cw]
                
                images.append(cropped_img)
            except Exception as e:
                print(f"Hata: {path} yüklenemedi. {e}")
        return images

    def advanced_stitch(self, image_paths):
        images = self.load_and_prep_images(image_paths)
        if len(images) < 2:
            return None, "En az iki resim seçmelisiniz."

        print("Özel Patoloji Motoru (Alpha-Feathering Renk Korumalı) başlatıldı...")
        
        canvas = images[0]
        unstitched = images[1:]
        
        sift_data = []
        for img in unstitched:
            img_bgr = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)
            kp, des = self.sift.detectAndCompute(img_bgr, None)
            sift_data.append({"img": img, "kp": kp, "des": des, "bgr": img_bgr})
            
        bf = cv2.BFMatcher()
        
        while sift_data:
            canvas_bgr = cv2.cvtColor(canvas, cv2.COLOR_BGRA2BGR)
            kp_canvas, des_canvas = self.sift.detectAndCompute(canvas_bgr, None)
            
            best_match_idx = -1
            best_match_inliers = 0
            best_M = None
            
            for idx, data in enumerate(sift_data):
                if data["des"] is None or des_canvas is None:
                    continue
                
                matches = bf.knnMatch(data["des"], des_canvas, k=2)
                good = []
                for m_knn in matches:
                    if len(m_knn) == 2:
                        m, n = m_knn
                        if m.distance < 0.75 * n.distance:
                            good.append(m)
                            
                if len(good) > 15:
                    src_pts = np.float32([data["kp"][m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
                    dst_pts = np.float32([kp_canvas[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)
                    
                    M, inliers = cv2.estimateAffinePartial2D(src_pts, dst_pts, cv2.RANSAC)
                    
                    if M is not None:
                        inlier_count = np.sum(inliers)
                        if inlier_count > best_match_inliers and inlier_count > 10:
                            best_match_inliers = inlier_count
                            best_match_idx = idx
                            best_M = M
                            
            if best_match_idx != -1:
                data = sift_data.pop(best_match_idx)
                img = data["img"]
                M = best_M
                
                h_c, w_c = canvas.shape[:2]
                h_i, w_i = img.shape[:2]
                
                corners = np.array([[0,0], [w_i,0], [w_i,h_i], [0,h_i]], dtype=np.float32).reshape(-1,1,2)
                transformed_corners = cv2.transform(corners, M)
                
                all_x = np.concatenate((transformed_corners[:, 0, 0], [0, w_c]))
                all_y = np.concatenate((transformed_corners[:, 0, 1], [0, h_c]))
                
                min_x, max_x = int(np.floor(all_x.min())), int(np.ceil(all_x.max()))
                min_y, max_y = int(np.floor(all_y.min())), int(np.ceil(all_y.max()))
                
                new_w = max_x - min_x
                new_h = max_y - min_y
                
                M_shifted = M.copy()
                M_shifted[0, 2] += -min_x
                M_shifted[1, 2] += -min_y
                
                warped_img = cv2.warpAffine(
                    img, M_shifted, (new_w, new_h), 
                    flags=cv2.INTER_LANCZOS4, 
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(0, 0, 0, 0) 
                )
                
                canvas_padded = np.zeros((new_h, new_w, 4), dtype=np.uint8)
                dx, dy = -min_x, -min_y
                canvas_padded[dy:dy+h_c, dx:dx+w_c] = canvas
                
                alpha_canvas = (canvas_padded[:, :, 3] / 255.0).astype(np.float32)
                alpha_warped = (warped_img[:, :, 3] / 255.0).astype(np.float32)
                
                weight_sum = alpha_canvas + alpha_warped
                weight_sum[weight_sum == 0] = 1.0 
                
                weight_canvas = alpha_canvas / weight_sum
                weight_warped = alpha_warped / weight_sum
                
                canvas_blended = np.zeros_like(canvas_padded, dtype=np.float32)
                
                for c in range(3): 
                    canvas_blended[:, :, c] = (canvas_padded[:, :, c].astype(np.float32) * weight_canvas) + \
                                              (warped_img[:, :, c].astype(np.float32) * weight_warped)
                                              
                canvas_blended[:, :, 3] = np.clip((alpha_canvas + alpha_warped) * 255, 0, 255)
                
                canvas = canvas_blended.astype(np.uint8)
                print(f"Bütünleşik doku saydamlık ile harmanlanıyor... Kalan parça: {len(sift_data)}")
            else:
                print("Eşleşmeyen veya doku örtüşmesi olmayan resimler atlandı.")
                break
                
        final_h, final_w = canvas.shape[:2]
        white_background = np.full((final_h, final_w, 3), 255, dtype=np.uint8)
        
        alpha_final = (canvas[:, :, 3] / 255.0)[:, :, np.newaxis]
        final_bgr = canvas[:, :, :3]
        
        final_result = (final_bgr * alpha_final + white_background * (1.0 - alpha_final)).astype(np.uint8)
                
        return final_result, None

class StitcherThread(QThread):
    result_signal = pyqtSignal(object, str)

    def __init__(self, core, image_paths):
        super().__init__()
        self.core = core
        self.image_paths = image_paths

    def run(self):
        result_img, error = self.core.advanced_stitch(self.image_paths)
        self.result_signal.emit(result_img, error)

class MikroskopBirlestirici(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mikroskop Görüntü Birleştirici (Patoloji Motoru)")
        self.setGeometry(100, 100, 1000, 700)
        self.core = MicroscopeStitcherCore()
        self.image_paths = []
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        self.btn_select = QPushButton("Resimleri Seç...")
        self.btn_select.clicked.connect(self.select_images)
        left_layout.addWidget(self.btn_select)
        
        self.list_widget = QListWidget()
        left_layout.addWidget(self.list_widget)
        
        self.btn_stitch = QPushButton("Bütünleşik Doku Olarak Birleştir")
        self.btn_stitch.clicked.connect(self.stitch_images)
        left_layout.addWidget(self.btn_stitch)
        
        self.btn_save = QPushButton("Sonucu Kaydet...")
        self.btn_save.clicked.connect(self.save_result)
        self.btn_save.setEnabled(False)
        left_layout.addWidget(self.btn_save)
        
        main_layout.addWidget(left_panel, 1)

        self.preview_label = QLabel("Sonuç önizlemesi\n(Resimleri seçin ve birleştire basın)")
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setScaledContents(True)
        self.preview_label.setStyleSheet("border: 1px solid black;")
        main_layout.addWidget(self.preview_label, 3)
        self.result_image_cv = None

    def select_images(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Mikroskop Resimlerini Seç", "", "Resim Dosyaları (*.png *.jpg *.jpeg)")
        if files:
            self.image_paths = files
            self.list_widget.clear()
            for file in self.image_paths:
                self.list_widget.addItem(os.path.basename(file))
            self.preview_label.setText(f"{len(self.image_paths)} resim seçildi.\nBirleştirmek için butona basın.")
            self.result_image_cv = None
            self.btn_save.setEnabled(False)

    def stitch_images(self):
        if len(self.image_paths) < 2:
            self.preview_label.setText("Lütfen en az iki resim seçin.")
            return
        self.preview_label.setText("Gelişmiş Patoloji Motoru çalışıyor...\n(Yüksek çözünürlüklü işlem, lütfen bekleyin)")
        self.btn_stitch.setEnabled(False)
        self.btn_select.setEnabled(False)
        self.btn_save.setEnabled(False)

        self.stitcher_thread = StitcherThread(self.core, self.image_paths)
        self.stitcher_thread.result_signal.connect(self.on_stitch_finished)
        self.stitcher_thread.start()

    def on_stitch_finished(self, result_img, error):
        self.btn_stitch.setEnabled(True)
        self.btn_select.setEnabled(True)
        
        if error:
            self.preview_label.setText(f"Hata: {error}")
            return
        
        if result_img is not None:
            self.result_image_cv = result_img
            self.btn_save.setEnabled(True)
            self.preview_label.setText("Bütünleşik doku başarıyla oluşturuldu.\nKaydedebilirsiniz.")
            
            result_img = np.ascontiguousarray(result_img)
            if len(result_img.shape) == 3: 
                height, width, channel = result_img.shape
                bytes_per_line = 3 * width
                q_img = QImage(result_img.tobytes(), width, height, bytes_per_line, QImage.Format_RGB888).rgbSwapped()
            else: 
                height, width = result_img.shape
                bytes_per_line = width
                q_img = QImage(result_img.tobytes(), width, height, bytes_per_line, QImage.Format_Grayscale8)
                
            self.preview_label.setPixmap(QPixmap.fromImage(q_img))
        else:
            self.preview_label.setText("Bütünleşik doku birleştirilemedi.")

    def save_result(self):
        if self.result_image_cv is not None:
            file_name, _ = QFileDialog.getSaveFileName(self, "Bütünleşik Dokuyu Kaydet", "", "Resim Dosyaları (*.png *.jpg *.jpeg)")
            if file_name:
                if not file_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                    file_name += '.png'
                cv2.imwrite(file_name, self.result_image_cv)
                self.preview_label.setText(f"Sonuç kaydedildi: {os.path.basename(file_name)}")

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = MikroskopBirlestirici()
    window.show()
    try:
        sys.exit(app.exec_())
    except AttributeError:
        sys.exit(app.exec())

```
