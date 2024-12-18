# -*- coding: utf-8 -*-
"""
/***************************************************************************
 HVLSPMergePackages
                                 A QGIS plugin
 This plugin merge HVLSP Geopackage files
 Generated by Plugin Builder: http://g-sherman.github.io/Qgis-Plugin-Builder/
                              -------------------
        begin                : 2024-10-30
        git sha              : $Format:%H$
        copyright            : (C) 2024 by IGN
        email                : guillaume.valtat@ign.fr
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import os
import sys
import subprocess
import time
import shutil
import logging

from collections import namedtuple
from PyQt5.QtWidgets import QApplication, QDockWidget
from qgis import processing
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication, Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import QgsProject, QgsVectorLayer, QgsApplication
from .HVLSP_merge_packages_dialog import HVLSPMergePackagesDialog
from .ProgressBar import ProgressBar

# Initialize Qt resources from file resources.py
from .resources import *


# Import the code for the dialog


class HVLSPMergePackages:
    """QGIS Plugin Implementation."""

    def __init__(self, iface) -> None:
        """Constructor.

        :param iface: An interface instance that will be passed to this class
            which provides the hook by which you can manipulate the QGIS
            application at run time.
        :type iface: QgsInterface
        """
        # Save reference to the QGIS interface
        self.dlg = None
        self.iface = iface
        # initialize plugin directory
        self.pluginDir = os.path.dirname(__file__)
        # initialize locale
        locale = QSettings().value('locale/userLocale')[0:2]
        localePath = os.path.join(
            self.pluginDir,
            'i18n',
            'HVLSPMergePackages_{}.qm'.format(locale))

        if os.path.exists(localePath):
            self.translator = QTranslator()
            self.translator.load(localePath)
            QCoreApplication.installTranslator(self.translator)

        # Declare instance attributes
        self.actions = []
        self.menu = self.tr(u'&HVLSP merge packages')

        # Check if plugin was started the first time in current QGIS session
        # Must be set in initGui() to survive plugin reloads
        self.firstStart = None

        # Dictionnary of Geopackage files
        self.__gpkgFiles = {}

        # The list of files to delete
        self.__filesToRemove = []

        # Patience
        self.__progress = None

        # Log file
        self.__logger = logging.getLogger(__name__)

        # Project directory
        self.__homePath = QgsProject.instance().homePath()

    def __isProjectRegistered(self) -> bool:
        self.__homePath = QgsProject.instance().homePath()
        if self.__homePath == "":
            message = "Your QGIS project must be saved before you can use the HVLSP_merge_packages plugin"
            HVLSPMergePackages.showMessageBox(message)
            self.printAndLogging("{}\n".format(message))
            return False
        return True

    def __isGroupInProjectLayers(self) -> bool:
        root = QgsProject.instance().layerTreeRoot()
        nodesGroup = root.findGroups()
        if len(nodesGroup) >= 1:
            message = "Your project contains layers with group names, to use the plugin, " \
                      "you must delete the group(s) or open a new project"
            HVLSPMergePackages.showMessageBox(message)
            self.printAndLogging("{}\n".format(message))
            return True
        return False

    # noinspection PyMethodMayBeStatic
    def tr(self, message) -> str:
        """Get the translation for a string using Qt translation API.

        We implement this ourselves since we do not inherit QObject.

        :param message: String for translation.
        :type message: str, QString

        :returns: Translated version of message.
        :rtype: QString
        """
        # noinspection PyTypeChecker,PyArgumentList,PyCallByClass
        return QCoreApplication.translate('HVLSPMergePackages', message)

    def addAction(
            self,
            iconPath,
            text,
            callback,
            enabledFlag=True,
            addToMenu=True,
            addToToolbar=True,
            statusTip=None,
            whatsThis=None,
            parent=None) -> QAction:
        """Add a toolbar icon to the toolbar.

        :param iconPath: Path to the icon for this action. Can be a resource
            path (e.g. ':/plugins/foo/bar.png') or a normal file system path.
        :type iconPath: str

        :param text: Text that should be shown in menu items for this action.
        :type text: str

        :param callback: Function to be called when the action is triggered.
        :type callback: function

        :param enabledFlag: A flag indicating if the action should be enabled
            by default. Defaults to True.
        :type enabledFlag: bool

        :param addToMenu: Flag indicating whether the action should also
            be added to the menu. Defaults to True.
        :type addToMenu: bool

        :param addToToolbar: Flag indicating whether the action should also
            be added to the toolbar. Defaults to True.
        :type addToToolbar: bool

        :param statusTip: Optional text to show in a popup when mouse pointer
            hovers over the action.
        :type statusTip: str

        :param parent: Parent widget for the new action. Defaults None.
        :type parent: QWidget

        :param whatsThis: Optional text to show in the status bar when the
            mouse pointer hovers over the action.

        :returns: The action that was created. Note that the action is also
            added to self.actions list.
        :rtype: QAction
        """

        icon = QIcon(iconPath)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabledFlag)

        if statusTip is not None:
            action.setStatusTip(statusTip)

        if whatsThis is not None:
            action.setWhatsThis(whatsThis)

        if addToToolbar:
            # Adds plugin icon to Plugins toolbar
            self.iface.addToolBarIcon(action)

        if addToMenu:
            self.iface.addPluginToMenu(
                self.menu,
                action)

        self.actions.append(action)

        return action

    def initGui(self) -> None:
        """Create the menu entries and toolbar icons inside the QGIS GUI."""
        iconPath = ':/plugins/HVLSPMergePackages/icons/import.png'
        self.addAction(
            iconPath,
            text=self.tr(u'Import Geopackage files'),
            callback=self.importing,
            parent=self.iface.mainWindow())

        iconPath = ':/plugins/HVLSPMergePackages/icons/remove.png'
        self.addAction(
            iconPath,
            text=self.tr(u'Merge layers and remove duplicates objects'),
            callback=self.mergeLayersAndRemoveDuplicates,
            parent=self.iface.mainWindow())

        iconPath = ':/plugins/HVLSPMergePackages/icons/save.png'
        self.addAction(
            iconPath,
            text=self.tr(u'Save layers into Geopackage files'),
            callback=self.saveLayers,
            parent=self.iface.mainWindow())

        iconPath = ':/plugins/HVLSPMergePackages/icons/treatments.png'
        self.addAction(
            iconPath,
            text=self.tr(u'Launch all treatments consecutively'),
            callback=self.launchAllTreatments,
            parent=self.iface.mainWindow())

        iconPath = ':/plugins/HVLSPMergePackages/icons/informations.png'
        self.addAction(
            iconPath,
            text=self.tr(u'Open user manual'),
            callback=HVLSPMergePackages.showHelp,
            parent=self.iface.mainWindow())

        # will be set False in run()
        self.firstStart = True

    def __showPythonConsole(self) -> None:
        pythonConsole = self.iface.mainWindow().findChild(QDockWidget, 'PythonConsole')
        if not pythonConsole or not pythonConsole.isVisible():
            self.iface.actionShowPythonDialog().trigger()

    def unload(self) -> None:
        """Removes the plugin menu item and icon from QGIS GUI."""
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&HVLSP merge packages'),
                action)
            self.iface.removeToolBarIcon(action)

    def launchAllTreatments(self) -> None:
        start = time.time()
        try:
            if not self.importing():
                return
            self.mergeLayersAndRemoveDuplicates()
            self.saveLayers()
        except Exception as e:
            self.printAndLogging(e)
            QApplication.setOverrideCursor(Qt.CursorShape.ArrowCursor)
            if self.__progress is not None:
                self.__progress.close()
            return
        end = time.time()
        timeResult = end - start
        if timeResult > 60:
            self.printAndLogging('Process complete in {} minutes.\n'.format(round(timeResult / 60)))
        else:
            self.printAndLogging('Process complete.\n')

    def importing(self) -> bool:
        # Is the project registered
        if not self.__isProjectRegistered():
            return False

        if self.__isGroupInProjectLayers():
            return False

        # if log file exist then log file is remove and start a new log file
        logfilename = "{}/HVLSPMergePackages.log".format(self.__homePath)
        if os.path.isfile(logfilename):
            with open(logfilename, 'w'):
                pass
        formatter = '%(asctime)s - %(name)s - %(message)s'
        logging.basicConfig(filename=logfilename, level=logging.INFO, format=formatter)
        self.printAndLogging("***New process***".format(logfilename))

        if self.firstStart:
            self.firstStart = False
            self.dlg = HVLSPMergePackagesDialog()
        self.dlg.listWidget.clear()
        self.dlg.setGeoPackageFiles()
        # show the dialog
        self.dlg.show()
        # Run the dialog event loop
        result = self.dlg.exec_()
        if result:
            self.__gpkgFiles = self.dlg.getGeoPackageFiles()
            if len(self.__gpkgFiles) == 0:
                self.printAndLogging('Process stopped : no files selected')
                return False
            self.__importGpkgFiles()
        else:
            self.printAndLogging('Process stopped by user')
            return False
        return True

    # Import GeoPackage files
    def __importGpkgFiles(self) -> None:
        if not self.__evaluateSpaceDiskForProcessing(self.__evaluateSpaceDisk()):
            return

        # start QGIS Python console
        self.__showPythonConsole()

        # start progress bar
        self.__progress = ProgressBar(len(self.__gpkgFiles), "Import GeoPackage files")
        self.printAndLogging('Import Geopackage files...')
        i = 0
        for gpkgFile in self.__gpkgFiles:
            i += 1
            self.__progress.setValue(i)
            self.printAndLogging('Import file : {}'.format(gpkgFile))
            layer = QgsVectorLayer(gpkgFile, "test", "ogr")
            subLayers = layer.dataProvider().subLayers()
            for subLayer in subLayers:
                name = subLayer.split('!!::!!')[1]
                self.printAndLogging(name)
                uri = "%s|layername=%s" % (gpkgFile, name)
                # Create layer
                subVlayer = QgsVectorLayer(uri, name, 'ogr')
                # Add layer to map
                QgsProject.instance().addMapLayer(subVlayer)
                self.printAndLogging('Done.')
        self.__progress.close()
        self.printAndLogging('All files are imported.\n')

    def mergeLayersAndRemoveDuplicates(self) -> None:
        # Is the project registered
        if not self.__isProjectRegistered():
            return
        if self.__isGroupInProjectLayers():
            return
        if not self.__runMergeLayers():
            return
        self.__runRemoveDuplicates()

    # Merge all layers
    def __runMergeLayers(self) -> bool:
        startTotal = time.time()
        textMerge = 'Merge all layers...'
        self.printAndLogging(textMerge)
        # Search distinct layers in map group by layer name
        result = HVLSPMergePackages.selectDistinctLayers()
        distinctLayerNames = result[0]
        groupedLayersByName = result[1]
        if len(distinctLayerNames) == 0 and len(groupedLayersByName) == 0:
            self.printAndLogging("No layers to merge. Process stopped.\n")
            return False
        self.printAndLogging('Total number of distinct layers : {}'.format(len(distinctLayerNames)))
        # Merge all layers
        self.__mergeLayers(distinctLayerNames, groupedLayersByName, textMerge)
        # Delete all layers when layers are merged
        self.printAndLogging("Delete old layers...")
        for layerName in distinctLayerNames:
            for layer in groupedLayersByName[layerName]:
                QgsProject.instance().removeMapLayer(layer.id())
        self.printAndLogging("Done.")
        endTotal = time.time()
        timeResultTotal = endTotal - startTotal
        self.printAndLogging(
            'All layers have been merged in {} minutes.\n'.format(round(timeResultTotal / 60)))
        return True

    def __runRemoveDuplicates(self) -> None:
        startTotal = time.time()
        count = 0
        projectLayers = QgsProject.instance().layerTreeRoot().children()
        layersToRemove = []
        textRemove = 'Remove duplicates...'
        self.printAndLogging(textRemove)
        self.__progress = ProgressBar(len(projectLayers), textRemove)
        for layerItem in projectLayers:
            start = time.time()
            layerName = layerItem.name()
            layer = QgsProject.instance().mapLayersByName(layerName)
            layersToRemove.append(layer[0])
            count += 1
            self.__progress.setValue(count)
            self.printAndLogging('{} - Processing layer : {}...'.format(count, layerName))
            newLayerName = layerName.replace('_merged', '')
            fileNameGpkg = '{}/{}.gpkg'.format(self.__homePath, newLayerName)
            self.__filesToRemove.append(fileNameGpkg)
            params = {
                'INPUT': layer[0],
                'FIELDS': ['objectid'],
                'OUTPUT': fileNameGpkg
            }
            processing.runAndLoadResults('native:removeduplicatesbyattribute', params)
            end = time.time()
            timeResult = end - start
            if timeResult > 60:
                self.printAndLogging('Done in {} minutes'.format(round(timeResult / 60)))
            else:
                self.printAndLogging("Done.")
        self.deleteOldLayers(layersToRemove)
        endTotal = time.time()
        timeResultTotal = endTotal - startTotal
        self.printAndLogging(
            'All duplicates have been removed in {} minutes.\n'.format(round(timeResultTotal / 60)))
        self.__progress.close()

    def saveLayers(self) -> None:
        # Is the project registered
        if not self.__isProjectRegistered():
            return
        if self.__isGroupInProjectLayers():
            return
        start = time.time()
        textSave = 'Save all layers in Geopackage file...'
        self.printAndLogging(textSave)
        self.__progress = ProgressBar(1, textSave)
        layersToSaveInGpkg = []
        for qgsLayersTreeNode in QgsProject.instance().layerTreeRoot().children():
            qgsMapLayers = QgsProject.instance().mapLayersByName(qgsLayersTreeNode.name())
            layersToSaveInGpkg.append(qgsMapLayers[0])
        fileNameGpkg = '{}/result.gpkg'.format(self.__homePath)
        self.printAndLogging(fileNameGpkg)
        self.__progress.setValue(1)
        if len(layersToSaveInGpkg) == 0:
            self.printAndLogging("No layers to save. Process stopped.\n")
            self.__progress.close()
            return
        params = {'LAYERS': layersToSaveInGpkg,
                  'OUTPUT': fileNameGpkg,
                  'OVERWRITE': True,
                  'SAVE_STYLES': False,
                  'SAVE_METADATA': False,
                  'SELECTED_FEATURES_ONLY': False}
        processing.run("native:package", params)
        self.__progress.close()
        end = time.time()
        timeResult = end - start
        if timeResult > 60:
            self.printAndLogging('Done in {} minutes.\n'.format(round(timeResult / 60)))
        else:
            self.printAndLogging("Done.\n")
        self.__removeFiles()

    def __mergeLayers(self, distinctLayerNames, groupedLayersByName, textMerge) -> None:
        self.__progress = ProgressBar(len(distinctLayerNames), textMerge)
        count = 0
        for layerName in distinctLayerNames:
            start = time.time()
            count += 1
            self.__progress.setValue(count)
            self.printAndLogging('{} - Processing layer : {}...'.format(count, layerName))
            fileNameGpkg = '{}/{}_merged.gpkg'.format(self.__homePath, layerName)
            self.__filesToRemove.append(fileNameGpkg)
            params = {
                'LAYERS': groupedLayersByName[layerName],
                'OUTPUT': fileNameGpkg
            }
            processing.runAndLoadResults('native:mergevectorlayers', params)
            end = time.time()
            timeResult = end - start
            if timeResult > 60:
                self.printAndLogging('Done in {} minutes'.format(round(timeResult / 60)))
            else:
                self.printAndLogging("Done.")
        self.__progress.close()

    # evaluate disk space for processing
    def __evaluateSpaceDiskForProcessing(self, diskUsage) -> bool:
        sizeFiles = 0
        for gpkgFile in self.__gpkgFiles:
            sizeFiles += os.path.getsize(gpkgFile)
        diskSpaceRequired = sizeFiles * 3 * 1.33
        if diskSpaceRequired > diskUsage.free:
            message = "Please free some space first as merging the datasets approximately {} Go " \
                      "of available space".format(HVLSPMergePackages.octetsToGigaOctets(diskSpaceRequired))
            self.printAndLogging(message)
            HVLSPMergePackages.showMessageBox(message)
            return False
        messageBis = 'Local disk (in Go) -> available : {0}, used : {1}, free : {2}, Size of selected files : {3}, ' \
                     'Disk space required : {4}'.format(HVLSPMergePackages.octetsToGigaOctets(diskUsage.available),
                                                          HVLSPMergePackages.octetsToGigaOctets(diskUsage.used),
                                                          HVLSPMergePackages.octetsToGigaOctets(diskUsage.free),
                                                          HVLSPMergePackages.octetsToGigaOctets(sizeFiles),
                                                          HVLSPMergePackages.octetsToGigaOctets(diskSpaceRequired))
        self.printAndLogging(messageBis)
        self.printAndLogging("Space needed for 3 temporary versions of the files, plus margin of security (33%)\n")
        return True

    @staticmethod
    def octetsToGigaOctets(numberToRound) -> float:
        return round(numberToRound / 1000000000, 2)

    def __removeFiles(self) -> None:
        self.printAndLogging("Delete working files...")
        QgsApplication.exitQgis()
        for filePath in self.__filesToRemove:
            if os.path.exists(filePath):
                os.remove(filePath)
                self.printAndLogging("The file {} has been deleted.".format(filePath))
        self.printAndLogging('Done.\n')
        QApplication.exit()
        # QgsApplication.initQgis()
        # QgsApplication.exec()

    @staticmethod
    def selectDistinctLayers() -> []:
        groupedLayersByName = {}
        distinctLayerNames = set()
        projectLayers = QgsProject.instance().layerTreeRoot().children()
        for layerItem in projectLayers:
            layerName = layerItem.name()
            distinctLayerNames.add(layerName)
            groupedLayersByName[layerName] = QgsProject.instance().mapLayersByName(layerName)
        return distinctLayerNames, groupedLayersByName

    def deleteOldLayers(self, layersToRemove) -> None:
        self.printAndLogging("Delete old layers...")
        for layer in layersToRemove:
            QgsProject.instance().removeMapLayer(layer.id())
        self.printAndLogging("Done.")

    def __evaluateSpaceDisk(self) -> ():
        diskUsage = namedtuple('diskUsage', 'available used free')
        available, used, free = shutil.disk_usage(self.__homePath)
        return diskUsage(available, used, free)

    @staticmethod
    def showHelp() -> None:
        file_path = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "files", "HVLSPMergePackagesUserManual.pdf"))
        if sys.platform == "win32":
            os.startfile(file_path)
        else:
            opener = "open" if sys.platform == "darwin" else "xdg-open"
            subprocess.call([opener, file_path])

    @staticmethod
    def showMessageBox(message) -> None:
        msgBox = QMessageBox()
        msgBox.setWindowTitle("HVLSP merge packages")
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.setText(message)
        msgBox.exec_()

    def printAndLogging(self, message) -> None:
        self.__logger.info(message)
        print(message)
