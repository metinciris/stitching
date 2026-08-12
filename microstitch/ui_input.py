from .ui_support import *


class MainWindowInputMixin:
    def _make_thumbnail(self, path):
        pixmap = QPixmap(path)
        if pixmap.isNull():
            return QIcon()
        return QIcon(pixmap.scaled(58, 58, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def add_paths(self, paths):
        seen = {os.path.normcase(os.path.abspath(p)) for p in self.image_paths}
        added = 0
        for raw in paths:
            p = os.path.abspath(str(raw))
            if Path(p).suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            key = os.path.normcase(p)
            if key in seen or not os.path.isfile(p):
                continue
            self.image_paths.append(p)
            seen.add(key)
            item = QListWidgetItem(self._make_thumbnail(p), os.path.basename(p))
            item.setToolTip(p)
            item.setData(Qt.UserRole, p)
            self.image_list.addItem(item)
            added += 1
        self.metric_images.set_value(len(self.image_paths))
        if added:
            self.status_label.setText(f"{len(self.image_paths)} image(s) ready.")
            if len(self.image_paths) == 1:
                self.image_view.set_image(self.image_paths[0])
                self.preview_name.setText(os.path.basename(self.image_paths[0]))
        self._log(f"Added {added} image(s). Total: {len(self.image_paths)}")

    def select_images(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Select microscope images",
            "",
            "Images (*.png *.jpg *.jpeg *.tif *.tiff *.bmp *.webp)",
        )
        if paths:
            self.add_paths(paths)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select image folder")
        if not folder:
            return
        paths = [str(p) for p in sorted(Path(folder).iterdir()) if p.suffix.lower() in IMAGE_EXTENSIONS]
        self.add_paths(paths)

    def select_output_dir(self):
        folder = QFileDialog.getExistingDirectory(self, "Select output folder", self.output_edit.text())
        if folder:
            self.output_edit.setText(folder)

    def remove_selected(self):
        selected = sorted({self.image_list.row(item) for item in self.image_list.selectedItems()}, reverse=True)
        for row in selected:
            item = self.image_list.takeItem(row)
            path = item.data(Qt.UserRole)
            try:
                self.image_paths.remove(path)
            except ValueError:
                pass
        self.metric_images.set_value(len(self.image_paths))
        self._log(f"Removed {len(selected)} image(s).")

    def clear_images(self):
        self.image_paths.clear()
        self.image_list.clear()
        self.image_view.clear_image()
        self.preview_name.setText("No result yet")
        self.metric_images.set_value("0")
        self.metric_groups.set_value("-")
        self.metric_error.set_value("-")
        self.metric_size.set_value("-")
        self._log("Image list cleared.")

    def _build_settings(self):
        return StitchSettings(
            work_max_dim=int(self.work_dim_spin.value()),
            sift_features=int(self.sift_spin.value()),
            ratio_test=float(self.ratio_spin.value()),
            ransac_threshold=float(self.ransac_spin.value()),
            min_inliers=int(self.min_inliers_spin.value()),
            seam_mode=self.seam_combo.currentText(),
            blend_bands=int(self.blend_bands_spin.value()),
            max_canvas_megapixels=float(self.canvas_mp_spin.value()),
            hybrid=bool(self.hybrid_check.isChecked()),
            save_png=bool(self.png_check.isChecked()),
            save_pyramidal_tiff=bool(self.tiff_check.isChecked()),
            save_preview=bool(self.preview_check.isChecked()),
        )
