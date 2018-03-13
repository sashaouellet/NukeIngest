import nuke, nukescripts
from nukescripts import panels
import os, csv, re
import sdm
from PySide2.QtCore import *
from PySide2.QtGui import *
from PySide2.QtWidgets import *
from PySide2.QtUiTools import QUiLoader
from edl import Parser
from timecode import Timecode
import fnmatch

class ShotListItemWidget():
	def __init__(self, shot, startFrame=0, endFrame=0, inc=1, handles=False, handleLength=12):
		self.shot = shot
		self.startFrame = startFrame
		self.endFrame = endFrame
		self.inc = inc
		self.handles = handles
		self.handleLength = handleLength

	def getWidgets(self):
		widgets = []

		widgets.append(QPushButton('-'))
		widgets.append(QLineEdit(str(self.shot)))
		widgets.append(QLineEdit(str(self.startFrame)))
		widgets.append(QLineEdit(str(self.endFrame)))
		widgets.append(QLineEdit(str(self.inc)))

		handleToggle = QCheckBox()
		handleLineEdit = QLineEdit(str(self.handleLength))

		handleToggle.stateChanged.connect(lambda s: handleLineEdit.setEnabled(s == Qt.Checked))
		handleLineEdit.setEnabled(self.handles)
		handleToggle.setChecked(self.handles)

		widgets.append(handleToggle)
		widgets.append(handleLineEdit)

		return widgets

	@staticmethod
	def fromWidgets(widgets):
		shot = int(widgets[1].text()) if isinstance(widgets[1], QLineEdit) else 0
		startFrame = int(widgets[2].text()) if isinstance(widgets[2], QLineEdit) else 0
		endFrame = int(widgets[3].text()) if isinstance(widgets[3], QLineEdit) else 0
		inc = int(widgets[4].text()) if isinstance(widgets[4], QLineEdit) else 1
		handles = widgets[5].isChecked() if isinstance(widgets[5], QCheckBox) else False
		handleLength = int(widgets[6].text()) if isinstance(widgets[6], QLineEdit) else 12

		return ShotListItemWidget(shot, startFrame, endFrame, inc, handles, handleLength)

