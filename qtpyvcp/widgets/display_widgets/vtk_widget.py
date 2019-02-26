from collections import defaultdict

import vtk

from qtpy.QtWidgets import QWidget, QVBoxLayout
from vtk.qt.QVTKRenderWindowInteractor import QVTKRenderWindowInteractor

from qtpyvcp.plugins import getPlugin
from qtpyvcp.widgets import VCPWidget

from vtk_cannon import VTKCanon

STATUS = getPlugin('status')


class VTKWidget(QWidget, VCPWidget):

    def __init__(self, parent=None):
        super(VTKWidget, self).__init__(parent)

        self.parent = parent
        self.status = STATUS

        self.axis = self.status.stat.axis

        self.gr = VTKCanon()

        self.vertical_layout = QVBoxLayout()
        self.vtkWidget = QVTKRenderWindowInteractor()
        self.vertical_layout.addWidget(self.vtkWidget)

        self.nav_style = vtk.vtkInteractorStyleTrackballCamera()

        self.renderer = vtk.vtkRenderer()
        self.vtkWidget.GetRenderWindow().AddRenderer(self.renderer)
        self.vtkWidget.SetInteractorStyle(self.nav_style)
        self.interactor = self.vtkWidget.GetRenderWindow().GetInteractor()

        self.machine = Machine(self.axis)
        self.machine_actor = self.machine.get_actor()
        self.machine_actor.SetCamera(self.renderer.GetActiveCamera())

        self.axes = Axes()
        self.axes_actor = self.axes.get_actor()

        self.tool = Tool()
        self.tool_actor = self.tool.get_actor()

        self.path_actors = list()

        self.renderer.SetBackground(0.36, 0.36, 0.36)

        self.renderer.AddActor(self.tool_actor)
        self.renderer.AddActor(self.machine_actor)
        self.renderer.AddActor(self.axes_actor)

        self.renderer.ResetCamera()

        self.setLayout(self.vertical_layout)

        self.interactor.Initialize()
        self.interactor.Start()

        self.status.file.notify(self.load_program)
        self.status.position.notify(self.move_tool)
        self.status.g5x_offset.notify(self.reload_program)
        self.status.g92_offset.notify(self.reload_program)
        self.status.tool_offset.notify(self.reload_program)

        self.line = None
        self._last_filename = str()

    def reload_program(self, *args, **kwargs):
        print("RELOAD")
        self.load_program(self._last_filename)

    def load_program(self, fname=None):
        print("LOAD")
        for path_actor in self.path_actors:
            self.renderer.RemoveActor(path_actor)

        if fname:
            self._last_filename = fname
        else:
            fname = self._last_filename

        self.gr.load(fname)

        path = Path(self.gr, self.renderer)
        self.path_actors = path.get_actors()

        for path_actor in self.path_actors:
            self.renderer.AddActor(path_actor)

        self.update_render()

    def move_tool(self, position):
        self.tool_actor.SetPosition(position[:3])
        self.update_render()

    def update_render(self):
        self.vtkWidget.GetRenderWindow().Render()


class Path:
    def __init__(self, gr, renderer):
        self.gr = gr

        feed_lines = len(self.gr.canon.feed)
        traverse_lines = len(self.gr.canon.traverse)
        arcfeed_lines = len(self.gr.canon.arcfeed)

        total_lines = feed_lines + traverse_lines + arcfeed_lines

        line = PathLine(self.gr, total_lines)

        path = dict()

        for traverse in self.gr.canon.traverse:
            seq = traverse[0]
            line_type = "straight_feed"
            cords = traverse[1][:3]

            path[seq] = [cords, line_type]

        for feed in self.gr.canon.feed:
            seq = feed[0]
            line_type = "traverse"
            cords = feed[1][:3]

            path[seq] = [cords, line_type]

        arc_segments = defaultdict(list)

        for index, arc in enumerate(self.gr.canon.arcfeed):

            seq = arc[0]
            line_type = "arc_feed"
            cords = arc[1][:3]
            arc_segments[seq].append((seq, [cords, line_type]))

        for point_data in path.items():
            line.add_line_point(point_data)

        for line_no, arc in arc_segments.items():
            for segment in arc:
                line.add_line_point(segment)

        line.draw_path_line()

        self.path_actor = line.get_actor()

        self.path_boundaries = PathBoundaries(renderer, self.path_actor)
        self.path_boundaries_actor = self.path_boundaries.get_actor()

    def get_actors(self):
        return [self.path_actor, self.path_boundaries_actor]


