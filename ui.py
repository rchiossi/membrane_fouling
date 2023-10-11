#!/usr/bin/env python

import os
import sys
import time
from enum import Enum

from PySide6 import QtCore, QtWidgets
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QPushButton, QTableWidget,
                               QTableWidgetItem, QVBoxLayout)

from mf import MembraneFouling


class State(Enum):
    NEW = 0
    DONE = 1
    ERROR = 2


class WorkerSignals(QObject):
    error = Signal(str)
    result = Signal(list)


class FileWorker(QRunnable):
    def __init__(self, path: str, filename: str):
        super(FileWorker, self).__init__()

        self.filename: str = filename
        self.path = path

        self.mf: MembraneFouling | None = None

        self.signals = WorkerSignals()

    def parse(self) -> None:
        with open(os.path.join(self.path, self.filename)) as f:
            data = f.read()

        lines = data.strip().split("\n")
        self.mf = MembraneFouling(*lines[1:7])

        for line in lines[8:]:
            self.mf.add_data(line)

    @QtCore.Slot()
    def run(self):
        try:
            self.parse()
            assert(self.mf is not None)

            data = []
            data.append(self.filename)
            data.append(self.mf.date)
            data.append(self.mf.time)
            data.append(str(self.mf.sdi))
            data.append(str(self.mf.ti))
            data.append(str(self.mf.tf))
            data.append(self.mf.status)
            data.append(f'{self.mf.calc_ti():.3f}')
            data.append(f'{self.mf.calc_tf5():.3f}')
            data.append(f'{self.mf.calc_tf15():.3f}')
            data.append(f'{self.mf.calc_sdi5():.2f}')
            data.append(f'{self.mf.calc_sdi15():.2f}')
            data.append(f'{self.mf.calc_mfi():.3f}')
            data.append(f'{self.mf.calc_avg_temp():.3f}')

            self.signals.result.emit(data)

        except Exception as e:
            print(f' Error processing file {self.filename}: {e}')
            self.signals.error.emit(self.filename)


class CSVWorker(QRunnable):
    def __init__(self, headers: list[str], data: dict[str, list[str]], state: dict[str, State], path: str, filename: str | None = None):
        super(CSVWorker, self).__init__()

        self.path = path
        self.filename = filename
        self.headers = headers
        self.data = data
        self.state = state

        if not self.filename:
            self.filename = f'membrane_fouling_{time.strftime("%Y%m%d-%H%M%S")}.csv'

        self.signals = WorkerSignals()

    @QtCore.Slot()
    def run(self):
        assert(self.filename is not None)

        fullpath = os.path.join(self.path, self.filename)

        try:
            with open(fullpath, "w") as f:
                f.write(','.join(self.headers))
                f.write("\n")

                for filename, result in self.data.items():
                    if self.state[filename] != State.DONE:
                        continue

                    f.write(",".join(result))
                    f.write("\n")

            self.signals.result.emit([fullpath])

        except Exception as e:
            print(f' Error generating csv {fullpath}: {e}')
            self.signals.error.emit(fullpath)


class MFWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.data: dict[str, list[str]] = {}
        self.state: dict[str, State] = {}
        self.dir = ''

        self.init_ui()

        self.threadpool = QThreadPool()

        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.update_table)
        self.timer.start()

    def init_ui(self):
        self.layout = QVBoxLayout(self)   # pyright: ignore

        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout()

        folder_label = QLabel("Data Directory: ")

        self.folder_textbox = QLineEdit()
        self.folder_textbox.setReadOnly(True)
        self.folder_textbox.setText(os.getcwd())

        folder_button = QPushButton("Select Folder")
        folder_button.clicked.connect(self.folder_click)

        dir_layout = QHBoxLayout()
        dir_layout.addWidget(folder_label)
        dir_layout.addWidget(self.folder_textbox)
        dir_layout.addWidget(folder_button)

        options_layout.addLayout(dir_layout)

        load_button = QPushButton("Load Files")
        load_button.clicked.connect(self.load_files)

        options_layout.addWidget(load_button)

        options_group.setLayout(options_layout)
        self.layout.addWidget(options_group)

        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout()

        self.table_headers = ["File",
                              "Date", "Time", "sdi", "ti", "tf", "status",
                              "calc_ti", "calc_tf5", "calc_tf15", "calc_sdi5",
                              "calc_sdi15", "calc_mfi", "calc_avg_temp"]
        self.tableWidget = QTableWidget(0, len(self.table_headers), self)
        self.tableWidget.setHorizontalHeaderLabels(self.table_headers)
        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

        table_layout = QVBoxLayout()
        table_layout.addWidget(self.tableWidget)
        results_layout.addLayout(table_layout, 2)

        calculate_button = QPushButton("Calculate")
        calculate_button.clicked.connect(self.calculate)

        results_layout.addWidget(calculate_button)

        results_layout.addStretch()

        results_group.setLayout(results_layout)
        self.layout.addWidget(results_group)

        export_group = QGroupBox("Export Results")
        export_layout = QVBoxLayout()

        export_label = QLabel("Destination Folder: ")

        self.export_textbox = QLineEdit()
        self.export_textbox.setReadOnly(True)
        self.export_textbox.setText(os.getcwd())

        expdir_button = QPushButton("Select Folder")
        expdir_button.clicked.connect(self.folder_click)

        expdir_layout = QHBoxLayout()
        expdir_layout.addWidget(export_label)
        expdir_layout.addWidget(self.export_textbox)
        expdir_layout.addWidget(expdir_button)

        export_layout.addLayout(expdir_layout)

        export_button = QPushButton("Export CSV")
        export_button.clicked.connect(self.export_csv)
        export_layout.addWidget(export_button)

        export_group.setLayout(export_layout)

        self.layout.addWidget(export_group)

    def update_table(self):
        self.tableWidget.clear()

        self.tableWidget.setHorizontalHeaderLabels(self.table_headers)

        rowCount = 0
        for key in sorted(self.data.keys()):
            data = self.data[key]
            state = self.state[data[0]]

            if rowCount >= self.tableWidget.rowCount():
                self.tableWidget.insertRow(rowCount)

            for index in range(len(self.table_headers)):
                item = QTableWidgetItem(data[index])

                match state:
                    case State.NEW:
                        item.setBackground(QColor.fromRgb(223, 231, 253))
                    case State.DONE:
                        item.setBackground(QColor.fromRgb(226, 236, 233))
                    case State.ERROR:
                        item.setBackground(QColor.fromRgb(250, 210, 225))
                    case _:
                        item.setBackground(QColor.fromRgb(255, 255, 255))

                item.setFlags(QtCore.Qt.ItemFlag.ItemIsSelectable | QtCore.Qt.ItemFlag.ItemIsEnabled)
                self.tableWidget.setItem(rowCount, index, item)

            rowCount += 1

        self.tableWidget.resizeColumnsToContents()
        self.tableWidget.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)

    @QtCore.Slot()
    def update_row(self, data: list[str]) -> None:
        print(f"Data Calculated: {data}")
        self.data[data[0]] = data
        self.state[data[0]] = State.DONE

    @QtCore.Slot()
    def update_error(self, filename: str) -> None:
        self.state[filename] = State.ERROR

    @QtCore.Slot()
    def folder_click(self):
        dir = str(QtWidgets.QFileDialog.getExistingDirectory(self, "Select Directory"))
        self.folder_textbox.setText(dir)

    @QtCore.Slot()
    def load_files(self):
        self.dir = self.folder_textbox.text()
        files = os.listdir(path=str(self.dir))

        self.data = {}
        self.state = {}

        for filename in files:
            self.data[filename] = [filename] + [''] * (len(self.table_headers) - 1)
            self.state[filename] = State.NEW

        self.update_table()

    @QtCore.Slot()
    def calculate(self):
        for filename in sorted(self.data.keys()):
            worker = FileWorker(self.dir, filename)
            worker.signals.result.connect(self.update_row)
            worker.signals.error.connect(self.update_error)

            self.threadpool.start(worker)

    @QtCore.Slot()
    def sucess_csv(self, filename: str):
        print(f"CSV Exported to: {filename}")

    @QtCore.Slot()
    def export_csv(self):
        worker = CSVWorker(self.table_headers, self.data, self.state, self.export_textbox.text())
        worker.signals.result.connect(self.sucess_csv)
        worker.signals.error.connect(self.update_error)

        self.threadpool.start(worker)


if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    widget = MFWidget()
    widget.resize(1000, 800)
    widget.setWindowTitle("Membrane Fouling")
    widget.show()

    sys.exit(app.exec())