class IngestPanel(QWidget):
	FOOTAGE_FORMATS = ['*.ari', '*.avi', '*cin', '*.dpx', '*.mov', '*.mp4', '*.r3d', '*.dng']

	def __init__(self, parent=None):
		QWidget.__init__(self, parent)

		uiPath = os.path.join(sdm.UI_DIR, 'ingest.ui')
		file = QFile(uiPath)

		file.open(QFile.ReadOnly)

		loader = QUiLoader()
		self.ui = loader.load(file)
		self.footage = []
		self.currFootage = ''
		self.shotConfig = {}
		self.baseDir = ''
		self.reads = {}

		self.setupConnections()
		self.setLayout(self.ui.layout())
		file.close()

	def setupConnections(self):
		self.ui.BTN_footage.clicked.connect(self.handleFootageImport)
		self.ui.BTN_rmFootage.clicked.connect(self.handleRemoveFootage)
		self.ui.BTN_edl.clicked.connect(self.handleEDLImport)
		self.ui.BTN_mappingFile.clicked.connect(self.handleMappingImport)
		self.ui.BTN_addMapping.clicked.connect(self.handleAddMapping)
		self.ui.BTN_shot.clicked.connect(self.handleAddShot)
		self.ui.BTN_ingest.clicked.connect(self.ingest)
		self.ui.BTN_addMeta.clicked.connect(self.handleAddMetadata)
		self.ui.BTN_footageDir.clicked.connect(self.handleChooseFootageBaseDir)
		self.ui.LNE_footageDir.textChanged.connect(lambda x: self.handleChooseFootageBaseDir(choose=False))

		self.ui.LST_files.itemSelectionChanged.connect(self.handleFootageSelection)

		self.ui.TBL_shots.setHorizontalHeaderLabels(['', 'Shot', 'Start', 'End', 'Inc', 'Handles', 'Handle Length'])
		self.ui.TBL_mappings.setHorizontalHeaderLabels(['', 'Input', 'Output'])
		self.ui.TBL_metadata.setHorizontalHeaderLabels(['', 'Name', 'Value'])

		self.ui.CHK_downscale.stateChanged.connect(self.handleDownscaleOption)
		self.ui.CHK_proxy.stateChanged.connect(self.handleProxyOptions)
		self.ui.CHK_proxyToSubdir.stateChanged.connect(self.handleProxySubdirOption)
		self.ui.CHK_proxyNameAppend.stateChanged.connect(self.handleProxyNameOption)

		self.ui.RDO_edl.toggled.connect(self.handleImportType)
		self.ui.RDO_manual.toggled.connect(self.handleImportType)

		self.ui.BTN_footageDir.setVisible(False)
		self.ui.LNE_footageDir.setVisible(False)
		self.ui.BTN_edl.setVisible(False)
		self.ui.LBL_fps.setVisible(False)
		self.ui.CMB_fps.setVisible(False)

		self.checkCanIngest()

	def handleChooseFootageBaseDir(self, choose=True):
		file = self.ui.LNE_footageDir.text()

		if choose:
			file = nuke.getFilename('Choose directory where footage is located')

		if os.path.exists(file) and not os.path.isdir(file):
			file = os.path.dirname(file)

		if os.path.exists(file):
			self.baseDir = file

			self.ui.BTN_edl.setEnabled(True)

			if choose:
				self.ui.LNE_footageDir.setText(file)
		else:
			self.ui.BTN_edl.setEnabled(False)

	def handleEDLImport(self):
		file = nuke.getFilename('Import EDL', pattern='*.edl')
		fps = self.ui.CMB_fps.currentText()
		parser = Parser(fps)

		if not file or not os.path.exists(file) or os.path.isdir(file):
			return

		with open(file) as f:
			edl = parser.parse(f)

			for event in edl.events:
				start, end = event.src_start_tc.frame_number, event.src_end_tc.frame_number
				clip = event.reel
				eventFootage = None

				for root, dirnames, filenames in os.walk(self.baseDir):
					for filename in fnmatch.filter(filenames, clip + '.*'):
						eventFootage = os.path.join(root, filename)

				if not eventFootage:
					nuke.message('Unable to find matching footage in specified base directory (or any of its children), aborting.')
					return

				self.handleFootageImport(files=[eventFootage])

				shots = self.shotConfig.get(eventFootage, [])
				_, frameOffset = self.reads.get(eventFootage, (None, 0))

				shots.append(ShotListItemWidget(int(event.num) * 100, startFrame=start-frameOffset, endFrame=end-frameOffset)) # TODO configuration for shot number padding

				self.shotConfig[eventFootage] = shots

	def handleImportType(self):
		edlImport = self.ui.RDO_edl.isChecked()

		self.ui.BTN_footageDir.setVisible(edlImport)
		self.ui.LNE_footageDir.setVisible(edlImport)
		self.ui.BTN_edl.setVisible(edlImport)
		self.ui.LBL_fps.setVisible(edlImport)
		self.ui.CMB_fps.setVisible(edlImport)
		self.ui.BTN_footage.setVisible(not edlImport)

	def handleProxyOptions(self, state):
		proxyEnabled = state == Qt.Checked

		self.ui.LBL_proxyFormat.setEnabled(proxyEnabled)
		self.ui.CMB_proxyFormat.setEnabled(proxyEnabled)
		self.ui.LBL_proxyDownscale.setEnabled(proxyEnabled)
		self.ui.CMB_proxyDownscale.setEnabled(proxyEnabled)
		self.ui.CHK_proxyToSubdir.setEnabled(proxyEnabled)
		self.ui.LNE_proxySubdir.setEnabled(proxyEnabled and self.ui.CHK_proxyToSubdir.isChecked())
		self.ui.CHK_proxyNameAppend.setEnabled(proxyEnabled)
		self.ui.LNE_proxyNameAppend.setEnabled(proxyEnabled and self.ui.CHK_proxyNameAppend.isChecked())

	def handleProxySubdirOption(self, state):
		self.ui.LNE_proxySubdir.setEnabled(state == Qt.Checked)

	def handleProxyNameOption(self, state):
		self.ui.LNE_proxyNameAppend.setEnabled(state == Qt.Checked)

	def handleDownscaleOption(self, state):
		self.ui.CMB_downscale.setEnabled(state == Qt.Checked)

	def handleFootageImport(self, files=[]):
		if not files:
			files = nuke.getFilename('Import footage', pattern=' '.join(IngestPanel.FOOTAGE_FORMATS), multiple=True)

		if not files:
			return

		for file in files:
			if file in self.footage:
				return

			self.footage.append(file)
			self.ui.LST_files.addItem(file)

			read = nuke.nodes.Read()

			read['file'].fromUserText(file)

			fps = self.ui.CMB_fps.currentText()
			viewerNode = nuke.activeViewer().node()
			viewerStart, viewerEnd = viewerNode.knob('frame_range').value().split('-')

			viewerNode.knob('frame_range').setValue('0-{}'.format(viewerEnd)) # Set viewer so start frame is 0
			nuke.activeViewer().frameControl(-6) # Set it so the viewer is actually at 0 prior to querying the timecode metadata

			frameOffset = Timecode(fps, read.metadata().get('r3d/absolute_time_code', '00:00:00:00')).frame_number

			self.reads[file] = (read, frameOffset)

	def stowShotConfig(self, clearTable=True):
		# Stow the currently created shot data for this footage
		if self.currFootage and self.ui.TBL_shots.rowCount() > 0:
			shots = []

			for row in range(self.ui.TBL_shots.rowCount()):
				widgets = []

				for col in range(7):
					widgets.append(self.ui.TBL_shots.cellWidget(row, col))

				shots.append(ShotListItemWidget.fromWidgets(widgets))

			self.shotConfig[self.currFootage] = shots

			if clearTable:
				self.ui.TBL_shots.setRowCount(0)

	def checkCanIngest(self):
		hasFootageSelection = len(self.ui.LST_files.selectedItems()) > 0
		hasShots = True # Set to True until proven otherwise
		hasMappings = self.ui.TBL_mappings.rowCount() > 0

		self.stowShotConfig(clearTable=False)

		for row in range(self.ui.LST_files.count()):
			footage = self.ui.LST_files.item(row).text()

			if not self.shotConfig.get(footage):
				hasShots = False
				break

		help = ['Select footage to import from list, add shot(s) for each one and add at least 1 mapping', '']

		self.ui.LBL_ingestHelp.setText(help[hasFootageSelection and hasShots and hasMappings])
		self.ui.BTN_ingest.setEnabled(hasFootageSelection and hasShots and hasMappings)

	def handleFootageSelection(self):
		selections = self.ui.LST_files.selectedItems()
		numSelected = len(selections)
		hasSelection = numSelected > 0

		self.ui.BTN_rmFootage.setEnabled(hasSelection)
		self.ui.BTN_shot.setEnabled(numSelected == 1)

		self.stowShotConfig()

		if numSelected == 1:
			self.ui.BTN_shot.setEnabled(True)
			self.currFootage = selections[0].text()
			shots = self.shotConfig.get(self.currFootage, [])

			for shot in shots:
				self.handleAddShot(shot.getWidgets())

		self.checkCanIngest()

	def handleRemoveFootage(self):
		for item in self.ui.LST_files.selectedItems():
			self.ui.LST_files.takeItem(self.ui.LST_files.row(item))
			self.footage.remove(item.text())
			self.shotConfig.pop(item.text(), None)

	def handleMappingImport(self):
		file = nuke.getFilename('Choose mapping config file', pattern='*.csv')

		self.ui.LNE_mappingFile.setText(file)
		self.populateMappings(file)

	def handleAddMapping(self):
		index = self.ui.TBL_mappings.rowCount()

		self.ui.TBL_mappings.setRowCount(index + 1)

		removeButton = QPushButton('-')

		removeButton.clicked.connect(lambda r=index: self.handleRemoveMapping(r))
		self.ui.TBL_mappings.setCellWidget(index, 0, removeButton)
		self.ui.TBL_mappings.setCellWidget(index, 1, QLineEdit())
		self.ui.TBL_mappings.setCellWidget(index, 2, QLineEdit())

		self.ui.TBL_mappings.setColumnWidth(0, 25)
		self.ui.TBL_mappings.resizeRowsToContents()
		self.checkCanIngest()

	def populateMappings(self, file):
		with open(file, 'rb') as csvfile:
			reader = csv.reader(csvfile, delimiter=',', quotechar='|')
			tableRow = 0
			self.mappings = {}

			try:
				for row in reader:
					key = row[0].strip()
					val = row[1].strip()

					if key not in self.mappings:
						removeButton = QPushButton('-')

						removeButton.clicked.connect(lambda r=tableRow: self.handleRemoveMapping(r))

						self.ui.TBL_mappings.setRowCount(tableRow + 1)
						self.ui.TBL_mappings.setCellWidget(tableRow, 0, removeButton)
						self.ui.TBL_mappings.setCellWidget(tableRow, 1, QLineEdit(key))
						self.ui.TBL_mappings.setCellWidget(tableRow, 2, QLineEdit(val))

						self.mappings[key] = val
						tableRow += 1

				self.ui.TBL_mappings.setColumnWidth(0, 25)
				self.ui.TBL_mappings.resizeRowsToContents()
			except csv.Error:
				nuke.message('Invalid CSV file')

		self.checkCanIngest()

	def handleRemoveMapping(self, row):
		key = self.ui.TBL_mappings.cellWidget(row, 1).text()
		self.ui.TBL_mappings.removeRow(row)

		for row in range(self.ui.TBL_mappings.rowCount()):
			removeButton = self.ui.TBL_mappings.cellWidget(row, 0)

			removeButton.clicked.disconnect()
			removeButton.clicked.connect(lambda r=row: self.handleRemoveMapping(r))

		self.checkCanIngest()

	def handleAddShot(self, widgets=None):
		index = self.ui.TBL_shots.rowCount()
		widgets = ShotListItemWidget(index + 1).getWidgets() if not widgets else widgets

		self.ui.TBL_shots.setRowCount(index + 1)

		for i, widg in enumerate(widgets):
			self.ui.TBL_shots.setCellWidget(index, i, widg)

			if i == 0: # The delete button
				widg.clicked.connect(lambda r=index: self.handleRemoveShot(r))

		self.ui.TBL_shots.setColumnWidth(0, 25)
		self.ui.TBL_shots.resizeRowsToContents()
		self.checkCanIngest()

	def handleRemoveShot(self, row):
		self.ui.TBL_shots.removeRow(row)

		shots = self.shotConfig.get(self.currFootage, [])

		if shots:
			shots.pop(row)

		for row in range(self.ui.TBL_shots.rowCount()):
			removeButton = self.ui.TBL_shots.cellWidget(row, 0)

			removeButton.clicked.disconnect()
			removeButton.clicked.connect(lambda r=row: self.handleRemoveShot(r))

		self.checkCanIngest()

	def handleAddMetadata(self):
		index = self.ui.TBL_metadata.rowCount()

		self.ui.TBL_metadata.setRowCount(index + 1)

		removeButton = QPushButton('-')

		removeButton.clicked.connect(lambda r=index: self.handleRemoveMetadata(r))
		self.ui.TBL_metadata.setCellWidget(index, 0, removeButton)
		self.ui.TBL_metadata.setCellWidget(index, 1, QLineEdit())
		self.ui.TBL_metadata.setCellWidget(index, 2, QLineEdit())

		self.ui.TBL_metadata.setColumnWidth(0, 25)
		self.ui.TBL_metadata.resizeRowsToContents()

	def handleRemoveMetadata(self, row):
		key = self.ui.TBL_metadata.cellWidget(row, 1).text()
		self.ui.TBL_metadata.removeRow(row)

		for row in range(self.ui.TBL_metadata.rowCount()):
			removeButton = self.ui.TBL_metadata.cellWidget(row, 0)

			removeButton.clicked.disconnect()
			removeButton.clicked.connect(lambda r=row: self.handleRemoveMetadata(r))

	def parseMappings(self):
		mappings = {}
		keyFinderRegex = re.compile(r'(\{\w+\})')

		for row in range(self.ui.TBL_mappings.rowCount()):
			key = self.ui.TBL_mappings.cellWidget(row, 1).text()
			keyPattern = key.replace('.', r'\.')
			keys = keyFinderRegex.findall(key)

			for var in keys:
				keyPattern = keyPattern.replace(var, '(.+)')

			mappings[row] = (keyPattern, keys)

		return mappings

	def parseMetadata(self):
		metaKeys = []

		for row in range(self.ui.TBL_metadata.rowCount()):
			key = self.ui.TBL_metadata.cellWidget(row, 1).text()
			val = self.ui.TBL_metadata.cellWidget(row, 2).text()

			metaKeys.append('{{set ingest/{key} "\\{val}"}}'.format(key=key, val=val))

		return '\n'.join(metaKeys)

	def getDownscale(self):
		scales = [0.75, 0.66, 0.5, 0.33, 0.25]

		return (self.ui.CHK_downscale.isChecked(), scales[self.ui.CMB_downscale.currentIndex()])

	def getProxySequence(self):
		isProxyEnabled = self.ui.CHK_proxy.isChecked()
		imageTypes = [5, 9, 11, 12] # Maps the indexes of our dropdown to the dropdown in the Write node
		scales = [1.0, 0.75, 0.5, 0.25]
		proxyFormat = imageTypes[self.ui.CMB_proxyFormat.currentIndex()]
		proxyScale = scales[self.ui.CMB_proxyDownscale.currentIndex()]
		exportSubdir = self.ui.CHK_proxyToSubdir.isChecked()
		subdir = self.ui.LNE_proxySubdir.text()
		proxyAppend = self.ui.LNE_proxyNameAppend.text() if self.ui.CHK_proxyNameAppend.isChecked() else ''

		return (isProxyEnabled, proxyFormat, proxyScale, exportSubdir, subdir, proxyAppend)

	def ingest(self):
		mappings = self.parseMappings()

		self.stowShotConfig(clearTable=False) # Stow current footage shot modifications first

		# Loop over every selected piece of footage
		for footage, (read, _) in self.reads.iteritems():
			newOutput = None

			for row in range(self.ui.TBL_mappings.rowCount()): # Every mapping
				output = self.ui.TBL_mappings.cellWidget(row, 2).text() # What we should map to (without vars replaced)
				keyPattern, keys = mappings[row] # keyPattern is for regx, keys will equate to groups in the regx match

				match = re.match(keyPattern, footage)

				if match:
					newOutput = output

					for i, group in enumerate(match.groups()):
						newOutput = newOutput.replace(keys[i], group) # Replace the vars in the output from above with what the match found (per-group)

					break # Found one match, no need to parse more mappings

			if newOutput:
				lastNode = read
				shots = self.shotConfig.get(footage, []) # Get all the shots for this particular footage
				writeNodes = ()
				frameRanges = ()
				outputDir, outputFile = os.path.split(newOutput)
				outputBase, outputExt = os.path.splitext(outputFile)
				newOutput = os.path.join(outputDir, '{}.exr'.format(outputBase))
				downscale, scale = self.getDownscale()

				if downscale:
					reformat = nuke.nodes.Reformat()
					lastNode = reformat

					reformat.knob('type').setValue(2) # Set type to "scale"
					reformat.knob('scale').setValue(scale)
					reformat.setInput(0, read)

				# Add metadata
				mmd = nuke.nodes.ModifyMetaData()

				mmd['metadata'].fromScript(self.parseMetadata())
				mmd.setInput(0, lastNode)

				for shot in shots:

					if self.ui.CHK_colorspace.isChecked(): # Set hardcoded colorspace values (TODO: change from hardcode)
						read.knob('r3d_colorspace').setValue('DRAGONcolor2')

					write = nuke.nodes.Write()

					# SHOT variable should be replaced with the shot number that the user added
					write.knob('file').setValue(newOutput.replace('{SHOT}', str(shot.shot)))

					write.knob('file_type').setValue(3) # Set to output exrs
					write.knob('metadata').setValue(3) # Set to "all metadata except input/*"
					write.knob('create_directories').setValue(1)

					shotHandles = 0 if not shot.handles else shot.handleLength
					shotStart = max(shot.startFrame - shotHandles, int(read.knob('first').value())) # Clamp at frame start for the clip
					shotEnd = min(shot.endFrame + shotHandles, int(read.knob('last').value())) # Clamp at frame end for the clip
					shotInc = shot.inc
					frameRange = (shotStart, shotEnd, shotInc)

					write.setInput(0, mmd)

					frameRanges += (frameRange,)
					writeNodes += (write,)

					cmd = self.ui.LNE_script.text()

					if cmd:
						cmd = cmd.replace('{SHOT}', str(shot.shot))
						cmd = cmd.replace('{START}', str(shot.startFrame))
						cmd = cmd.replace('{END}', str(shot.endFrame))

						os.system(cmd)

					isProxyEnabled, proxyFormat, proxyScale, exportSubdir, subdir, proxyAppend = self.getProxySequence()

					if isProxyEnabled:
						proxyWrite = nuke.nodes.Write()
						proxyDir, origName = os.path.split(newOutput.replace('{SHOT}', str(shot.shot)))
						baseName, ext = os.path.splitext(origName)

						if exportSubdir:
							proxyDir = os.path.join(proxyDir, subdir.lstrip(os.sep))

						proxyWrite.knob('file_type').setValue(proxyFormat)

						newName = '{}{}.{}'.format(baseName, proxyAppend, proxyWrite.knob('file_type').value())

						proxyWrite.knob('file').setValue(os.path.join(proxyDir, newName))
						proxyWrite.knob('create_directories').setValue(1)

						if proxyScale != 1.0:
							reformat = nuke.nodes.Reformat()

							reformat.knob('type').setValue(2) # Set type to "scale"
							reformat.knob('scale').setValue(proxyScale)

							reformat.setInput(0, mmd)
							proxyWrite.setInput(0, reformat)
						else:
							proxyWrite.setInput(0, mmd)

						frameRanges += (frameRange,)
						writeNodes += (proxyWrite,)

				for i, write in enumerate(writeNodes):
					nuke.execute(write, *frameRanges[i])

			else: # No mappings found
				pass

def createPanel():
	pane = nuke.getPaneFor('com.sashaouellet.ingest')

	nukescripts.panels.registerWidgetAsPanel('IngestPanel', 'Ingest', 'com.sashaouellet.Ingest', True).addToPane(pane)