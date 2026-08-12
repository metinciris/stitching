from .ui_support import *


class MainWindowProcessMixin:
    def start_stitch(self):
        if self.worker and self.worker.isRunning():
            return
        if len(self.image_paths) < 2:
            QMessageBox.warning(self, APP_NAME, "Please add at least two microscope images.")
            return
        output_dir = self.output_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, APP_NAME, "Please choose an output folder.")
            return
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        settings = self._build_settings()
        if not (settings.save_png or settings.save_preview or settings.save_pyramidal_tiff):
            QMessageBox.warning(self, APP_NAME, "Enable at least one output format.")
            return

        self.last_report = None
        self.last_preview_path = None
        self.open_result_btn.setEnabled(False)
        self.open_folder_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.status_label.setText("Starting global registration...")
        self.stitch_btn.setEnabled(False)
        self.cancel_btn.setEnabled(True)
        self.add_images_btn.setEnabled(False)
        self.add_folder_btn.setEnabled(False)
        self.tabs.setCurrentIndex(2)
        self._log("=" * 70)
        self._log(f"Starting {APP_NAME} {APP_VERSION}")
        self._log(f"Input images: {len(self.image_paths)}")
        self._log(f"Output folder: {output_dir}")
        self._log(f"Settings: {asdict(settings)}")

        self.worker = StitchWorker(self.image_paths, output_dir, settings, self)
        self.worker.progressSignal.connect(self.on_progress)
        self.worker.finishedSignal.connect(self.on_finished)
        self.worker.failedSignal.connect(self.on_failed)
        self.worker.start()

    def cancel_stitch(self):
        if self.worker and self.worker.isRunning():
            self.status_label.setText("Cancellation requested...")
            self.cancel_btn.setEnabled(False)
            self.worker.request_cancel()
            self._log("Cancellation requested by user.")

    def on_progress(self, stage, fraction, message):
        fraction = max(0.0, min(1.0, float(fraction)))
        self.progress_bar.setValue(int(fraction * 1000))
        self.status_label.setText(message)
        self._log(f"[{stage:>10}] {fraction * 100:6.1f}%  {message}")

    def _best_output_from_report(self, report):
        groups = report.get("groups", [])
        if groups:
            valid = [g for g in groups if g.get("outputs")]
            if valid:
                best = min(valid, key=lambda g: (g.get("relative_scale", 1.0), -len(g.get("tile_indices", []))))
                outputs = best.get("outputs", {})
                return outputs.get("preview") or outputs.get("png") or outputs.get("pyramidal_tiff")
        outputs = report.get("outputs", {})
        for group_outputs in outputs.values():
            if isinstance(group_outputs, dict):
                p = group_outputs.get("preview") or group_outputs.get("png")
                if p:
                    return p
        return None

    def on_finished(self, report):
        self.last_report = report
        self.progress_bar.setValue(1000)
        self.status_label.setText("Stitching completed successfully.")
        self._set_busy(False)
        groups = report.get("groups", [])
        self.metric_groups.set_value(len({g.get("group_id") for g in groups}))
        residuals = [
            g.get("median_registration_residual_px")
            for g in groups
            if g.get("median_registration_residual_px") is not None
        ]
        if residuals:
            self.metric_error.set_value(f"{min(residuals):.2f} px")
        if groups:
            best = min(groups, key=lambda g: (g.get("relative_scale", 1.0), -len(g.get("tile_indices", []))))
            shape = best.get("output_shape", [])
            if len(shape) >= 2:
                self.metric_size.set_value(f"{shape[1]} x {shape[0]}")
        preview = self._best_output_from_report(report)
        if preview and os.path.exists(preview):
            self.last_preview_path = preview
            if self.image_view.set_image(preview):
                self.preview_name.setText(os.path.basename(preview))
                self.tabs.setCurrentIndex(0)
                self.open_result_btn.setEnabled(True)
        self.open_folder_btn.setEnabled(True)
        self._log(f"Completed. Report: {report.get('report_path', '')}")
        QMessageBox.information(
            self,
            APP_NAME,
            "Whole-slide style mosaic completed.\nThe highest-resolution objective group is shown in Preview.",
        )

    def on_failed(self, text):
        self._set_busy(False)
        self.status_label.setText("Stitching stopped or failed.")
        self._log(text)
        if "cancelled" in text.lower():
            QMessageBox.information(self, APP_NAME, "Operation cancelled.")
        else:
            QMessageBox.critical(self, APP_NAME, "Stitching failed. See the Process log tab for details.")
            self.tabs.setCurrentIndex(2)

    def _set_busy(self, busy):
        self.stitch_btn.setEnabled(not busy)
        self.cancel_btn.setEnabled(busy)
        self.add_images_btn.setEnabled(not busy)
        self.add_folder_btn.setEnabled(not busy)
        self.remove_btn.setEnabled(not busy)
        self.clear_btn.setEnabled(not busy)
        self.output_browse_btn.setEnabled(not busy)

    def _log(self, text):
        self.log_edit.append(str(text).replace("\n", "<br>"))
        bar = self.log_edit.verticalScrollBar()
        bar.setValue(bar.maximum())

    def open_result(self):
        if self.last_preview_path and os.path.exists(self.last_preview_path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.last_preview_path))

    def open_output_folder(self):
        folder = self.output_edit.text().strip()
        if folder and os.path.isdir(folder):
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            choice = QMessageBox.question(
                self,
                APP_NAME,
                "Stitching is still running. Cancel and close?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if choice != QMessageBox.Yes:
                event.ignore()
                return
            self.worker.request_cancel()
            self.worker.wait(3000)
        event.accept()
