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
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#############################################################################

"""
Module for view class.

:author: Pekka Savolainen <pekka.t.savolainen@vtt.fi>
:date:   19.12.2017
"""

import logging
from metaobject import MetaObject
from widgets.view_subwindow_widget import ViewWidget
from PySide2.QtCore import Slot
from views import ViewImage


class View(MetaObject):
    """View class.

    Attributes:
        parent (ToolboxUI): QMainWindow instance
        name (str): Object name
        description (str): Object description
        project (SpineToolboxProject): Project
    """
    def __init__(self, parent, name, description, project, x, y):
        super().__init__(name, description)
        self._parent = parent
        self.item_type = "View"
        self.item_category = "Views"
        self._project = project
        self._data = "data"
        self._widget = ViewWidget(name, self.item_type)
        self._widget.set_type_label(self.item_type)
        self._widget.set_name_label(name)
        self._widget.set_data_label(self._data)
        self._graphics_item = ViewImage(self._parent, x, y, 70, 70, self.name)
        self.connect_signals()

    def connect_signals(self):
        """Connect this view's signals to slots."""
        self._widget.ui.pushButton_info.clicked.connect(self.info_clicked)
        self._widget.ui.pushButton_connections.clicked.connect(self.show_connections)

    def set_icon(self, icon):
        """Set icon."""
        self._graphics_item = icon

    def get_icon(self):
        """Returns the item representing this data connection in the scene."""
        return self._graphics_item

    def get_widget(self):
        """Returns the graphical representation (QWidget) of this object."""
        return self._widget

    @Slot(name='info_clicked')
    def info_clicked(self):
        """Info button clicked."""
        logging.debug(self.name + " - " + str(self._data))

    @Slot(name="show_connections")
    def show_connections(self):
        """Show connections of this item."""
        inputs = self._parent.connection_model.input_items(self.name)
        outputs = self._parent.connection_model.output_items(self.name)
        self._parent.msg.emit("<br/><b>{0}</b>".format(self.name))
        self._parent.msg.emit("Input items")
        if not inputs:
            self._parent.msg_warning.emit("None")
        else:
            for item in inputs:
                self._parent.msg_warning.emit("{0}".format(item))
        self._parent.msg.emit("Output items")
        if not outputs:
            self._parent.msg_warning.emit("None")
        else:
            for item in outputs:
                self._parent.msg_warning.emit("{0}".format(item))

    def set_data(self, d):
        """Set data and update widgets representation of data."""
        self._data = d
        self._widget.set_data_label("Data:" + str(self._data))

    def get_data(self):
        """Returns data of object."""
        return self._data
