#############################################################################
# Copyright (C) 2017 - 2018 VTT Technical Research Centre of Finland
#
# This file is part of Spine Toolbox.
#
# Spine Toolbox is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#############################################################################

# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file '../spinetoolbox/ui/subwindow.ui'
#
#
# WARNING! All changes made in this file will be lost!

from PySide2 import QtCore, QtGui, QtWidgets

class Ui_Form(object):
    def setupUi(self, Form):
        Form.setObjectName("Form")
        Form.resize(174, 112)
        Form.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.gridLayout = QtWidgets.QGridLayout(Form)
        self.gridLayout.setObjectName("gridLayout")
        self.label_type = QtWidgets.QLabel(Form)
        self.label_type.setObjectName("label_type")
        self.gridLayout.addWidget(self.label_type, 0, 0, 1, 1)
        self.label_name = QtWidgets.QLabel(Form)
        self.label_name.setWordWrap(True)
        self.label_name.setObjectName("label_name")
        self.gridLayout.addWidget(self.label_name, 1, 0, 1, 1)
        self.label_data = QtWidgets.QLabel(Form)
        self.label_data.setObjectName("label_data")
        self.gridLayout.addWidget(self.label_data, 2, 0, 1, 1)
        self.pushButton_edit = QtWidgets.QPushButton(Form)
        self.pushButton_edit.setMaximumSize(QtCore.QSize(75, 23))
        self.pushButton_edit.setObjectName("pushButton_edit")
        self.gridLayout.addWidget(self.pushButton_edit, 3, 0, 1, 1)
        self.pushButton_connections = QtWidgets.QPushButton(Form)
        self.pushButton_connections.setObjectName("pushButton_connections")
        self.gridLayout.addWidget(self.pushButton_connections, 3, 1, 1, 1)

        self.retranslateUi(Form)
        QtCore.QMetaObject.connectSlotsByName(Form)

    def retranslateUi(self, Form):
        Form.setWindowTitle(QtWidgets.QApplication.translate("Form", "Item", None, -1))
        self.label_type.setText(QtWidgets.QApplication.translate("Form", "Type", None, -1))
        self.label_name.setText(QtWidgets.QApplication.translate("Form", "Name", None, -1))
        self.label_data.setText(QtWidgets.QApplication.translate("Form", "Data", None, -1))
        self.pushButton_edit.setText(QtWidgets.QApplication.translate("Form", "Info", None, -1))
        self.pushButton_connections.setToolTip(QtWidgets.QApplication.translate("Form", "<html><head/><body><p>Show connections</p></body></html>", None, -1))
        self.pushButton_connections.setText(QtWidgets.QApplication.translate("Form", "Conn.", None, -1))

