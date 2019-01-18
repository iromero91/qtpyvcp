"""Tool Table data plugin.

Exposes all the info available in the tool table. Watches the
tool table file for changes and re-loads as needed.
"""

import os

from qtpy.QtCore import QFileSystemWatcher, QTimer

from qtpyvcp.utilities.info import Info
from qtpyvcp.utilities.logger import getLogger
from qtpyvcp.plugins import QtPyVCPDataPlugin, QtPyVCPDataChannel, getPlugin

STATUS = getPlugin('status')
INFO = Info()

# Set up logging
LOG = getLogger(__name__)

#                          E X A M P L E   I N T E R F A C E
# tooltable:current_tool?            # will return the current tool data dictionary
# tooltable:current_tool?diameter    # will return the current tool diameter
# toollife:current_tool?hours

DEFAULT_TOOL = {
    'A': 0.0,
    'B': 0.0,
    'C': 0.0,
    'D': 0.0,
    'I': 0.0,
    'J': 0.0,
    'P': -1,
    'Q':  0,
    'T': -1,
    'U': 0.0,
    'V': 0.0,
    'W': 0.0,
    'X': 0.0,
    'Y': 0.0,
    'Z': 0.0,
    'comment': '',
}

NO_TOOL = DEFAULT_TOOL.copy()
NO_TOOL.update({'T': 0,
                'comment': 'No Tool Loaded'})

HEADER_LABELS = {
    'A': 'A Offset',
    'B': 'B Offset',
    'C': 'C Offset',
    'D': 'Diameter',
    'I': 'Fnt Ang',
    'J': 'Bak Ang',
    'P': 'Pocket',
    'Q': 'Orient',
    'T': 'Tool',
    'U': 'U Offset',
    'V': 'V Offset',
    'W': 'W Offset',
    'X': 'X Offset',
    'Y': 'Y Offset',
    'Z': 'Z Offset',
}

class CurrentTool(QtPyVCPDataChannel):
    """Current tool data channel.
    """

    def __init__(self):
        super(CurrentTool, self).__init__()

        self._value = NO_TOOL

    @property
    def value(self):
        return self._value

    @property
    def number(self):
        return self._value['T']

    @property
    def pocket(self):
        return self._value['P']

    @property
    def diameter(self):
        return self._value['D']

    @property
    def x_offset(self):
        return self._value['X']

    @property
    def y_offset(self):
        return self._value['Y']

    @property
    def z_offset(self):
        return self._value['Z']

    @property
    def a_offset(self):
        return self._value['A']

    @property
    def b_offset(self):
        return self._value['B']

    @property
    def c_offset(self):
        return self._value['C']

    @property
    def u_offset(self):
        return self._value['U']

    @property
    def v_offset(self):
        return self._value['V']

    @property
    def w_offset(self):
        return self._value['W']

    @property
    def front_angle(self):
        return self._value['I']

    @property
    def back_angle(self):
        return self._value['J']

    @property
    def orientation(self):
        return self._value['Q']

    @property
    def comment(self):
        return self._value['comment']

    def _update(self, value):
        self._value = value
        self.valueChanged.emit(value)


