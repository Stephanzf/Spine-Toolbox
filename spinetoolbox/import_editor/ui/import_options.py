# -*- coding: utf-8 -*-
######################################################################################################################
# Copyright (C) 2017-2020 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

################################################################################
## Form generated from reading UI file 'import_options.ui'
##
## Created by: Qt User Interface Compiler version 5.14.2
##
## WARNING! All changes made in this file will be lost when recompiling UI file!
################################################################################

from PySide2.QtCore import (QCoreApplication, QDate, QDateTime, QMetaObject,
    QObject, QPoint, QRect, QSize, QTime, QUrl, Qt)
from PySide2.QtGui import (QBrush, QColor, QConicalGradient, QCursor, QFont,
    QFontDatabase, QIcon, QKeySequence, QLinearGradient, QPalette, QPainter,
    QPixmap, QRadialGradient)
from PySide2.QtWidgets import *


class Ui_ImportOptions(object):
    def setupUi(self, ImportOptions):
        if not ImportOptions.objectName():
            ImportOptions.setObjectName(u"ImportOptions")
        ImportOptions.resize(400, 300)
        self.verticalLayout = QVBoxLayout(ImportOptions)
        self.verticalLayout.setObjectName(u"verticalLayout")
        self.options_box = QGroupBox(ImportOptions)
        self.options_box.setObjectName(u"options_box")
        self.verticalLayout_2 = QVBoxLayout(self.options_box)
        self.verticalLayout_2.setObjectName(u"verticalLayout_2")
        self.options_layout = QFormLayout()
        self.options_layout.setObjectName(u"options_layout")

        self.verticalLayout_2.addLayout(self.options_layout)


        self.verticalLayout.addWidget(self.options_box)


        self.retranslateUi(ImportOptions)

        QMetaObject.connectSlotsByName(ImportOptions)
    # setupUi

    def retranslateUi(self, ImportOptions):
        ImportOptions.setWindowTitle(QCoreApplication.translate("ImportOptions", u"Form", None))
        self.options_box.setTitle(QCoreApplication.translate("ImportOptions", u"Options", None))
    # retranslateUi

