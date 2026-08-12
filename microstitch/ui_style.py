from .ui_support import *


class MainWindowStyleMixin:
    def _apply_style(self):
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #f4f6f9; color: #1e293b; font-family: 'Segoe UI'; font-size: 11pt; }
            #sidebar { background: #111827; border: none; }
            #sidebar QLabel { color: #e5e7eb; }
            #brand { background: transparent; color: #ffffff; font-size: 24pt; font-weight: 700; padding: 0; }
            #subtitle { background: transparent; color: #cbd5e1; font-size: 10.5pt; padding-bottom: 4px; }
            #statusLabel { background: transparent; color: #e2e8f0; font-size: 10.5pt; padding: 6px 2px; }
            #content { background: #f4f6f9; }
            #pageTitle { font-size: 20pt; font-weight: 700; color: #0f172a; }
            #previewName { font-size: 11pt; font-weight: 600; color: #334155; }
            #metricCard { background: white; border: 1px solid #e2e8f0; border-radius: 10px; }
            #metricTitle { color: #475569; font-size: 9.5pt; font-weight: 600; }
            #metricValue { color: #0f172a; font-size: 15pt; font-weight: 700; }
            QGroupBox { background: white; border: 1px solid #dbe2ea; border-radius: 9px; margin-top: 11px; padding-top: 12px; font-size: 10.5pt; font-weight: 700; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #334155; }
            #sidebar QGroupBox { background: #172033; border-color: #2c3952; color: #e5e7eb; }
            #sidebar QGroupBox::title { color: #dbeafe; }
            QPushButton { background: white; border: 1px solid #cbd5e1; border-radius: 7px; padding: 8px 13px; min-height: 22px; color: #1e293b; font-size: 10.5pt; }
            QPushButton:hover { background: #f8fafc; border-color: #94a3b8; }
            QPushButton:disabled { color: #94a3b8; background: #e2e8f0; border-color: #e2e8f0; }
            #sidebar QPushButton { background: #1f2937; color: #e5e7eb; border-color: #374151; }
            #sidebar QPushButton:hover { background: #273449; border-color: #4b5563; }
            #primaryButton { background: #2563eb; color: white; border: none; font-weight: 700; letter-spacing: 0.5px; }
            #primaryButton:hover { background: #1d4ed8; }
            #primaryButton:disabled { background: #475569; color: #94a3b8; }
            #dangerButton { background: #7f1d1d; color: white; border: none; }
            #dangerButton:hover { background: #991b1b; }
            QListWidget { background: #0f172a; color: #e5e7eb; border: 1px solid #334155; border-radius: 7px; padding: 4px; }
            QListWidget::item { padding: 7px 6px; border-radius: 5px; min-height: 56px; }
            QListWidget::item:selected { background: #1d4ed8; color: white; }
            QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #cbd5e1; border-radius: 6px; padding: 7px; min-height: 22px; font-size: 10.5pt; }
            #sidebar QLineEdit { background: #0f172a; color: #f8fafc; border-color: #334155; }
            QTabWidget::pane { border: 1px solid #dbe2ea; background: white; border-radius: 8px; }
            QTabBar::tab { background: #e9eef5; color: #475569; padding: 11px 20px; font-size: 10.5pt; border-top-left-radius: 6px; border-top-right-radius: 6px; margin-right: 2px; }
            QTabBar::tab:selected { background: white; color: #0f172a; font-weight: 700; }
            #imageView { background: #111827; border-radius: 7px; }
            QTextEdit { background: #0b1220; color: #e2f0ff; border: 1px solid #1f2937; border-radius: 7px; padding: 6px; font-family: Consolas, 'Courier New'; font-size: 10.5pt; selection-background-color: #1d4ed8; }
            QProgressBar { background: #0f172a; color: white; border: 1px solid #475569; border-radius: 6px; text-align: center; min-height: 24px; font-size: 10pt; font-weight: 600; }
            QProgressBar::chunk { background: #2563eb; border-radius: 5px; }
            QCheckBox { spacing: 9px; font-size: 10.5pt; }
            QFormLayout QLabel { font-size: 10.5pt; }
            QToolTip { background: #111827; color: #f8fafc; border: 1px solid #475569; padding: 5px; }
            """
        )

    def _wire_signals(self):
        self.add_images_btn.clicked.connect(self.select_images)
        self.add_folder_btn.clicked.connect(self.select_folder)
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn.clicked.connect(self.clear_images)
        self.output_browse_btn.clicked.connect(self.select_output_dir)
        self.stitch_btn.clicked.connect(self.start_stitch)
        self.cancel_btn.clicked.connect(self.cancel_stitch)
        self.fit_btn.clicked.connect(self.image_view.fit_to_window)
        self.open_result_btn.clicked.connect(self.open_result)
        self.open_folder_btn.clicked.connect(self.open_output_folder)
        self.image_list.filesDropped.connect(self.add_paths)
        self.preset_combo.currentTextChanged.connect(self._sync_preset)
        for widget in (
            self.work_dim_spin,
            self.sift_spin,
            self.ratio_spin,
            self.ransac_spin,
            self.min_inliers_spin,
            self.blend_bands_spin,
            self.canvas_mp_spin,
        ):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(self._mark_custom_if_needed)

    def _set_default_output_dir(self):
        base = Path.home() / "MicroStitch_Output"
        self.output_edit.setText(str(base))

    def _sync_preset(self):
        preset = self.preset_combo.currentText()
        profiles = {
            "Fast": dict(work=520, sift=1500, ratio=0.79, ransac=3.6, inliers=12, bands=2, canvas=160),
            "Balanced": dict(work=750, sift=2600, ratio=0.78, ransac=3.0, inliers=16, bands=3, canvas=220),
            "Maximum quality": dict(work=1100, sift=4800, ratio=0.76, ransac=2.6, inliers=20, bands=4, canvas=420),
        }
        if preset not in profiles:
            return
        p = profiles[preset]
        widgets = (
            self.work_dim_spin,
            self.sift_spin,
            self.ratio_spin,
            self.ransac_spin,
            self.min_inliers_spin,
            self.blend_bands_spin,
            self.canvas_mp_spin,
        )
        blockers = [w.blockSignals(True) for w in widgets]
        self.work_dim_spin.setValue(p["work"])
        self.sift_spin.setValue(p["sift"])
        self.ratio_spin.setValue(p["ratio"])
        self.ransac_spin.setValue(p["ransac"])
        self.min_inliers_spin.setValue(p["inliers"])
        self.blend_bands_spin.setValue(p["bands"])
        self.canvas_mp_spin.setValue(p["canvas"])
        for widget, old in zip(widgets, blockers):
            widget.blockSignals(old)

    def _mark_custom_if_needed(self, *args):
        if self.preset_combo.currentText() != "Custom":
            self.preset_combo.blockSignals(True)
            self.preset_combo.setCurrentText("Custom")
            self.preset_combo.blockSignals(False)