class ToolTable(QtPyVCPDataPlugin):

    protocol = 'tooltable'

    # data channels
    current_tool = CurrentTool()

    TOOL_TABLE = {}

    def __init__(self, columns='TPXYZD'):
        super(ToolTable, self).__init__()

        self.fs_watcher = None
        self.orig_header = ''

        self.columns = self.validateColumns(columns) or [c for c in 'TPXYZD']

        self.tool_table_file = INFO.getToolTableFile()
        if not os.path.exists(self.tool_table_file):
            return

        if self.TOOL_TABLE == {}:
            self.loadToolTable()

        self.current_tool._update(self.TOOL_TABLE[STATUS.tool_in_spindle.value])

        # update signals
        STATUS.tool_in_spindle.onValueChanged(self.onToolChanged)

    def initialise(self):
        self.fs_watcher = QFileSystemWatcher()
        self.fs_watcher.addPath(self.tool_table_file)
        self.fs_watcher.fileChanged.connect(self.onToolTableFileChanged)

    @staticmethod
    def validateColumns(columns):
        """Validate display column specification.

        The user can specify columns in multiple ways, method is used to make
        sure that that data is validated and converted to a consistent format.

        Args:
            columns (str | list) : A string or list of the column IDs
                that should be shown in the tooltable.

        Returns:
            None if not valid, else a list of uppercase column IDs.
        """
        if not isinstance(columns, (basestring, list, tuple)):
            return

        return [col for col in [col.strip().upper() for col in columns]
                if col in 'TPXYZABCUVWDIJQ' and not col == '']

    def onToolTableFileChanged(self, path):
        LOG.debug('Tool Table file changed: {}'.format(path))
        # ToolEdit deletes the file and then rewrites it, so wait
        # a bit to ensure the new data has been writen out.
        QTimer.singleShot(50, self.reloadToolTable)

    def onToolChanged(self, tool_num):
        self.current_tool._update(self.TOOL_TABLE[tool_num])

    def reloadToolTable(self):
        # rewatch the file if it stop being watched because it was deleted
        if self.tool_table_file not in self.fs_watcher.files():
            self.fs_watcher.addPath(self.tool_table_file)

        # reload with the new data
        self.loadToolTable()

    def loadToolTable(self):

        if not os.path.exists(self.tool_table_file):
            LOG.critical("Tool table file does not exist: {}".format(self.tool_table_file))
            return

        with open(self.tool_table_file, 'r') as fh:
            lines = fh.readlines()

        table = {0: NO_TOOL,}

        for line in lines:

            line = line.strip()
            data, sep, comment = line.partition(';')

            tool = DEFAULT_TOOL.copy()
            for item in data.split():
                descriptor = item[0]
                if descriptor in 'TPXYZABCUVWDIJQ':
                    value = item.lstrip(descriptor)
                    if descriptor in ('T', 'P', 'Q'):
                        try:
                            tool[descriptor] = int(value)
                        except:
                            LOG.error('Error converting value to int: {}'.format(value))
                            break
                    else:
                        try:
                            tool[descriptor] = float(value)
                        except:
                            LOG.error('Error converting value to float: {}'.format(value))
                            break

            tool['comment'] = comment.strip()

            tnum = tool['T']
            if tnum == -1:
                continue

            # add the tool to the table
            table[tnum] = tool

        # update tooltable
        self.__class__.TOOL_TABLE = table

        self.current_tool._update(self.TOOL_TABLE[STATUS.tool_in_spindle.value])

        # import json
        # print json.dumps(table, sort_keys=True, indent=4)

    def saveToolTable(self, columns=None, tool_file=None):
        """Write tooltable data to file.

        Args:
            columns (str | list) : A list of data columns to write.
                If `None` will use the value of ``self.columns``.
            tool_file (str) : Path to write the tooltable too.
                Defaults to ``self.tool_table_file``.
        """

        columns = self.validateColumns(columns) or self.columns

        if tool_file is None:
            tool_file = self.tool_table_file

        lines = []

        # create the table header
        items = []
        for col in columns:
            w = (6 if col in 'TPQ' else 8) - 1 if col == self.columns[0] else 0
            items.append('{:<{w}}'.format(HEADER_LABELS[col], w=w))

        items.append('Comment')
        lines.append(';' + ' '.join(items))

        # add the tools
        for tool_num in sorted(self.TOOL_TABLE.iterkeys()):
            items = []
            tool_data = self.TOOL_TABLE[tool_num]
            for col in columns:
                items.append('{col}{val:<{w}}'
                             .format(col=col,
                                     val=tool_data[col],
                                     w=6 if col in 'TPQ' else 8))

            comment = tool_data.get('comment', '')
            if comment is not '':
                items.append(';' + comment)

            lines.append(''.join(items))

        # write to file
        with open(tool_file, 'w') as fh:
            fh.write('\n'.join(lines))
