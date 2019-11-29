######################################################################################################################
# Copyright (C) 2017 - 2019 Spine project consortium
# This file is part of Spine Toolbox.
# Spine Toolbox is free software: you can redistribute it and/or modify it under the terms of the GNU Lesser General
# Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option)
# any later version. This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
# without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Lesser General
# Public License for more details. You should have received a copy of the GNU Lesser General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.
######################################################################################################################

"""
Spine Toolbox project class.

:authors: P. Savolainen (VTT), E. Rinne (VTT)
:date:   10.1.2018
"""

import os
import logging
import json
from PySide2.QtCore import Slot
from .metaobject import MetaObject
from .helpers import create_dir
from .tool_specifications import JuliaTool, PythonTool, GAMSTool, ExecutableTool
from .config import LATEST_PROJECT_VERSION, PROJECT_FILENAME
from .executioner import DirectedGraphHandler, ExecutionInstance, ExecutionState, ResourceMap
from .spine_db_manager import SpineDBManager


class SpineToolboxProject(MetaObject):
    """Class for Spine Toolbox projects."""

    def __init__(self, toolbox, name, description, p_dir):
        """

        Args:
            toolbox (ToolboxUI): toolbox of this project
            name (str): Project name
            description (str): Project description
            p_dir (str): Project directory
        """
        super().__init__(name, description)
        self._toolbox = toolbox
        self._qsettings = self._toolbox.qsettings()
        self.dag_handler = DirectedGraphHandler(self._toolbox)
        self.db_mngr = SpineDBManager(self)
        self._ordered_dags = dict()  # Contains all ordered lists of items to execute in the project
        self.execution_instance = None
        self._graph_index = 0
        self._n_graphs = 0
        self._executed_graph_index = 0
        self._invalid_graphs = list()
        self.dirty = False  # TODO: Indicates if project has changed since loading
        self.project_dir = None  # Full path to project directory
        self.config_dir = None  # Full path to .spinetoolbox directory
        self.items_dir = None  # Full path to items directory
        self.config_file = None  # Full path to .spinetoolbox/project.json file
        if not self._create_project_structure(p_dir):
            self._toolbox.msg_error.emit("Creating project directory "
                                         "structure to <b>{0}</b> failed"
                                         .format(p_dir))

    def connect_signals(self):
        """Connect signals to slots."""
        self.dag_handler.dag_simulation_requested.connect(self.notify_changes_in_dag)

    def _create_project_structure(self, directory):
        """Makes the given directory a Spine Toolbox project directory.
        Creates directories and files that are common to all projects.

        Args:
            directory (str): Abs. path to a directory that should be made into a project directory

        Returns:
            bool: True if project structure was created successfully, False otherwise
        """
        self.project_dir = directory
        self.config_dir = os.path.abspath(os.path.join(self.project_dir, ".spinetoolbox"))
        self.items_dir = os.path.abspath(os.path.join(self.config_dir, "items"))
        self.config_file = os.path.abspath(os.path.join(self.config_dir, PROJECT_FILENAME))
        try:
            create_dir(self.project_dir)  # Make project directory
        except OSError:
            self._toolbox.msg_error.emit("Creating directory {0} failed".format(self.project_dir))
            return False
        try:
            create_dir(self.config_dir)  # Make project config directory
        except OSError:
            self._toolbox.msg_error.emit("Creating directory {0} failed".format(self.config_dir))
            return False
        try:
            create_dir(self.items_dir)  # Make project items directory
        except OSError:
            self._toolbox.msg_error.emit("Creating directory {0} failed".format(self.items_dir))
            return False
        return True

    def change_name(self, name):
        """Changes project name.

        Args:
            name (str): New project name
        """
        super().set_name(name)
        # Update Window Title
        self._toolbox.setWindowTitle("Spine Toolbox    -- {} --".format(self.name))
        self._toolbox.msg.emit("Project name changed to <b>{0}</b>".format(self.name))

    def save(self, tool_def_paths):
        """Collect project information and project items
        into a dictionary and write to a JSON file.

        Args:
            tool_def_paths (list): List of absolute paths to tool specification files

        Returns:
            bool: True or False depending on success
        """
        project_dict = dict()  # Dictionary for storing project info
        project_dict["version"] = LATEST_PROJECT_VERSION
        project_dict["name"] = self.name
        project_dict["description"] = self.description
        project_dict["tool_specifications"] = tool_def_paths
        # Compute connections directly from Links on scene
        connections = list()
        for link in self._toolbox.ui.graphicsView.links():
            src_connector = link.src_connector
            src_anchor = src_connector.position
            src_name = src_connector.parent_name()
            dst_connector = link.dst_connector
            dst_anchor = dst_connector.position
            dst_name = dst_connector.parent_name()
            conn = {"from": [src_name, src_anchor], "to": [dst_name, dst_anchor]}
            connections.append(conn)
        project_dict["connections"] = connections
        scene_rect = self._toolbox.ui.graphicsView.scene().sceneRect()
        project_dict["scene_y"] = scene_rect.y()
        project_dict["scene_w"] = scene_rect.width()
        project_dict["scene_h"] = scene_rect.height()
        project_dict["scene_x"] = scene_rect.x()
        items_dict = dict()  # Dictionary for storing project items
        # Traverse all items in project model by category
        for category_item in self._toolbox.project_item_model.root().children():
            category = category_item.name
            category_dict = items_dict[category] = dict()
            for item in self._toolbox.project_item_model.items(category):
                category_dict[item.name] = item.item_dict()
        # Write project on disk
        saved_dict = dict(project=project_dict, objects=items_dict)
        # Write into JSON file
        with open(self.config_file, "w") as fp:
            json.dump(saved_dict, fp, indent=4)
        return True

    def load(self, objects_dict):
        """Populate project item model with items loaded from project file.

        Args:
            objects_dict (dict): Dictionary containing all project items in JSON format

        Returns:
            Boolean value depending on operation success.
        """
        self._toolbox.msg.emit("Loading project items...")
        empty = True
        for category_name, category_dict in objects_dict.items():
            category_name = _update_if_changed(category_name)
            items = []
            for name, item_dict in category_dict.items():
                item_dict.pop("short name", None)
                item_dict["name"] = name
                items.append(item_dict)
                empty = False
            self.add_project_items(category_name, *items, verbosity=False)
        if empty:
            self._toolbox.msg_warning.emit("Project has no items")
        return True

    def load_tool_specification_from_file(self, jsonfile):
        """Create a Tool specification according to a tool definition file.

        Args:
            jsonfile (str): Path of the tool specification definition file

        Returns:
            ToolSpecification or None if reading the file failed
        """
        try:
            with open(jsonfile, "r") as fp:
                try:
                    definition = json.load(fp)
                except ValueError:
                    self._toolbox.msg_error.emit("Tool specification file not valid")
                    logging.exception("Loading JSON data failed")
                    return None
        except FileNotFoundError:
            self._toolbox.msg_error.emit("Tool specification file <b>{0}</b> does not exist".format(jsonfile))
            return None
        # Path to main program relative to definition file
        includes_main_path = definition.get("includes_main_path", ".")
        path = os.path.normpath(os.path.join(os.path.dirname(jsonfile), includes_main_path))
        return self.load_tool_specification_from_dict(definition, path)

    def load_tool_specification_from_dict(self, definition, path):
        """Create a Tool specification according to a dictionary.

        Args:
            definition (dict): Dictionary with the tool definition
            path (str): Directory where main program file is located

        Returns:
            ToolSpecification or None if something went wrong
        """
        try:
            _tooltype = definition["tooltype"].lower()
        except KeyError:
            self._toolbox.msg_error.emit(
                "No tool type defined in tool definition file. Supported types "
                "are 'python', 'gams', 'julia' and 'executable'"
            )
            return None
        if _tooltype == "julia":
            return JuliaTool.load(self._toolbox, path, definition)
        if _tooltype == "python":
            return PythonTool.load(self._toolbox, path, definition)
        if _tooltype == "gams":
            return GAMSTool.load(self._toolbox, path, definition)
        if _tooltype == "executable":
            return ExecutableTool.load(self._toolbox, path, definition)
        self._toolbox.msg_warning.emit("Tool type <b>{}</b> not available".format(_tooltype))
        return None

    def add_project_items(self, category_name, *items, set_selected=False, verbosity=True):
        """Adds item to project.

        Args:
            category_name (str): The items' category
            items (dict): one or more dict of items to add
            set_selected (bool): Whether to set item selected after the item has been added to project
            verbosity (bool): If True, prints message
        """
        category_ind = self._toolbox.project_item_model.find_category(category_name)
        if not category_ind:
            self._toolbox.msg_error.emit("Category {0} not found".format(category_name))
            return
        category_item = self._toolbox.project_item_model.project_item(category_ind)
        item_maker = category_item.item_maker()
        for item_dict in items:
            try:
                item = item_maker(self._toolbox, **item_dict)
            except TypeError:
                self._toolbox.msg_error.emit(
                    "Loading project item <b>{0}</b> into category <b>{1}</b> failed. "
                    "This is most likely caused by an outdated project file.".format(item_dict["name"], category_name)
                )
                continue
            self._toolbox.project_item_model.insert_item(item, category_ind)
            # Append new node to networkx graph
            self.add_to_dag(item.name)
            if verbosity:
                self._toolbox.msg.emit("{0} <b>{1}</b> added to project.".format(item.item_type(), item.name))
            if set_selected:
                self.set_item_selected(item)

    def add_to_dag(self, item_name):
        """Add new node (project item) to the directed graph."""
        self.dag_handler.add_dag_node(item_name)

    def set_item_selected(self, item):
        """Sets item selected and shows its info screen.

        Args:
            item (ProjectItem): Project item to select
        """
        ind = self._toolbox.project_item_model.find_item(item.name)
        self._toolbox.ui.treeView_project.setCurrentIndex(ind)

    def execute_selected(self):
        """Starts executing selected directed acyclic graph. Selected graph is
        determined by the selected project item(s). Aborts, if items from multiple
        graphs are selected."""
        self._toolbox.ui.textBrowser_eventlog.verticalScrollBar().setValue(
            self._toolbox.ui.textBrowser_eventlog.verticalScrollBar().maximum()
        )
        if not self.dag_handler.dags():
            self._toolbox.msg_warning.emit("Project has no items to execute")
            return
        # Get selected item
        selected_indexes = self._toolbox.ui.treeView_project.selectedIndexes()
        if not selected_indexes:
            self._toolbox.msg_warning.emit("Please select a project item and try again")
            return
        if len(selected_indexes) == 1:
            selected_item = self._toolbox.project_item_model.project_item(selected_indexes[0])
        else:
            # More than one item selected. Make sure they part of the same graph or abort
            selected_item = self._toolbox.project_item_model.project_item(selected_indexes.pop())
            selected_item_graph = self.dag_handler.dag_with_node(selected_item.name)
            for ind in selected_indexes:
                # Check that other selected nodes are in the same graph
                i = self._toolbox.project_item_model.project_item(ind)
                if not self.dag_handler.dag_with_node(i.name) == selected_item_graph:
                    self._toolbox.msg_warning.emit("Please select items from only one graph")
                    return
        self._executed_graph_index = 0  # Needed in execute_selected() just for printing the number
        self._n_graphs = 1
        # Calculate bfs-ordered list of project items to execute
        dag = self.dag_handler.dag_with_node(selected_item.name)
        if not dag:
            self._toolbox.msg_error.emit(
                "[BUG] Could not find a graph containing {0}. "
                "<b>Please reopen the project.</b>".format(selected_item.name)
            )
            return
        ordered_nodes = self.dag_handler.calc_exec_order(dag)
        if not ordered_nodes:
            self._toolbox.msg.emit("")
            self._toolbox.msg_warning.emit(
                "Selected graph is not a directed acyclic graph. "
                "Please edit connections in Design View and try again."
            )
            return
        # Make execution instance, connect signals and start execution
        self.execution_instance = ExecutionInstance(self._toolbox, ordered_nodes)
        self._toolbox.msg.emit("")
        self._toolbox.msg.emit("--------------------------------------------------")
        self._toolbox.msg.emit("<b>Executing Selected Directed Acyclic Graph</b>")
        self._toolbox.msg.emit("Order: {0}".format(" -> ".join(list(ordered_nodes))))
        self._toolbox.msg.emit("--------------------------------------------------")
        self.execution_instance.graph_execution_finished_signal.connect(self.graph_execution_finished)
        self.execution_instance.start_execution()
        return

    def execute_project(self):
        """Determines the number of directed acyclic graphs to execute in the project.
        Determines the execution order of project items in each graph. Creates an
        instance for executing the first graph and starts executing it.
        """
        self._toolbox.ui.textBrowser_eventlog.verticalScrollBar().setValue(
            self._toolbox.ui.textBrowser_eventlog.verticalScrollBar().maximum()
        )
        if not self.dag_handler.dags():
            self._toolbox.msg_warning.emit("Project has no items to execute")
            return
        self._n_graphs = len(self.dag_handler.dags())
        i = 0  # Key for self._ordered_dags dictionary
        for g in self.dag_handler.dags():
            ordered_nodes = self.dag_handler.calc_exec_order(g)
            if not ordered_nodes:
                self._invalid_graphs.append(g)
                continue
            self._ordered_dags[i] = ordered_nodes
            i += 1
        if not self._ordered_dags.keys():
            self._toolbox.msg_error.emit(
                "There are no valid Directed Acyclic Graphs to execute. Please modify connections."
            )
            self._invalid_graphs.clear()
            return
        self._executed_graph_index = 0
        # Get first graph, connect signals and start executing it
        ordered_nodes = self._ordered_dags.pop(self._executed_graph_index)  # Pop first set of items to execute
        self.execution_instance = ExecutionInstance(self._toolbox, ordered_nodes)
        self._toolbox.msg.emit("")
        self._toolbox.msg.emit("---------------------------------------")
        self._toolbox.msg.emit("<b>Executing All Directed Acyclic Graphs</b>")
        self._toolbox.msg.emit("<b>Starting DAG {0}/{1}</b>".format(self._executed_graph_index + 1, self._n_graphs))
        self._toolbox.msg.emit("Order: {0}".format(" -> ".join(list(ordered_nodes))))
        self._toolbox.msg.emit("---------------------------------------")
        self.execution_instance.graph_execution_finished_signal.connect(self.graph_execution_finished)
        self.execution_instance.start_execution()

    @Slot("QVariant")
    def graph_execution_finished(self, state):
        """Releases resources from previous execution and prepares the next
        graph for execution if there are still graphs left. Otherwise,
        finishes the run.

        Args:
            state (ExecutionState): proposed execution state after item finished execution
        """
        self.execution_instance.graph_execution_finished_signal.disconnect(self.graph_execution_finished)
        self.execution_instance.deleteLater()
        self.execution_instance = None
        if state == ExecutionState.ABORT:
            # Execution failed due to some error in executing the project item. E.g. Tool is missing an input file
            pass
        elif state == ExecutionState.STOP_REQUESTED:
            self._toolbox.msg_error.emit("Execution stopped")
            self._ordered_dags.clear()
            self._invalid_graphs.clear()
            return
        self._toolbox.msg.emit("<b>DAG {0}/{1} finished</b>".format(self._executed_graph_index + 1, self._n_graphs))
        self._executed_graph_index += 1
        # Pop next graph
        ordered_nodes = self._ordered_dags.pop(self._executed_graph_index, None)  # Pop next graph
        if not ordered_nodes:
            # All valid DAGs have been executed. Check if there are invalid DAGs and report these to user
            self.handle_invalid_graphs()
            # No more graphs to execute
            self._toolbox.msg_success.emit("Execution complete")
            return
        # Execute next graph
        self.execution_instance = ExecutionInstance(self._toolbox, ordered_nodes)
        self._toolbox.msg.emit("")
        self._toolbox.msg.emit("---------------------------------------")
        self._toolbox.msg.emit("<b>Starting DAG {0}/{1}</b>".format(self._executed_graph_index + 1, self._n_graphs))
        self._toolbox.msg.emit("Order: {0}".format(" -> ".join(ordered_nodes)))
        self._toolbox.msg.emit("---------------------------------------")
        self.execution_instance.graph_execution_finished_signal.connect(self.graph_execution_finished)
        self.execution_instance.start_execution()

    def stop(self):
        """Stops execution of the current DAG. Slot for the main window Stop tool button
        in the toolbar."""
        if not self.execution_instance:
            self._toolbox.msg.emit("No execution in progress")
            return
        self._toolbox.msg.emit("Stopping...")
        if not self.execution_instance:
            return
        self.execution_instance.stop()

    def handle_invalid_graphs(self):
        """Prints messages to Event Log if there are invalid DAGs (e.g. contain self-loops) in the project."""
        if self._invalid_graphs:
            for g in self._invalid_graphs:
                # Some graphs in the project are not DAGs. Report to user that these will not be executed.
                self._toolbox.msg.emit("")
                self._toolbox.msg.emit("---------------------------------------")
                self._toolbox.msg_warning.emit(
                    "<b>Graph {0}/{1} is not a Directed Acyclic Graph</b>".format(
                        self._executed_graph_index + 1, self._n_graphs
                    )
                )
                self._toolbox.msg.emit("Items in graph: {0}".format(", ".join(g.nodes())))
                edges = ["{0} -> {1}".format(*edge) for edge in self.dag_handler.edges_causing_loops(g)]
                self._toolbox.msg.emit(
                    "Please edit connections in Design View to execute it. "
                    "Possible fix: remove connection(s) {0}.".format(", ".join(edges))
                )
                self._toolbox.msg.emit("---------------------------------------")
                self._executed_graph_index += 1
        self._invalid_graphs.clear()

    def export_graphs(self):
        """Export all valid directed acyclic graphs in project to GraphML files."""
        if not self.dag_handler.dags():
            self._toolbox.msg_warning.emit("Project has no graphs to export")
            return
        i = 0
        for g in self.dag_handler.dags():
            fn = str(i) + ".graphml"
            path = os.path.join(self.project_dir, fn)
            if not self.dag_handler.export_to_graphml(g, path):
                self._toolbox.msg_warning.emit("Exporting graph nr. {0} failed. Not a directed acyclic graph".format(i))
            else:
                self._toolbox.msg.emit("Graph nr. {0} exported to {1}".format(i, path))
            i += 1

    @Slot("QVariant")
    def notify_changes_in_dag(self, dag):
        """Notifies the items in given dag that the dag has changed."""
        ordered_nodes = self.dag_handler.calc_exec_order(dag)
        if not ordered_nodes:
            # Not a dag, invalidate workflow
            edges = self.dag_handler.edges_causing_loops(dag)
            for node in dag.nodes():
                ind = self._toolbox.project_item_model.find_item(node)
                project_item = self._toolbox.project_item_model.project_item(ind)
                project_item.invalidate_workflow(edges)
            return
        # Make resource map and run simulation
        project_item_model = self._toolbox.project_item_model
        resource_map = ResourceMap(ordered_nodes, project_item_model)
        resource_map.update()
        for rank, item in enumerate(ordered_nodes):
            ind = project_item_model.find_item(item)
            project_item = project_item_model.project_item(ind)
            project_item.handle_dag_changed(rank, resource_map.available_upstream_resources(item))

    def notify_changes_in_all_dags(self):
        """Notifies all items of changes in all dags in the project."""
        for g in self.dag_handler.dags():
            self.notify_changes_in_dag(g)

    def notify_changes_in_containing_dag(self, item):
        """Notifies items in dag containing the given item that the dag has changed."""
        dag = self.dag_handler.dag_with_node(item)
        # Some items trigger this method while they are being initialized
        # but before they have been added to any DAG.
        # In those cases we don't need to notify other items.
        if dag:
            self.notify_changes_in_dag(dag)
        elif self._toolbox.project_item_model.find_item(item) is not None:
            self._toolbox.msg_error.emit(
                "[BUG] Could not find a graph containing {0}. " "<b>Please reopen the project.</b>".format(item)
            )


def _update_if_changed(category_name):
    """
    Checks if category name has been changed.

    This allows old project files to be loaded.

    Args:
        category_name (str): Category name

    Returns:
        str: New category name if it has changed or category_name
    """
    if category_name == "Data Interfaces":
        return "Importers"
    if category_name == "Data Exporters":
        return "Exporters"
    return category_name