class PathLine:
    def __init__(self, gr, points):

        self.gr = gr

        self.num_points = points

        self.points = vtk.vtkPoints()
        self.lines = vtk.vtkCellArray()

        self.line_type = list()

        self.arc_data = dict()

        self.lines_poligon_data = vtk.vtkPolyData()
        self.polygon_mapper = vtk.vtkPolyDataMapper()
        self.actor = vtk.vtkActor()

    def add_line_point(self, point):
        data = point[1][0]
        line_type = point[1][1]
        self.line_type.append(line_type)
        self.points.InsertNextPoint(data)

    def draw_path_line(self):
        # https://github.com/invesalius/invesalius3/blob/3b3e3f88c2f48514e6d57e8e20f2543deac7c228/invesalius/data/measures.py
        namedColors = vtk.vtkNamedColors()

        # Create a vtkUnsignedCharArray container and store the colors in it
        colors = vtk.vtkUnsignedCharArray()
        colors.SetNumberOfComponents(3)

        for index in range(0, self.num_points-1):

            line_type = self.line_type[index]

            if line_type == "traverse" or line_type == "arc_feed":
                colors.InsertNextTypedTuple(namedColors.GetColor3ub("Mint"))
            elif line_type == "straight_feed":
                colors.InsertNextTypedTuple(namedColors.GetColor3ub("Tomato"))

            line = vtk.vtkLine()
            line.GetPointIds().SetId(0, index)  # the second 0 is the index of the Origin in linesPolyData's points
            line.GetPointIds().SetId(1, index+1)  # the second 1 is the index of P0 in linesPolyData's points
            self.lines.InsertNextCell(line)

        self.lines_poligon_data.SetPoints(self.points)
        self.lines_poligon_data.SetLines(self.lines)

        self.lines_poligon_data.GetCellData().SetScalars(colors)

        self.polygon_mapper.SetInputData(self.lines_poligon_data)
        self.polygon_mapper.Update()

        self.actor.SetMapper(self.polygon_mapper)

    def get_actor(self):
        return self.actor


class PathBoundaries:
    def __init__(self, renderer, path_actor):

        self.path_actor = path_actor

        cube_axes_actor = vtk.vtkCubeAxesActor()

        cube_axes_actor.SetBounds(self.path_actor.GetBounds())

        cube_axes_actor.SetCamera(renderer.GetActiveCamera())

        cube_axes_actor.SetXLabelFormat("%6.3f")
        cube_axes_actor.SetYLabelFormat("%6.3f")
        cube_axes_actor.SetZLabelFormat("%6.3f")

        cube_axes_actor.SetFlyModeToStaticEdges()

        cube_axes_actor.GetTitleTextProperty(0).SetColor(1.0, 0.0, 0.0)
        cube_axes_actor.GetLabelTextProperty(0).SetColor(1.0, 0.0, 0.0)

        cube_axes_actor.GetTitleTextProperty(1).SetColor(0.0, 1.0, 0.0)
        cube_axes_actor.GetLabelTextProperty(1).SetColor(0.0, 1.0, 0.0)

        cube_axes_actor.GetTitleTextProperty(2).SetColor(0.0, 0.0, 1.0)
        cube_axes_actor.GetLabelTextProperty(2).SetColor(0.0, 0.0, 1.0)

        cube_axes_actor.XAxisLabelVisibilityOff()
        cube_axes_actor.YAxisLabelVisibilityOff()
        cube_axes_actor.ZAxisLabelVisibilityOff()


        # cube_axes_actor.XAxisMinorTickVisibilityOff()
        # cube_axes_actor.YAxisMinorTickVisibilityOff()
        # cube_axes_actor.ZAxisMinorTickVisibilityOff()

        cube_axes_actor.XAxisTickVisibilityOff()
        cube_axes_actor.YAxisTickVisibilityOff()
        cube_axes_actor.ZAxisTickVisibilityOff()

        self.actor = cube_axes_actor

    def get_actor(self):
        return self.actor


