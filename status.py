#!/usr/bin/env python3
"""Read-only status companion for the onedrive systemd user service."""
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime
from PyQt6.QtCore import QProcess, QTimer, QUrl, Qt
from PyQt6.QtGui import QAction, QColor, QIcon, QImage, QPainter, QPixmap, QDesktopServices
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox

@dataclass
class Status:
    label: str = 'Checking OneDrive'
    color: str = '#94a3b8'
    last_sync: float | None = None
    activity: float | None = None
    detail: str = 'Waiting for service logs.'

def parse_logs(rows, now=None):
    now = time.time() if now is None else now
    result = Status()
    for row in sorted(rows, key=lambda r: int(r.get('__REALTIME_TIMESTAMP', 0))):
        message = str(row.get('MESSAGE', ''))
        stamp = int(row.get('__REALTIME_TIMESTAMP', 0)) / 1e6
        lower = message.lower()
        result.activity = stamp
        if 'sync with microsoft onedrive is complete' in lower:
            result.label, result.color = 'Last sync completed', '#22c55e'
            result.last_sync = stamp
            result.detail = 'The client reported a completed sync.'
        elif 'starting a sync' in lower or 'syncing changes' in lower:
            result.label, result.color = 'Syncing', '#3b82f6'
            result.detail = message
        elif any(x in lower for x in ['error', 'failed', 'unable to', 'cannot connect', 'could not connect']):
            result.label, result.color = 'Needs attention', '#ef4444'
            result.detail = message
        elif 'attempting to contact' in lower:
            result.label, result.color = 'Connecting', '#f59e0b'
            result.detail = message
    if result.activity is None:
        result.label, result.detail = 'No recent status', 'No OneDrive service messages were found.'
    elif now - result.activity > 12 * 60:
        result.label, result.color = 'Status is stale', '#f59e0b'
        result.detail = 'No service activity for more than 12 minutes. Check whether syncing is running.'
    return result

def apply_service_state(status, state):
    """Only a definite stopped/failed response overrides the sync log."""
    if state in ['inactive', 'failed', 'deactivating']:
        status.label = 'Service failed' if state == 'failed' else 'Service stopped'
        status.color = '#ef4444'
        status.detail = f'OneDrive user service: {state}. The indicator does not start or stop syncing.'
    elif state != 'active':
        status.detail += '\nService status check unavailable; the displayed status comes from the sync log.'
    return status

def status_icon(color):
    image = QImage(64, 64, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor('#60a5fa'))
    painter.drawEllipse(7, 25, 26, 25)
    painter.drawEllipse(18, 12, 32, 36)
    painter.drawEllipse(36, 27, 22, 23)
    painter.drawRoundedRect(15, 34, 36, 16, 5, 5)
    painter.setBrush(QColor('#172033'))
    painter.drawEllipse(39, 39, 24, 24)
    painter.setBrush(QColor(color))
    painter.drawEllipse(43, 43, 16, 16)
    painter.end()
    return QIcon(QPixmap.fromImage(image))

class Indicator:
    def __init__(self):
        self.status = Status()
        self.tray = QSystemTrayIcon(status_icon(self.status.color))
        menu = QMenu()
        self.menu = menu
        self.state_action = menu.addAction(self.status.label)
        self.state_action.setEnabled(False)
        self.time_action = menu.addAction('Last completed sync: unknown')
        self.time_action.setEnabled(False)
        menu.addSeparator()
        menu.addAction('View status details', self.details)
        menu.addAction('Open OneDrive folder', self.open_folder)
        menu.addAction('Refresh status', self.refresh)
        menu.addSeparator()
        menu.addAction('Quit indicator', QApplication.instance().quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.details() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
        self.tray.show()
        self.logs = QProcess()
        self.logs.finished.connect(self.logs_finished)
        self.service = QProcess()
        self.service.finished.connect(self.service_finished)
        self.timer = QTimer()
        self.timer.timeout.connect(self.refresh)
        self.timer.start(15000)
        self.refresh()

    def refresh(self):
        if self.logs.state() != QProcess.ProcessState.NotRunning or self.service.state() != QProcess.ProcessState.NotRunning:
            return
        self.logs.start('journalctl', ['--user', '-u', 'onedrive.service', '--since', '24 hours ago', '-n', '1000', '--no-pager', '-o', 'json'])
        QTimer.singleShot(8000, lambda: self.logs.kill() if self.logs.state() != QProcess.ProcessState.NotRunning else None)

    def logs_finished(self, code, exit_status):
        try:
            if code != 0:
                raise RuntimeError('Service logs could not be read. Check journal access.')
            text = bytes(self.logs.readAllStandardOutput()).decode(errors='replace')
            self.status = parse_logs([json.loads(line) for line in text.splitlines() if line.strip()])
        except (ValueError, RuntimeError) as exc:
            self.status = Status(label='Status unavailable', detail=str(exc))
        self.update()
        if self.service.state() == QProcess.ProcessState.NotRunning:
            self.service.start('systemctl', ['--user', 'is-active', 'onedrive.service'])
            QTimer.singleShot(5000, lambda: self.service.kill() if self.service.state() != QProcess.ProcessState.NotRunning else None)

    def service_finished(self, code, exit_status):
        state = bytes(self.service.readAllStandardOutput()).decode().strip()
        self.status = apply_service_state(self.status, state)
        self.update()

    def update(self):
        last = datetime.fromtimestamp(self.status.last_sync).strftime('%d %b %H:%M:%S') if self.status.last_sync else 'unknown'
        self.state_action.setText(self.status.label)
        self.time_action.setText('Last completed sync: ' + last)
        self.tray.setIcon(status_icon(self.status.color))
        self.tray.setToolTip(f'OneDrive: {self.status.label}\nLast completed sync: {last}')

    def details(self):
        last = datetime.fromtimestamp(self.status.last_sync).strftime('%d %b %Y %H:%M:%S') if self.status.last_sync else 'unknown'
        box = QMessageBox()
        box.setWindowTitle('OneDrive status')
        box.setText(self.status.label)
        box.setInformativeText(f'Last completed sync: {last}\n\n{self.status.detail}\n\nA completed sync is the client’s report; individual file uploads are not independently verified.')
        box.exec()

    def open_folder(self):
        folder = Path.home() / 'OneDrive'
        if folder.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        else:
            QMessageBox.information(None, 'OneDrive folder', 'The default ~/OneDrive folder was not found.')

if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName('OneDrive Status')
    app.setQuitOnLastWindowClosed(False)
    indicator = Indicator()
    sys.exit(app.exec())
