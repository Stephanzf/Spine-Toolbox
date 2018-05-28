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
Widget to show Data Store Form.

:author: Manuel Marin <manuelma@kth.se>
:date:   21.4.2018
"""

from PySide2.QtWidgets import QWidget, QStatusBar, QHeaderView,\
    QDialog, QLineEdit, QInputDialog
from PySide2.QtCore import Slot, Qt, QSettings
from PySide2.QtGui import QStandardItem
from ui.data_store_form import Ui_Form
from config import STATUSBAR_SS
from widgets.custom_menus import ObjectTreeContextMenu, ObjectParameterValueContextMenu
from widgets.custom_qdialog import CustomQDialog
from helpers import busy_effect
from models import ObjectTreeModel, MinimalTableModel, ObjectParameterValueProxy,\
    RelationshipParameterValueProxy, ObjectParameterProxy, RelationshipParameterProxy
import logging
from datetime import datetime, timezone
from sqlalchemy import or_
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session, aliased
import time # just to measure loading time and sqlalchemy ORM performance
from widgets.lineedit_delegate import LineEditDelegate
from widgets.combobox_delegate import ComboBoxDelegate


class DataStoreForm(QWidget):
    """A widget to show and edit Spine objects in a data store."""

    def __init__(self, parent, engine, database, username):
        """ Initialize class.

        Args:
            parent (ToolBoxUI): QMainWindow instance
            engine (Engine): The sql alchemy engine to use with this Store
            database (str): The database name
            username (str): The user name
        """
        tic = time.clock()
        super().__init__()
        # Setup UI from Qt Designer file
        self.ui = Ui_Form()
        self.ui.setupUi(self)
        self.qsettings = QSettings("SpineProject", "Spine Toolbox Data Store")
        # Class attributes
        self._parent = parent
        self.engine = engine
        self.database = database
        self.username = username
        self.Base = None
        self.ObjectClass = None
        self.Object = None
        self.RelationshipClass = None
        self.Relationship = None
        self.Parameter = None
        self.ParameterValue = None
        self.object_class = None
        self.Commit = None
        self.session = None
        self.bold_font = None
        # Object tree model
        self.object_tree_model = ObjectTreeModel(self)
        # Parameter value models
        self.object_parameter_value_model = MinimalTableModel(self)
        self.object_parameter_value_proxy = ObjectParameterValueProxy(self)
        self.relationship_parameter_value_model = MinimalTableModel(self)
        self.relationship_parameter_value_proxy = RelationshipParameterValueProxy(self)
        # Parameter (definition) models
        self.object_parameter_model = MinimalTableModel(self)
        self.object_parameter_proxy = ObjectParameterProxy(self)
        self.relationship_parameter_model = MinimalTableModel(self)
        self.relationship_parameter_proxy = RelationshipParameterProxy(self)
        # Add status bar to form
        self.statusbar = QStatusBar(self)
        self.statusbar.setFixedHeight(20)
        self.statusbar.setSizeGripEnabled(False)
        self.statusbar.setStyleSheet(STATUSBAR_SS)
        self.ui.horizontalLayout_statusbar_placeholder.addWidget(self.statusbar)
        # context menus
        self.object_tree_context_menu = None
        self.object_parameter_value_context_menu = None
        self.create_session()
        self.init_object_tree_model()
        self.init_parameter_value_models()
        self.init_parameter_value_views()
        self.connect_signals()
        self.restore_ui()
        self.setWindowTitle("Spine Data Store    -- {} --".format(self.database))
        # Ensure this window gets garbage-collected when closed
        self.setAttribute(Qt.WA_DeleteOnClose)
        toc = time.clock()
        logging.debug("Elapsed = {}".format(toc - tic))

    def connect_signals(self):
        """Connect signals to slots."""
        self.ui.pushButton_commit.clicked.connect(self.commit_clicked)
        self.ui.pushButton_close.clicked.connect(self.close_clicked)
        self.ui.pushButton_revert.clicked.connect(self.revert_clicked)
        self.ui.treeView_object.selectionModel().currentChanged.connect(self.filter_parameter_models)
        self.ui.treeView_object.editKeyPressed.connect(self.rename_item)
        self.ui.treeView_object.customContextMenuRequested.connect(self.show_object_tree_context_menu)
        self.ui.treeView_object.doubleClicked.connect(self.expand_at_top_level)
        self.ui.tableView_object_parameter_value.selectionModel().selectionChanged.\
            connect(self.update_object_parameter_value_selection)
        self.ui.tableView_object_parameter_value.customContextMenuRequested.\
            connect(self.show_object_parameter_value_context_menu)

    @Slot(name="commit_clicked")
    def commit_clicked(self):
        """Commit changes to source database."""
        comment = self.ui.lineEdit_commit_msg.text()
        if not comment:
            msg = "Commit message missing."
            self.statusbar.showMessage(msg, 3000)
            return
        if not self.session:
            msg = "No session!"
            self.statusbar.showMessage(msg, 3000)
            return
        self.commit.comment = comment
        self.commit.date = datetime.now(timezone.utc)
        try:
            self.session.commit()
        except DBAPIError as e:
            msg = "Error while trying to commit changes: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        msg = "All changes commited successfully."
        self.statusbar.showMessage(msg, 5000)
        self.new_commit()

    @Slot(name="revert_clicked")
    def revert_clicked(self):
        if not self.session:
            return
        try:
            self.session.rollback()
        except Exception:
            msg = "Error while trying to revert changes."
            self.statusbar.showMessage(msg, 3000)
        self.new_commit()
        self.init_object_tree_model()
        self.init_parameter_value_models()
        msg = "All changes (since last commit) reverted successfully."
        self.statusbar.showMessage(msg, 3000)
        # clear filters
        self.object_parameter_value_proxy.clear_filter()
        self.relationship_parameter_value_proxy.clear_filter()

    def create_session(self):
        """Create base, engine, reflect tables and create session."""
        self.Base = automap_base()
        self.Base.prepare(self.engine, reflect=True)
        self.ObjectClass = self.Base.classes.object_class
        self.Object = self.Base.classes.object
        self.RelationshipClass = self.Base.classes.relationship_class
        self.Relationship = self.Base.classes.relationship
        self.Parameter = self.Base.classes.parameter
        self.ParameterValue = self.Base.classes.parameter_value
        self.Commit = self.Base.classes.commit
        self.session = Session(self.engine)
        self.new_commit()

    def new_commit(self):
        """Add row to commit table"""
        comment = 'in progress'
        user = self.username
        date = datetime.now(timezone.utc)
        self.commit = self.Commit(comment=comment, date=date, user=user)
        self.session.add(self.commit)
        self.session.flush() # there shouldn't be any DBAPIError here


    def relationship_class_query(self, object_class_id):
        """Return relationship classes involving a given object class."""
        as_parent_query = self.session.query(
            self.RelationshipClass.id,
            self.RelationshipClass.name,
            self.RelationshipClass.child_object_class_id,
            self.RelationshipClass.parent_object_class_id
        ).filter_by(parent_object_class_id=object_class_id)
        as_child_query = self.session.query(
            self.RelationshipClass.id,
            self.RelationshipClass.name,
            self.RelationshipClass.parent_object_class_id.label('child_object_class_id'),
            self.RelationshipClass.child_object_class_id.label('parent_object_class_id')
        ).filter_by(parent_relationship_class_id=None).\
        filter_by(child_object_class_id=object_class_id)
        return {'as_parent': as_parent_query, 'as_child': as_child_query}

    def init_object_tree_model(self):
        """Initialize object tree model from source database."""
        self.object_tree_model.clear()
        db_name = self.database
        # create root item
        root_item = QStandardItem(db_name)
        self.bold_font = root_item.font()
        self.bold_font.setBold(True)
        root_item.setFont(self.bold_font)
        # get all object_classes
        for object_class in self.session.query(
                    self.ObjectClass.id,
                    self.ObjectClass.name,
                    self.ObjectClass.display_order,
                ).order_by(self.ObjectClass.display_order):
            # create object class item
            object_class_item = QStandardItem(object_class.name)
            object_class_item.setFont(self.bold_font)
            object_class_item.setData('object_class', Qt.UserRole)
            object_class_item.setData(object_class._asdict(), Qt.UserRole+1)
            # get objects of this class
            object_query = self.session.query(
                self.Object.id,
                self.Object.class_id,
                self.Object.name
            ).filter_by(class_id=object_class.id)
            # get relationship classes involving the present class
            relationship_class_query = self.relationship_class_query(object_class.id)
            # recursively populate branches
            for object_ in object_query:
                # create object item
                object_item = QStandardItem(object_.name)
                object_item.setData('object', Qt.UserRole)
                object_item.setData(object_._asdict(), Qt.UserRole+1)
                for relationship_class in relationship_class_query['as_parent']:
                    # create relationship class item
                    relationship_class_item = self.visit_relationship_class(
                        relationship_class,
                        object_,
                        role='parent'
                    )
                    relationship_class_item.setData('relationship_class', Qt.UserRole)
                    object_item.appendRow(relationship_class_item)
                for relationship_class in relationship_class_query['as_child']:
                    # create relationship class item
                    relationship_class_item = self.visit_relationship_class(
                        relationship_class,
                        object_,
                        role='child'
                    )
                    relationship_class_item.setData('relationship_class', Qt.UserRole)
                    object_item.appendRow(relationship_class_item)
                object_class_item.appendRow(object_item)
            root_item.appendRow(object_class_item)
        self.object_tree_model.appendRow(root_item)
        # setup object tree view
        self.ui.treeView_object.setModel(self.object_tree_model)
        self.ui.treeView_object.header().hide()
        self.ui.treeView_object.expand(root_item.index())
        self.ui.treeView_object.resizeColumnToContents(0)

    def visit_relationship_class(self, relationship_class, object_, role=None):
        """Recursive function to create branches for relationships of relationships.

        Args:
            relationship_class (KeyedTuple or dict): relationship class to explore
            object_ (KeyedTuple): parent object
        """
        # create relationship class item
        relationship_class_item = QStandardItem(relationship_class.name)
        relationship_class_item.setFont(self.bold_font)
        relationship_class_item.setData(relationship_class._asdict(), Qt.UserRole+1)
        # get relationship classes having this relationship class as parent
        # (in our current convention, relationship classes are never child classes
        # in other relationship classes --but this may change)
        new_relationship_class_query = self.session.query(
            self.RelationshipClass.id,
            self.RelationshipClass.name,
            self.RelationshipClass.child_object_class_id,
            self.RelationshipClass.parent_relationship_class_id
        ).filter_by(parent_relationship_class_id=relationship_class.id)
        if  'relationship_id' not in object_.keys():
            # the parent object is a 'first-class' object. In the tree, this
            # object is located directly beneath an object class
            if role == 'parent':
                # get new child objects in new relationship class
                # also save the relationship id for further tasks
                new_object_query = self.session.query(
                        self.Object.id,
                        self.Object.class_id,
                        self.Object.name,
                        self.Relationship.id.label('relationship_id')
                    ).filter(self.Object.id == self.Relationship.child_object_id).\
                    filter(self.Relationship.class_id == relationship_class.id).\
                    filter(self.Relationship.parent_object_id == object_.id)
            elif role == 'child':
                # get new child objects in new relationship class
                new_object_query = self.session.query(
                        self.Object.id,
                        self.Object.class_id,
                        self.Object.name,
                        self.Relationship.id.label('relationship_id')
                    ).filter(self.Object.id == self.Relationship.parent_object_id).\
                    filter(self.Relationship.class_id == relationship_class.id).\
                    filter(self.Relationship.child_object_id == object_.id)
        else:
            # the parent object is itself a 'related' object in other relationship
            # get new child objects in new relationship class
            new_object_query = self.session.query(
                self.Object.id,
                self.Object.class_id,
                self.Object.name,
                self.Relationship.id.label('relationship_id')
            ).filter(self.Object.id == self.Relationship.child_object_id).\
            filter(self.Relationship.class_id == relationship_class.id).\
            filter(self.Relationship.parent_relationship_id == object_.relationship_id)
        # recursively populate branches
        for new_object in new_object_query:
            # create child object item
            new_object_item = QStandardItem(new_object.name)
            new_object_item.setData('related_object', Qt.UserRole)
            new_object_item.setData(new_object._asdict(), Qt.UserRole+1)
            for new_relationship_class in new_relationship_class_query:
                # create next relationship class item
                new_relationship_class_item = self.visit_relationship_class(
                    new_relationship_class,
                    new_object
                )
                new_relationship_class_item.setData('meta_relationship_class', Qt.UserRole)
                new_object_item.appendRow(new_relationship_class_item)
            relationship_class_item.appendRow(new_object_item)
        return relationship_class_item


    def init_parameter_value_models(self):
        """Initialize parameter value models from source database."""
        # get all parameters
        parameter_value_subquery = self.session.query(
            self.Parameter.name.label('parameter_name'),
            self.ParameterValue.id.label('parameter_value_id'),
            self.ParameterValue.relationship_id,
            self.ParameterValue.object_id,
            self.ParameterValue.index,
            self.ParameterValue.value,
            self.ParameterValue.expression,
            self.ParameterValue.time_pattern,
            self.ParameterValue.time_series_id,
            self.ParameterValue.stochastic_model_id
        ).filter(self.Parameter.id == self.ParameterValue.parameter_id).subquery()

        # just add the object class_id and name (this below is effectively a join)
        object_parameter_value_list = self.session.query(
            self.Object.class_id.label('object_class_id'),
            self.ObjectClass.name.label('object_class_name'),
            parameter_value_subquery.c.object_id,
            self.Object.name.label('object_name'),
            parameter_value_subquery.c.parameter_value_id,
            parameter_value_subquery.c.parameter_name,
            parameter_value_subquery.c.index,
            parameter_value_subquery.c.value,
            parameter_value_subquery.c.expression,
            parameter_value_subquery.c.time_pattern,
            parameter_value_subquery.c.time_series_id,
            parameter_value_subquery.c.stochastic_model_id
        ).filter(self.Object.id == parameter_value_subquery.c.object_id).\
        filter(self.Object.class_id == self.ObjectClass.id).all()

        # here add the relationship_class_id and name,
        # parent relationship id and name, parent and child object id and name
        # (again this is a join)
        relationship = aliased(self.Relationship)
        parent_relationship = aliased(self.Relationship)
        parent_object = aliased(self.Object)
        child_object = aliased(self.Object)
        relationship_parameter_value_list = self.session.query(
            self.Relationship.class_id.label('relationship_class_id'),
            self.RelationshipClass.name.label('relationship_class_name'),
            self.Relationship.id.label('relationship_id'),
            self.Relationship.parent_relationship_id,
            self.Relationship.parent_object_id,
            self.Relationship.child_object_id,
            parent_relationship.name.label('parent_relationship_name'),
            parent_object.name.label('parent_object_name'),
            child_object.name.label('child_object_name'),
            parameter_value_subquery.c.parameter_value_id,
            parameter_value_subquery.c.parameter_name,
            parameter_value_subquery.c.index,
            parameter_value_subquery.c.value,
            parameter_value_subquery.c.expression,
            parameter_value_subquery.c.time_pattern,
            parameter_value_subquery.c.time_series_id,
            parameter_value_subquery.c.stochastic_model_id
        ).outerjoin(parameter_value_subquery, self.Relationship.id == parameter_value_subquery.c.relationship_id).\
        filter(self.Relationship.class_id == self.RelationshipClass.id).\
        outerjoin(parent_relationship, parent_relationship.id == self.Relationship.parent_relationship_id).\
        outerjoin(parent_object, parent_object.id == self.Relationship.parent_object_id).\
        filter(child_object.id == self.Relationship.child_object_id).all()

        if object_parameter_value_list:
            # get column names from the first row
            header = object_parameter_value_list[0].keys()
            object_parameter = [list(row._asdict().values()) for row in object_parameter_value_list]
            self.object_parameter_value_model.header = header
            self.object_parameter_value_model.reset_model(object_parameter)
            self.object_parameter_value_proxy.setSourceModel(self.object_parameter_value_model)

        if relationship_parameter_value_list:
            # get header from the first row
            header = relationship_parameter_value_list[0].keys()
            relationship_parameter = [list(row._asdict().values()) for row in relationship_parameter_value_list]
            self.relationship_parameter_value_model.header = header
            self.relationship_parameter_value_model.reset_model(relationship_parameter)
            self.relationship_parameter_value_proxy.setSourceModel(self.relationship_parameter_value_model)

    def init_parameter_value_views(self):
        self.init_object_parameter_value_view()
        self.init_relationship_parameter_value_view()

    def init_object_parameter_value_view(self):
        """Init the object parameter table view.
        """
        header = self.object_parameter_value_model.header
        if not header:
            return
        # set column resize mode
        self.ui.tableView_object_parameter_value.horizontalHeader().\
            setSectionResizeMode(QHeaderView.ResizeToContents)
        # set model
        self.ui.tableView_object_parameter_value.setModel(self.object_parameter_value_proxy)
        # hide id columns
        self.ui.tableView_object_parameter_value.hideColumn(header.index("object_class_id"))
        self.ui.tableView_object_parameter_value.hideColumn(header.index("object_id"))
        self.ui.tableView_object_parameter_value.hideColumn(header.index("parameter_value_id"))
        # create line edit delegate and connect signals
        lineedit_delegate = LineEditDelegate(self)
        lineedit_delegate.closeEditor.connect(self.update_parameter_value)
        self.ui.tableView_object_parameter_value.setItemDelegate(lineedit_delegate)
        # create combobox delegate and connect signals
        combobox_delegate = ComboBoxDelegate(self)
        combobox_delegate.commit_data.connect(self.new_parameter_value_)
        combobox_delegate.closeEditor.connect(self.new_parameter_value_)
        self.ui.tableView_object_parameter_value.\
            setItemDelegateForColumn(header.index("parameter_name"), combobox_delegate)

    def init_relationship_parameter_value_view(self):
        """Init the relationship parameter table view.
        """
        header = self.relationship_parameter_value_model.header
        if not header:
            return
        # set column resize mode
        self.ui.tableView_relationship_parameter_value.horizontalHeader().\
            setSectionResizeMode(QHeaderView.ResizeToContents)
        # set model
        self.ui.tableView_relationship_parameter_value.setModel(self.relationship_parameter_value_proxy)
        # hide id columns
        self.ui.tableView_relationship_parameter_value.hideColumn(header.index("relationship_class_id"))
        self.ui.tableView_relationship_parameter_value.hideColumn(header.index("parent_relationship_id"))
        self.ui.tableView_relationship_parameter_value.hideColumn(header.index("parent_object_id"))
        self.ui.tableView_relationship_parameter_value.hideColumn(header.index("child_object_id"))
        self.ui.tableView_relationship_parameter_value.hideColumn(header.index("relationship_id"))
        self.ui.tableView_relationship_parameter_value.hideColumn(header.index("parameter_value_id"))


    def object_class_parameter_names(self, object_class_id, object_id):
        """Return unassigned parameter names for object class

        Args:
            object_class_id (int): object class id
            object_id (int): object id
        """
        # Note: for new relationship parameters don't do it here,
        # just create another method
        parameter_name_query = self.session.query(self.Parameter.name).\
            filter_by(object_class_id=object_class_id).\
            filter( # filter out parameters already assigned
                ~self.Parameter.id.in_(
                    self.session.query(self.ParameterValue.parameter_id).\
                    filter_by(object_id=object_id)
                )
            )
        return [row.name for row in parameter_name_query]

    @Slot("QModelIndex", "QModelIndex", name="update_object_parameter_value_selection")
    def update_object_parameter_value_selection(self, selected, deselected):
        """Select the entire row when the current index lays in definition columns"""
        current = self.ui.tableView_object_parameter_value.currentIndex()
        header = self.object_parameter_value_model.header
        col1 = header.index("object_class_name")
        col2 = header.index("object_name")
        col3 = header.index("parameter_name")
        if current.column() not in (col1, col2, col3):
            return
        self.ui.tableView_object_parameter_value.selectRow(current.row())


    @Slot("QModelIndex", name="expand_at_top_level")
    def expand_at_top_level(self, index):
        """Expand object at the top level"""
        # logging.debug("expand_at_top_level leaf")
        if not index.isValid():
            return # just to be safe
        clicked_type = index.data(Qt.UserRole)
        if not clicked_type.endswith('object'):
            return
        clicked_item = index.model().itemFromIndex(index)
        if clicked_item.hasChildren():
            return
        self.expand_at_top_level_(index)

    def expand_at_top_level_(self, index):
        """Expand object at the top level (suite)"""
        clicked_object = index.data(Qt.UserRole+1)
        root_item = index.model().invisibleRootItem().child(0)
        founded_object_class_item = None
        for i in range(root_item.rowCount()):
            object_class_item = root_item.child(i)
            object_class = object_class_item.data(Qt.UserRole+1)
            if object_class['id'] == clicked_object['class_id']:
                founded_object_class_item = object_class_item
                break
        if not founded_object_class_item:
            return
        for j in range(founded_object_class_item.rowCount()):
            object_item = founded_object_class_item.child(j)
            object_ = object_item.data(Qt.UserRole+1)
            if object_['id'] == clicked_object['id']:
                object_index = index.model().indexFromItem(object_item)
                self.ui.treeView_object.setCurrentIndex(object_index)
                self.ui.treeView_object.scrollTo(object_index)
                self.ui.treeView_object.expand(object_index)
                return

    @Slot("QModelIndex", "QModelIndex", name="filter_parameter_models")
    def filter_parameter_models(self, current, previous):
        """Populate tableViews whenever an object item is selected in the treeView"""
        # TODO: try to make it more sparse
        # logging.debug("filter_parameter_models")
        self.object_parameter_value_proxy.clear_filter()
        self.relationship_parameter_value_proxy.clear_filter()
        clicked_type = current.data(Qt.UserRole)
        header = self.relationship_parameter_value_model.header
        # row filter
        if clicked_type == 'object_class': # show all objects of this class
            object_class_id = current.data(Qt.UserRole+1)['id']
            self.object_parameter_value_proxy.object_class_id_filter = object_class_id
        elif clicked_type == 'object': # show only this object
            # filter rows
            object_id = current.data(Qt.UserRole+1)['id']
            self.object_parameter_value_proxy.object_id_filter = object_id
            self.relationship_parameter_value_proxy.object_id_filter = object_id
            # filter columns
            self.relationship_parameter_value_proxy.hide_column = header.index("parent_relationship_name")
        elif clicked_type == 'relationship_class':
            # show all related objects to this parent object, through this relationship class
            # filter rows
            parent_object_id = current.parent().data(Qt.UserRole+1)['id']
            relationship_class_id = current.data(Qt.UserRole+1)['id']
            self.relationship_parameter_value_proxy.object_id_filter = parent_object_id
            self.relationship_parameter_value_proxy.relationship_class_id_filter = relationship_class_id
            # filter columns
            self.relationship_parameter_value_proxy.hide_column = header.index("parent_relationship_name")
        elif clicked_type == 'related_object':
            # show only this object and this relationship
            # filter rows
            object_id = current.data(Qt.UserRole+1)['id']
            relationship_id = current.data(Qt.UserRole+1)['relationship_id']
            self.object_parameter_value_proxy.object_id_filter = object_id
            self.relationship_parameter_value_proxy.relationship_id_filter = relationship_id
            #filter columns
            relationship_class_type = current.parent().data(Qt.UserRole)
            if relationship_class_type == 'meta_relationship_class': # hide parent_object_name
                self.relationship_parameter_value_proxy.hide_column = header.index("parent_object_name")
            elif relationship_class_type == 'relationship_class': # hide parent_relationship_name
                self.relationship_parameter_value_proxy.hide_column = header.index("parent_relationship_name")
        elif clicked_type == 'meta_relationship_class':
            # show all related objects to this parent relationship, through this meta-relationship class
            # filter rows
            parent_relationship_id = current.parent().data(Qt.UserRole+1)['relationship_id']
            relationship_class_id = current.data(Qt.UserRole+1)['id']
            self.relationship_parameter_value_proxy.parent_relationship_id_filter = parent_relationship_id
            self.relationship_parameter_value_proxy.relationship_class_id_filter = relationship_class_id
            # filter columns
            self.relationship_parameter_value_proxy.hide_column = header.index("parent_object_name")
        # trick to trigger filtering
        self.object_parameter_value_proxy.setFilterRegExp("")
        self.relationship_parameter_value_proxy.setFilterRegExp("")

    @Slot("QPoint", name="show_object_tree_context_menu")
    def show_object_tree_context_menu(self, pos):
        """Context menu for object tree.

        Args:
            pos (QPoint): Mouse position
        """
        # logging.debug("object tree context menu")
        index = self.ui.treeView_object.indexAt(pos)
        global_pos = self.ui.treeView_object.viewport().mapToGlobal(pos)
        self.object_tree_context_menu = ObjectTreeContextMenu(self, global_pos, index)#
        option = self.object_tree_context_menu.get_action()
        if option == "New object class":
            self.new_object_class(index)
        elif option == "New object":
            self.new_object(index)
        elif option == "New relationship class":
            self.new_relationship_class(index)
        elif option == "New relationship":
            self.new_relationship(index)
        elif option == "Expand at top level":
            self.expand_at_top_level_(index)
        elif option == "Rename":
            self.rename_item(index)
        elif option == "Remove":
            self.remove_item(index)
        elif option == "New parameter value":
            self.new_parameter_value(index)
        else:  # No option selected
            pass
        self.object_tree_context_menu.deleteLater()
        self.object_tree_context_menu = None


    def new_object_class(self, index):
        """Insert new object class.

        Args:
            index (QModelIndex): the index of either the root or an object class item
        """
        dialog = CustomQDialog(self, "New object class",
            name="Type name here...",
            description="Type description here...")
        answer = dialog.exec_()
        if answer != QDialog.Accepted:
            return
        name = dialog.answer["name"]
        description = dialog.answer["description"]
        if index.parent().isValid(): # we are on an object class item
            # prepare to insert the new item just before the selected one
            root_item = index.model().itemFromIndex(index.parent())
            insert_at_row = index.row()
            child_item = root_item.child(insert_at_row)
            display_order = child_item.data(Qt.UserRole+1)['display_order'] - 1
        else: # we are on the root item
            # prepare to insert the new item and the end
            root_item = index.model().itemFromIndex(index)
            insert_at_row = root_item.rowCount()
            child_item = root_item.child(insert_at_row - 1)
            display_order = child_item.data(Qt.UserRole+1)['display_order']
        object_class = self.ObjectClass(
            name=name,
            description=description,
            display_order=display_order,
            commit_id=self.commit.id
        )
        self.session.add(object_class)
        try:
            self.session.flush() # to get object class id
        except DBAPIError as e:
            msg = "Could not insert new object class: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually add item to model as well
        object_class_item = QStandardItem(name)
        object_class_item.setFont(self.bold_font)
        object_class_item.setData('object_class', Qt.UserRole)
        object_class_item.setData(object_class.__dict__, Qt.UserRole+1)
        root_item.insertRow(insert_at_row, QStandardItem())
        root_item.setChild(insert_at_row, 0, object_class_item)
        # scroll to newly inserted item in treeview
        object_class_index = index.model().indexFromItem(object_class_item)
        self.ui.treeView_object.setCurrentIndex(object_class_index)
        self.ui.treeView_object.scrollTo(object_class_index)

    def new_object(self, index):
        """Insert new object.

        Args:
            index (QModelIndex): the index of an object class item
        """
        dialog = CustomQDialog(self, "New object",
            name="Type name here...",
            description="Type description here...")
        answer = dialog.exec_()
        if answer != QDialog.Accepted:
            return
        object_class_item = index.model().itemFromIndex(index)
        name = dialog.answer["name"]
        description = dialog.answer["description"]
        class_id = object_class_item.data(Qt.UserRole+1)['id']
        object_ = self.Object(
            class_id=class_id,
            name=name,
            description=description,
            commit_id=self.commit.id
        )
        self.session.add(object_)
        try:
            self.session.flush() # to get object id
        except DBAPIError as e:
            msg = "Could not insert new object: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually add item to model as well
        object_class = object_class_item.data(Qt.UserRole+1)
        object_item = QStandardItem(name)
        object_item.setData('object', Qt.UserRole)
        object_item.setData(object_.__dict__, Qt.UserRole+1)
        # get relationship classes involving the present object class
        relationship_class_query = self.relationship_class_query(object_class['id'])
        relationship_class_query = relationship_class_query['as_parent'].\
                                    union(relationship_class_query['as_child'])
        # create and append relationship class items
        for relationship_class in relationship_class_query:
            # no need to visit the relationship class here,
            # since this object does not have any relationships yet
            relationship_class_item = QStandardItem(relationship_class.name)
            relationship_class_item.setFont(self.bold_font)
            relationship_class_item.setData('relationship_class', Qt.UserRole)
            relationship_class_item.setData(relationship_class._asdict(), Qt.UserRole+1)
            object_item.appendRow(relationship_class_item)
        object_class_item.appendRow(object_item)
        # scroll to newly inserted item in treeview
        object_index = index.model().indexFromItem(object_item)
        self.ui.treeView_object.setCurrentIndex(object_index)
        self.ui.treeView_object.scrollTo(object_index)

    def new_relationship_class(self, index):
        """Insert new relationship class.

        Args:
            index (QModelIndex): the index of an object or relationship class item
        """
        # query object_class table
        child_object_class_query = self.session.query(self.ObjectClass).\
                order_by(self.ObjectClass.display_order)
        child_object_class_name_list = ['Select child object class...']
        child_object_class_name_list.extend([item.name for item in child_object_class_query])
        dialog = CustomQDialog(self, "New relationship class",
            name="Type name here...",
            child_object_class_name_list=child_object_class_name_list)
        answer = dialog.exec_()
        if answer != QDialog.Accepted:
            return
        name = dialog.answer['name']
        # get information about the parent
        parent_class_item = index.model().itemFromIndex(index)
        parent_type = parent_class_item.data(Qt.UserRole)
        parent_class = parent_class_item.data(Qt.UserRole+1)
        if parent_type.endswith('relationship_class'):
            parent_relationship_class_id = parent_class['id']
            parent_object_class_id = None
            relationship_class_type = 'meta_relationship_class'
        elif parent_type == 'object_class':
            parent_relationship_class_id = None
            parent_object_class_id = parent_class['id']
            relationship_class_type = 'relationship_class'
        # and about the child
        # get selected index from combobox, to look it up in child_class_list
        ind = dialog.answer['child_object_class_name_list']['index'] - 1
        child_object_class_id = child_object_class_query[ind].id
        relationship_class = self.RelationshipClass(
            name=name,
            parent_relationship_class_id=parent_relationship_class_id,
            parent_object_class_id=parent_object_class_id,
            child_object_class_id=child_object_class_id,
            commit_id=self.commit.id
        )
        self.session.add(relationship_class)
        try:
            self.session.flush() # to get the relationship class id
        except DBAPIError as e:
            msg = "Could not insert new relationship class: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually add items to model
        # append new relationship class item to objects of parent_class
        relationship_class_dict = relationship_class.__dict__
        for row in range(parent_class_item.rowCount()):
            object_item = parent_class_item.child(row)
            relationship_class_item = QStandardItem(name)
            relationship_class_item.setFont(self.bold_font)
            relationship_class_item.setData(relationship_class_type, Qt.UserRole)
            relationship_class_item.setData(relationship_class_dict, Qt.UserRole+1)
            object_item.appendRow(relationship_class_item)
        # ...and to objects of child class if relationship class is between object classes
        if relationship_class_type != 'relationship_class':
            return
        # find child_class_item in the first level
        root_item = index.model().invisibleRootItem().child(0)
        founded_object_class_item = None
        for row in range(root_item.rowCount()):
            object_class_item = root_item.child(row)
            object_class = object_class_item.data(Qt.UserRole+1)
            if object_class['id'] == child_object_class_id:
                founded_object_class_item = object_class_item
                break
        if not founded_object_class_item:
            return
        for row in range(founded_object_class_item.rowCount()):
            object_item = founded_object_class_item.child(row)
            relationship_class_item = QStandardItem(name)
            relationship_class_item.setFont(self.bold_font)
            relationship_class_item.setData('relationship_class', Qt.UserRole)
            # invert relationship class and save it
            relationship_class_dict['child_object_class_id'] = parent_object_class_id
            relationship_class_dict['parent_object_class_id'] = child_object_class_id
            relationship_class_item.setData(relationship_class_dict, Qt.UserRole+1)
            object_item.appendRow(relationship_class_item)
        # now it seems meaningless to scroll somewhere

    def new_relationship(self, index):
        """Insert new relationship.

        Args:
            index (QModelIndex): the index of a relationship class item
        """
        relationship_class_item = index.model().itemFromIndex(index)
        relationship_class_type = relationship_class_item.data(Qt.UserRole)
        relationship_class = relationship_class_item.data(Qt.UserRole+1)
        child_object_class_id = relationship_class['child_object_class_id']
        child_object_query = self.session.query(self.Object).\
            filter_by(class_id=child_object_class_id)
        if not child_object_query.first():
            child_object_class_name = self.session.query(self.ObjectClass).\
                filter_by(id=child_object_class_id).one().name
            msg = "There are no objects of child class {}.".format(child_object_class_name)
            self.statusbar.showMessage(msg, 3000)
            return
        child_object_name_list = ['Select child object...']
        child_object_name_list.extend([item.name for item in child_object_query])
        dialog = CustomQDialog(self, "New relationship",
            name="Type name here...",
            child_object_name_list=child_object_name_list)
        answer = dialog.exec_()
        if answer != QDialog.Accepted:
            return
        class_id = relationship_class['id']
        name = dialog.answer["name"]
        parent_object_item = index.model().itemFromIndex(index.parent())
        parent_object_type = parent_object_item.data(Qt.UserRole)
        parent_object = parent_object_item.data(Qt.UserRole+1)
        if parent_object_type == 'related_object':
            parent_relationship_id = parent_object['relationship_id']
            parent_object_id = None
        elif parent_object_type == 'object':
            parent_relationship_id = None
            parent_object_id = parent_object['id']
        # get selected index from combobox, to look it up in child_object_list
        ind = dialog.answer['child_object_name_list']['index'] - 1
        child_object_id = child_object_query[ind].id
        relationship = self.Relationship(
            class_id=class_id,
            name=name,
            parent_relationship_id=parent_relationship_id,
            parent_object_id=parent_object_id,
            child_object_id=child_object_id
        )
        self.session.add(relationship)
        try:
            self.session.flush() # to get the relationship id
        except DBAPIError as e:
            msg = "Could not insert new relationship: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # alternative 1, rebuild the whole model
        # self.init_object_tree_model()
        # alternative 2, manually add items to model
        # (pros: faster, doesn't collapse all items. cons: uglier, harder to maintain?)
        # add child object item to relationship class...
        # create new object
        new_object_name = dialog.answer['child_object_name_list']['text']
        new_object_item = QStandardItem(new_object_name)
        # query object table to get new object directly as dict
        new_object = self.session.query(
            self.Object.id,
            self.Object.class_id,
            self.Object.name
        ).filter_by(id=child_object_id).one_or_none()._asdict()
        # add parent relationship id manually
        # (this is better than joining relationship table in the query above)
        new_object['relationship_id'] = relationship.id
        new_object_item.setData('related_object', Qt.UserRole)
        new_object_item.setData(new_object, Qt.UserRole+1)
        # get relationship classes having the present relationship class as parent
        new_relationship_class_query = self.session.query(
            self.RelationshipClass.id,
            self.RelationshipClass.name,
            self.RelationshipClass.child_object_class_id,
            self.RelationshipClass.parent_relationship_class_id
        ).filter_by(parent_relationship_class_id=relationship_class['id'])
        # create and append relationship class items
        for new_relationship_class in new_relationship_class_query:
            new_relationship_class_item = self.visit_relationship_class(
                new_relationship_class,
                new_object
            )
            new_relationship_class_item.setData('meta_relationship_class', Qt.UserRole)
            new_object_item.appendRow(new_relationship_class_item)
        relationship_class_item.appendRow(new_object_item)
        # scroll to newly inserted item in treeview
        new_object_index = index.model().indexFromItem(new_object_item)
        self.ui.treeView_object.setCurrentIndex(new_object_index)
        self.ui.treeView_object.scrollTo(new_object_index)
        # ...and if parent class is an object class,
        # then add child object item to inverse relationship class...
        if relationship_class_type != 'relationship_class':
            return
        # find inverse relationship class item by traversing the tree from the root
        root_item = index.model().invisibleRootItem().child(0)
        founded_relationship_class_item = None
        founded_object_class_item = None
        founded_object_item = None
        for i in range(root_item.rowCount()):
            object_class_item = root_item.child(i)
            object_class = object_class_item.data(Qt.UserRole+1)
            if object_class['id'] == child_object_class_id:
                founded_object_class_item = object_class_item
                break
        if not founded_object_class_item:
            return
        for j in range(founded_object_class_item.rowCount()):
            object_item = founded_object_class_item.child(j)
            object_ = object_item.data(Qt.UserRole+1)
            if object_['id'] == child_object_id:
                founded_object_item = object_item
                break
        if not founded_object_item:
            return
        for k in range(object_item.rowCount()):
            relationship_class_item = object_item.child(k)
            relationship_class = relationship_class_item.data(Qt.UserRole+1)
            if relationship_class['id'] == class_id:
                founded_relationship_class_item = relationship_class_item
                break
        if not founded_relationship_class_item:
            return
        # create new object
        new_object_item = QStandardItem(parent_object['name'])
        # query object table to get new object directly as dict
        new_object = self.session.query(
            self.Object.id,
            self.Object.class_id,
            self.Object.name
        ).filter_by(id=parent_object_id).one_or_none()._asdict()
        # add parent relationship id manually
        new_object['relationship_id'] = relationship.id
        new_object_item.setData('object', Qt.UserRole)
        new_object_item.setData(new_object, Qt.UserRole+1)
        # create and append relationship class items
        for new_relationship_class in new_relationship_class_query:
            new_relationship_class_item = self.visit_relationship_class(
                new_relationship_class,
                new_object
            )
            new_relationship_class_item.setData('relationship_class', Qt.UserRole)
            new_object_item.appendRow(new_relationship_class_item)
        founded_relationship_class_item.appendRow(new_object_item)

    def rename_item(self, index):
        """Rename item in the database and treeview"""
        item = index.model().itemFromIndex(index)
        name = item.text()
        answer = QInputDialog.getText(self, "Rename item", "Enter new name:",\
            QLineEdit.Normal, name)
        new_name = answer[0]
        if not new_name: # cancel clicked
            return
        if new_name == name: # nothing to do here
            return
        # find out which table
        entity_type = item.data(Qt.UserRole)
        if entity_type == 'object_class':
            table = self.ObjectClass
        elif entity_type.endswith('object'):
            table = self.Object
        elif entity_type.endswith('relationship_class'):
            table = self.RelationshipClass
        else:
            return # should never happen
        # get item from table
        entity = item.data(Qt.UserRole+1)
        instance = self.session.query(table).filter_by(id=entity['id']).one_or_none()
        if not instance:
            return
        instance.name = new_name
        instance.commit_id = self.commit.id
        try:
            self.session.flush()
        except DBAPIError as e:
            msg = "Could not rename item: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually rename all items in model
        items = index.model().findItems(name, Qt.MatchRecursive)
        for it in items:
            ent_type = it.data(Qt.UserRole)
            ent = it.data(Qt.UserRole+1)
            if (ent_type in entity_type or entity_type in ent_type)\
                    and ent['id'] == entity['id']:
                ent['name'] = new_name
                it.setText(new_name)

    def remove_item(self, index):
        """Remove item from the treeview"""
        item = index.model().itemFromIndex(index)
        # find out which table
        entity_type = item.data(Qt.UserRole)
        if entity_type == 'object_class':
            table = self.ObjectClass
        elif entity_type.endswith('object'):
            table = self.Object
        elif entity_type.endswith('relationship_class'):
            table = self.RelationshipClass
        else:
            return # should never happen
        # get item from table
        entity = item.data(Qt.UserRole+1)
        instance = self.session.query(table).filter_by(id=entity['id']).one_or_none()
        if not instance:
            return
        self.session.delete(instance)
        try:
            self.session.flush()
        except DBAPIError as e:
            msg = "Could not insert new relationship class: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually remove all items in model
        def visit_and_remove(it):
            """Visit item, remove it if necessary and visit children.

            Returns:
                True if item was removed, False otherwise
            """
            # visit children
            i = 0
            while True:
                if i == it.rowCount(): # all children have been visited
                    break
                if not visit_and_remove(it.child(i)): # visit next children
                    i += 1 # increment counter only if children wasn't removed
            # visit item
            ent_type = it.data(Qt.UserRole)
            ent = it.data(Qt.UserRole+1)
            if not ent_type: # root item
                return False
            if ent_type == entity_type and ent['id'] == entity['id']:
                ind = index.model().indexFromItem(it)
                index.model().removeRows(ind.row(), 1, ind.parent())
                return True
            if ent_type.endswith('relationship_class'):
                child_object_class_id = ent['child_object_class_id']
                if child_object_class_id == entity['id']:
                    ind = index.model().indexFromItem(it)
                    index.model().removeRows(ind.row(), 1, ind.parent())
                    return True
            return False
        root_item = index.model().invisibleRootItem().child(0)
        visit_and_remove(root_item)


    @Slot("QPoint", name="show_object_parameter_value_context_menu")
    def show_object_parameter_value_context_menu(self, pos):
        """Context menu for object parameter table view.

        Args:
            pos (QPoint): Mouse position
        """
        #logging.debug("object parameter value context menu")
        index = self.ui.tableView_object_parameter_value.indexAt(pos)
        global_pos = self.ui.tableView_object_parameter_value.viewport().mapToGlobal(pos)
        self.object_parameter_value_context_menu = ObjectParameterValueContextMenu(self, global_pos, index)
        option = self.object_parameter_value_context_menu.get_action()
        if option == "New parameter value":
            self.new_parameter_value(index)
        elif option == "Remove":
            self.remove_parameter_value(index)
        elif option == "Edit field":
            self.ui.tableView_object_parameter_value.edit(index)

    def new_parameter_value(self, tree_index):
        """Prepare to insert new parameter value. Insert object and object class
        fields, and open editor to request for parameter name.
        """
        model = self.object_parameter_value_model
        # find out parameter names
        tree_index_data = tree_index.data(Qt.UserRole+1)
        object_class_id = tree_index_data['class_id']
        object_id = tree_index_data['id']
        parameter_names = self.object_class_parameter_names(object_class_id, object_id)
        if not parameter_names:
            self.statusbar.showMessage("All parameters for this object are already created", 3000)
            return
        # insert new row
        last_row = model.rowCount()
        if not model.insertRows(last_row, 1):
            return
        row = model.rowCount()-1
        tree_parent_data = tree_index.parent().data(Qt.UserRole+1)
        # add object_class_id
        column = model.header.index("object_class_id")
        index = model.index(row, column)
        model.setData(index, object_class_id)
        # add object_class_name
        column = model.header.index("object_class_name")
        index = model.index(row, column)
        model.setData(index, tree_parent_data['name'])
        # add object_id
        column = model.header.index("object_id")
        index = model.index(row, column)
        model.setData(index, object_id)
        # add object_name
        column = model.header.index("object_name")
        index = model.index(row, column)
        model.setData(index, tree_index_data['name'])
        # store parameter names in proxy index's Qt.UserRole
        column = model.header.index("parameter_name")
        index = model.index(row, column)
        self.filter_parameter_models(tree_index, tree_index)
        proxy_index = self.object_parameter_value_proxy.mapFromSource(index)
        self.object_parameter_value_proxy.setData(proxy_index, parameter_names, Qt.UserRole)
        # edit
        self.ui.tableView_object_parameter_value.setCurrentIndex(proxy_index)
        self.ui.tableView_object_parameter_value.adding_new_parameter_value = True
        self.ui.tableView_object_parameter_value.edit(proxy_index)


    @Slot("CustomComboEditor", name="new_parameter_value_")
    def new_parameter_value_(self, combo):
        """Insert new parameter value.
        If successful, also add parameter value to model.
        """
        logging.debug("new parameter value")
        index = self.object_parameter_value_proxy.index(combo.row, combo.column)
        parameter_name = combo.currentText()
        if not parameter_name: # user didn't select a parameter name from combobox
            self.object_parameter_value_proxy.removeRows(index.row(), 1)
            return
        # get object_id
        column = self.object_parameter_value_model.header.index("object_id")
        object_id = index.sibling(index.row(), column).data()
        # get parameter_id
        parameter = self.session.query(self.Parameter.id).\
            filter_by(name=parameter_name).one_or_none()
        if not parameter:
            return
        parameter_value = self.ParameterValue(
            object_id=object_id,
            parameter_id=parameter.id,
            commit_id=self.commit.id
        )
        self.session.add(parameter_value)
        try:
            self.session.flush()
        except DBAPIError as e:
            msg = "Could not insert parameter: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually add item in model
        # parameter_value.id
        id_column = self.object_parameter_value_model.header.index("parameter_value_id")
        id_index = index.sibling(index.row(), id_column)
        source_id_index = self.object_parameter_value_proxy.mapToSource(id_index)
        self.object_parameter_value_model.setData(source_id_index, parameter_value.id)
        # parameter name
        source_index = self.object_parameter_value_proxy.mapToSource(index)
        self.object_parameter_value_model.setData(source_index, parameter_name)


    @Slot("QWidget", "QAbstractItemDelegate.EndEditHint", name="update_parameter_value")
    def update_parameter_value(self, editor, hint):
        """Update parameter_value table with newly edited data.
        If successful, also update item in the model.
        """
        logging.debug("update parameter value")
        editor.close()
        index = self.ui.tableView_object_parameter_value.currentIndex()
        header = self.object_parameter_value_model.header
        id_column = header.index('parameter_value_id')
        sibling = index.sibling(index.row(), id_column)
        parameter_value_id = sibling.data()
        parameter_value = self.session.query(self.ParameterValue).\
            filter_by(id=parameter_value_id).one_or_none()
        if not parameter_value:
            logging.debug("entry not found in parameter_value table")
            return
        field_name = header[index.column()]
        value = getattr(parameter_value, field_name)
        data_type = type(value)
        try:
            new_value = data_type(editor.text())
        except ValueError:
            # Note: try to avoid this by setting up a good validator in line edit delegate
            self.ui.statusbar.showMessage("The value entered doesn't fit the datatype.")
            return
        if value == new_value:
            logging.debug("parameter value not changed")
            return
        setattr(parameter_value, field_name, new_value)
        parameter_value.commit_id = self.commit.id
        try:
            self.session.flush()
        except DBAPIError as e:
            msg = "Could not update parameter: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually update item in model
        source_index = self.object_parameter_value_proxy.mapToSource(index)
        self.object_parameter_value_model.setData(source_index, new_value)

    def remove_parameter_value(self, index):
        """Remove row from parameter_value table.
        If succesful, also remove row from model"""
        id_column = self.object_parameter_value_model.header.index('parameter_value_id')
        sibling = index.sibling(index.row(), id_column)
        parameter_value_id = sibling.data()
        parameter_value = self.session.query(self.ParameterValue).\
            filter_by(id=parameter_value_id).one_or_none()
        if not parameter_value:
            logging.debug("entry not found in parameter_value table")
            return
        self.session.delete(parameter_value)
        try:
            self.session.flush()
        except DBAPIError as e:
            msg = "Could not remove parameter: {}".format(e.orig.args)
            self.statusbar.showMessage(msg, 5000)
            self.session.rollback()
            return
        # manually remove row from model
        self.object_parameter_value_proxy.removeRows(index.row(), 1)


    def restore_ui(self):
        """Restore UI state from previous session."""
        window_size = self.qsettings.value("mainWindow/windowSize")
        window_pos = self.qsettings.value("mainWindow/windowPosition")
        splitter_tree_parameter_state = self.qsettings.value("mainWindow/splitterTreeParameterState")
        window_maximized = self.qsettings.value("mainWindow/windowMaximized", defaultValue='false')  # returns string
        if window_size:
            self.resize(window_size)
        if window_pos:
            self.move(window_pos)
        if window_maximized == 'true':
            self.setWindowState(Qt.WindowMaximized)
        if splitter_tree_parameter_state:
            self.ui.splitter_tree_parameter.restoreState(splitter_tree_parameter_state)


    @Slot(name="close_clicked")
    def close_clicked(self):
        """Close this form without commiting any changes."""
        self.close()

    def keyPressEvent(self, e):
        """Close Setup form when escape key is pressed.

        Args:
            e (QKeyEvent): Received key press event.
        """
        if e.key() == Qt.Key_Escape:
            self.close()

    def closeEvent(self, event=None):
        """Handle close window.

        Args:
            event (QEvent): Closing event if 'X' is clicked.
        """
        # save qsettings
        self.qsettings.setValue("mainWindow/splitterTreeParameterState", self.ui.splitter_tree_parameter.saveState())
        self.qsettings.setValue("mainWindow/windowSize", self.size())
        self.qsettings.setValue("mainWindow/windowPosition", self.pos())
        if self.windowState() == Qt.WindowMaximized:
            self.qsettings.setValue("mainWindow/windowMaximized", True)
        else:
            self.qsettings.setValue("mainWindow/windowMaximized", False)
        # close sql session
        if self.session:
            self.session.rollback()
            self.session.close()
        if self.engine:
                self.engine.dispose()
        if event:
            event.accept()