class Grid:
    def __init__(self):
        x = [
            -1.22396, -1.17188, -1.11979, -1.06771, -1.01562, -0.963542,
            -0.911458, -0.859375, -0.807292, -0.755208, -0.703125, -0.651042,
            -0.598958, -0.546875, -0.494792, -0.442708, -0.390625, -0.338542,
            -0.286458, -0.234375, -0.182292, -0.130209, -0.078125, -0.026042,
            0.0260415, 0.078125, 0.130208, 0.182291, 0.234375, 0.286458,
            0.338542, 0.390625, 0.442708, 0.494792, 0.546875, 0.598958,
            0.651042, 0.703125, 0.755208, 0.807292, 0.859375, 0.911458,
            0.963542, 1.01562, 1.06771, 1.11979, 1.17188]

        y = [
            -1.25, -1.17188, -1.09375, -1.01562, -0.9375, -0.859375,
            -0.78125, -0.703125, -0.625, -0.546875, -0.46875, -0.390625,
            -0.3125, -0.234375, -0.15625, -0.078125, 0, 0.078125,
            0.15625, 0.234375, 0.3125, 0.390625, 0.46875, 0.546875,
            0.625, 0.703125, 0.78125, 0.859375, 0.9375, 1.01562,
            1.09375, 1.17188, 1.25]

        z = [
            0, 0.1, 0.2, 0.3, 0.4, 0.5,
            0.6, 0.7, 0.75, 0.8, 0.9, 1,
            1.1, 1.2, 1.3, 1.4, 1.5, 1.6,
            1.7, 1.75, 1.8, 1.9, 2, 2.1,
            2.2, 2.3, 2.4, 2.5, 2.6, 2.7,
            2.75, 2.8, 2.9, 3, 3.1, 3.2,
            3.3, 3.4, 3.5, 3.6, 3.7, 3.75,
            3.8, 3.9]

        # Create a rectilinear grid by defining three arrays specifying the
        # coordinates in the x-y-z directions.
        xCoords = vtk.vtkFloatArray()
        for i in x:
            xCoords.InsertNextValue(i)

        yCoords = vtk.vtkFloatArray()
        for i in y:
            yCoords.InsertNextValue(i)

        zCoords = vtk.vtkFloatArray()
        for i in z:
            zCoords.InsertNextValue(i)

        # The coordinates are assigned to the rectilinear grid. Make sure that
        # the number of values in each of the XCoordinates, YCoordinates,
        # and ZCoordinates is equal to what is defined in SetDimensions().
        #
        rgrid = vtk.vtkRectilinearGrid()
        rgrid.SetDimensions(len(x), len(y), len(z))
        rgrid.SetXCoordinates(xCoords)
        rgrid.SetYCoordinates(yCoords)
        rgrid.SetZCoordinates(zCoords)

        # Extract a plane from the grid to see what we've got.
        plane = vtk.vtkRectilinearGridGeometryFilter()
        plane.SetInputData(rgrid)
        plane.SetExtent(0, 46, 16, 16, 0, 43)

        rgridMapper = vtk.vtkPolyDataMapper()
        rgridMapper.SetInputConnection(plane.GetOutputPort())

        self.wire_actor = vtk.vtkActor()
        self.wire_actor.SetMapper(rgridMapper)
        self.wire_actor.GetProperty().SetRepresentationToWireframe()
        self.wire_actor.GetProperty().SetColor(0, 0, 0)

    def get_actor(self):
        return self.wire_actor


class Machine:
    def __init__(self, axis):
        cube_axes_actor = vtk.vtkCubeAxesActor()

        x_max = axis[0]["max_position_limit"]
        x_min = axis[0]["min_position_limit"]

        y_max = axis[1]["max_position_limit"]
        y_min = axis[1]["min_position_limit"]

        z_max = axis[2]["max_position_limit"]
        z_min = axis[2]["min_position_limit"]

        cube_axes_actor.SetBounds(x_min, x_max, y_min, y_max, z_min, z_max)

        cube_axes_actor.SetXLabelFormat("%6.3f")
        cube_axes_actor.SetYLabelFormat("%6.3f")
        cube_axes_actor.SetZLabelFormat("%6.3f")

        cube_axes_actor.SetFlyModeToStaticEdges()

        cube_axes_actor.GetTitleTextProperty(0).SetColor(1.0, 0.0, 0.0)
        cube_axes_actor.GetLabelTextProperty(0).SetColor(1.0, 0.0, 0.0)

        cube_axes_actor.GetTitleTextProperty(1).SetColor(0.0, 1.0, 0.0)
        cube_axes_actor.GetLabelTextProperty(1).SetColor(0.0, 1.0, 0.0)

        cube_axes_actor.GetTitleTextProperty(2).SetColor(0.0, 0.0, 1.0)
        cube_axes_actor.GetLabelTextProperty(2).SetColor(0.0, 0.0, 1.0)

        # cube_axes_actor.XAxisMinorTickVisibilityOff()
        # cube_axes_actor.YAxisMinorTickVisibilityOff()
        # cube_axes_actor.ZAxisMinorTickVisibilityOff()

        cube_axes_actor.XAxisTickVisibilityOff()
        cube_axes_actor.YAxisTickVisibilityOff()
        cube_axes_actor.ZAxisTickVisibilityOff()

        cube_axes_actor.XAxisLabelVisibilityOff()
        cube_axes_actor.YAxisLabelVisibilityOff()
        cube_axes_actor.ZAxisLabelVisibilityOff()


        # cube_axes_actor.SetXUnits("mm")  # Todo machine units here
        # cube_axes_actor.SetYUnits("mm")
        # cube_axes_actor.SetZUnits("mm")

        self.actor = cube_axes_actor

    def get_actor(self):
        return self.actor


class Axes:
    def __init__(self):
        transform = vtk.vtkTransform()
        transform.Translate(0.0, 0.0, 0.0)  # Z up

        self.actor = vtk.vtkAxesActor()
        self.actor.SetUserTransform(transform)

        self.actor.AxisLabelsOff()
        self.actor.SetShaftType(vtk.vtkAxesActor.CYLINDER_SHAFT)

    def get_actor(self):
        return self.actor


class Frustum:
    def __init__(self):
        colors = vtk.vtkNamedColors()

        camera = vtk.vtkCamera()
        camera.SetClippingRange(0.1, 0.4)
        planesArray = [0] * 24

        camera.GetFrustumPlanes(1.0, planesArray)

        planes = vtk.vtkPlanes()
        planes.SetFrustumPlanes(planesArray)

        frustumSource = vtk.vtkFrustumSource()
        frustumSource.ShowLinesOff()
        frustumSource.SetPlanes(planes)

        shrink = vtk.vtkShrinkPolyData()
        shrink.SetInputConnection(frustumSource.GetOutputPort())
        shrink.SetShrinkFactor(.9)

        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(shrink.GetOutputPort())

        back = vtk.vtkProperty()
        back.SetColor(colors.GetColor3d("Tomato"))

        self.actor = vtk.vtkActor()
        self.actor.SetMapper(mapper)
        self.actor.GetProperty().EdgeVisibilityOn()
        self.actor.GetProperty().SetColor(colors.GetColor3d("Banana"))
        self.actor.SetBackfaceProperty(back)

    def get_actor(self):
        return self.actor


class Tool:
    def __init__(self):

        self.height = 1.0

        # Create source
        source = vtk.vtkConeSource()
        source.SetResolution(128)
        source.SetHeight(self.height)
        source.SetCenter(-self.height/2, 0, 0)
        source.SetRadius(0.5)

        transform = vtk.vtkTransform()
        transform.RotateWXYZ(90, 0, 1, 0)
        transform_filter = vtk.vtkTransformPolyDataFilter()
        transform_filter.SetTransform(transform)
        transform_filter.SetInputConnection(source.GetOutputPort())
        transform_filter.Update()

        # Create a mapper
        mapper = vtk.vtkPolyDataMapper()
        mapper.SetInputConnection(transform_filter.GetOutputPort())

        # Create an actor
        self.actor = vtk.vtkActor()
        self.actor.SetMapper(mapper)

    def get_actor(self):
        return self.actor


class CoordinateWidget:
    def __init__(self, interactor):
        colors = vtk.vtkNamedColors()

        axes = vtk.vtkAxesActor()

        widget = vtk.vtkOrientationMarkerWidget()
        rgba = [0] * 4
        colors.GetColor("Carrot", rgba)
        widget.SetOutlineColor(rgba[0], rgba[1], rgba[2])
        widget.SetOrientationMarker(axes)
        widget.SetInteractor(interactor)
        widget.SetViewport(0.0, 0.0, 0.4, 0.4)
        widget.SetEnabled(1)
        widget.InteractiveOn()
