
# -*- coding: utf-8 -*-
from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtWidgets import (
    QAction, QDialog, QVBoxLayout, QFormLayout, QComboBox, QCheckBox, QLineEdit,
    QPushButton, QMessageBox, QHBoxLayout
)
from qgis.PyQt.QtGui import QIcon

from qgis.core import (
    QgsProject, QgsVectorLayer, QgsWkbTypes, QgsFeature, QgsFields, QgsField,
    QgsGeometry, QgsPointXY, QgsCoordinateReferenceSystem, QgsCoordinateTransform
)
from qgis.utils import iface
import math, json, os

# Cargar recursos (icono desde resources.py si existe)
try:
    from .resources import *
except Exception:
    pass

# Selector de proyecciones (si está disponible)
try:
    from qgis.gui import QgsProjectionSelectionWidget
    HAS_PROJ_WIDGET = True
except Exception:
    HAS_PROJ_WIDGET = False

# ---- Por defecto
DEFAULT_FIELD_X = 'Coordenada X'
DEFAULT_FIELD_Y = 'Coordenada Y'
DEFAULT_FIELD_L = 'Longitud'
TARGET_SHEET_NAME = 'evaluación_itinerario'
TARGET_UBIC_NAME = 'ubicaciones prueba'  # para preselección amigable
CRS_METRIC_EPSG = 25830  # ETRS89 / UTM 30N (metros)

def load_plugin_icon():
    """
    Carga robustamente el icono del plugin:
    1) Recurso empaquetado (:/icons/sendas.svg o :/icons/senda.svg)
    2) Ruta física relativa al plugin (icons/sendas.svg o icons/senda.svg)
    """
    candidates = [
        ':/icons/sendas.svg',
        ':/icons/senda.svg',
        os.path.join(os.path.dirname(__file__), 'icons', 'sendas.svg'),
        os.path.join(os.path.dirname(__file__), 'icons', 'senda.svg'),
    ]
    for path in candidates:
        ic = QIcon(path)
        # QIcon no tiene isNull en todas las builds, pero si el archivo no existe, normalmente no se carga
        try:
            if not ic.isNull():
                return ic
        except Exception:
            # Si no hay isNull, intentamos devolver el primero que sea de archivo existente
            if os.path.isfile(path):
                return ic
    return QIcon()  # vacío si no hay icono disponible


class TramosItinerarioPlugin:
    """Plugin QGIS: acción en menú y barra, abre diálogo y ejecuta lógica."""
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        icon = load_plugin_icon()
        self.action = QAction(icon, 'Tramos sobre track (25830)', self.iface.mainWindow())
        self.action.setToolTip('Generar tramos desde hoja "evaluación_itinerario" + ubicaciones (EPSG:25830)')
        self.action.triggered.connect(self.run)
        # Añadir a menú y barra
        self.iface.addPluginToMenu('Itinerarios', self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu('Itinerarios', self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        dlg = ItinerarioDialog(self.iface)
        dlg.show()
        dlg.exec_()


# -------------------- Helpers --------------------

def get_loaded_table_layers():
    return [lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and not lyr.isSpatial()]

def get_loaded_line_layers():
    return [lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsVectorLayer) and QgsWkbTypes.geometryType(lyr.wkbType()) == QgsWkbTypes.LineGeometry]

def to_float(val):
    if val in (None, ''):
        return None
    try:
        return float(str(val).strip().replace(',', '.'))
    except Exception:
        return None

def deep_copy_geometry(geom):
    if not geom or geom.isEmpty():
        return None
    try:
        return QgsGeometry.fromWkb(geom.asWkb())
    except Exception:
        return QgsGeometry.fromWkt(geom.asWkt())

def transform_geometry(geom, ct):
    g = deep_copy_geometry(geom)
    if not g or g.isEmpty():
        return None
    if g.transform(ct) != 0:
        return None
    return g

def transform_point_xy(pt_xy, ct):
    try:
        return ct.transform(pt_xy)
    except Exception:
        return None

def polylines_from_json(geom):
    res = []
    try:
        gj = json.loads(geom.asJson())
        t = gj.get('type')
        coords = gj.get('coordinates', [])
        if t == 'LineString' and isinstance(coords, list) and len(coords) >= 2:
            res.append([QgsPointXY(c[0], c[1]) for c in coords])
        elif t == 'MultiLineString' and isinstance(coords, list):
            for ring in coords:
                if isinstance(ring, list) and len(ring) >= 2:
                    res.append([QgsPointXY(c[0], c[1]) for c in ring])
    except Exception:
        pass
    return res

def polylines_from_native(geom):
    res = []
    try:
        pts = geom.asPolyline()
        if pts and len(pts) > 0:
            res.append([QgsPointXY(p.x(), p.y()) for p in pts])
        else:
            mpts = geom.asMultiPolyline()
            if mpts and len(mpts) > 0:
                for ring in mpts:
                    if ring and len(ring) >= 2:
                        res.append([QgsPointXY(p.x(), p.y()) for p in ring])
    except Exception:
        pass
    return res

def polylines_from_vertices(geom):
    pts = []
    try:
        it = geom.vertices()
        for v in it:
            pts.append(QgsPointXY(v.x(), v.y()))
    except Exception:
        pass
    return [pts] if len(pts) >= 2 else []

def geom_to_polylines_robust(geom):
    if not geom or geom.isEmpty():
        return []
    try:
        merged = geom.lineMerge()
        if merged and not merged.isEmpty():
            geom = merged
    except Exception:
        pass
    res = polylines_from_json(geom)
    if res: return res
    res = polylines_from_native(geom)
    if res: return res
    res = polylines_from_vertices(geom)
    return res

def line_total_length_xy(points):
    if not points or len(points) < 2:
        return 0.0
    L = 0.0
    for i in range(1, len(points)):
        dx = points[i].x() - points[i-1].x()
        dy = points[i].y() - points[i-1].y()
        L += math.hypot(dx, dy)
    return L

def interpolate_point_along_line(points, measure):
    if not points:
        return None
    if len(points) == 1:
        return points[0]
    if measure <= 0:
        return points[0]
    acc = 0.0
    for i in range(1, len(points)):
        p0, p1 = points[i-1], points[i]
        seg_len = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
        if acc + seg_len >= measure:
            t = 0.0 if seg_len == 0 else (measure - acc) / seg_len
            x = p0.x() + t * (p1.x() - p0.x())
            y = p0.y() + t * (p1.y() - p0.y())
            return QgsPointXY(x, y)
        acc += seg_len
    return points[-1]

def segment_at_measure(points, measure):
    if not points or len(points) < 2:
        return None
    if measure <= 0:
        return (1, points[0], points[1], 0.0)
    acc = 0.0
    for i in range(1, len(points)):
        p0, p1 = points[i-1], points[i]
        seg_len = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
        if acc + seg_len >= measure:
            t = 0.0 if seg_len == 0 else (measure - acc) / seg_len
            return (i, p0, p1, t)
        acc += seg_len
    i = len(points) - 1
    return (i, points[i-1], points[i], 1.0)

def slice_line_by_measures_polyline(points, start_dist, end_dist):
    total_len = line_total_length_xy(points)
    if total_len <= 0:
        return None
    s = max(0.0, float(start_dist)); e = max(0.0, float(end_dist))
    if s > e: s, e = e, s
    s = min(s, total_len); e = min(e, total_len)
    if s == e:
        p = interpolate_point_along_line(points, s)
        q = interpolate_point_along_line(points, min(s + 0.001, total_len))
        return QgsGeometry.fromPolylineXY([p, q]) if p and q else None
    start_pt = interpolate_point_along_line(points, s)
    end_pt   = interpolate_point_along_line(points, e)
    if not start_pt or not end_pt:
        return None
    sub_points = [start_pt]
    acc = 0.0
    for i in range(1, len(points)):
        p0, p1 = points[i-1], points[i]
        seg_len = math.hypot(p1.x() - p0.x(), p1.y() - p0.y())
        seg_start, seg_end = acc, acc + seg_len
        if seg_start > s and seg_start < e: sub_points.append(p0)
        if seg_end   > s and seg_end   < e: sub_points.append(p1)
        acc += seg_len
    sub_points.append(end_pt)
    cleaned = []
    for p in sub_points:
        if not cleaned or (p.x() != cleaned[-1].x() or p.y() != cleaned[-1].y()):
            cleaned.append(p)
    if len(cleaned) < 2:
        return None
    return QgsGeometry.fromPolylineXY(cleaned)

def perpendicular_tick_at(points, measure, half_len=3.0):
    info = segment_at_measure(points, measure)
    if not info:
        return None
    _, p0, p1, t = info
    px = p0.x() + t*(p1.x() - p0.x())
    py = p0.y() + t*(p1.y() - p0.y())
    dx = p1.x() - p0.x(); dy = p1.y() - p0.y()
    seg_len = math.hypot(dx, dy)
    if seg_len == 0:
        return QgsGeometry.fromPolylineXY([QgsPointXY(px, py - half_len), QgsPointXY(px, py + half_len)])
    nx, ny = -dy / seg_len, dx / seg_len
    pA = QgsPointXY(px - nx*half_len, py - ny*half_len)
    pB = QgsPointXY(px + nx*half_len, py + ny*half_len)
    return QgsGeometry.fromPolylineXY([pA, pB])


# -------------------- Diálogo principal --------------------

class ItinerarioDialog(QDialog):
    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Tramos sobre track desde hoja "evaluación_itinerario" (EPSG:25830)')
        self.setWindowModality(Qt.ApplicationModal)
        self.resize(900, 660)

        self.tables = get_loaded_table_layers()
        self.lines = get_loaded_line_layers()

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # Tabla principal (evaluación_itinerario)
        self.cmbTable = QComboBox()
        for lyr in self.tables:
            self.cmbTable.addItem(lyr.name(), lyr)
        form.addRow('Tabla (evaluación_itinerario):', self.cmbTable)
        if self.cmbTable.count() > 0:
            idx = self.cmbTable.findText(TARGET_SHEET_NAME, Qt.MatchContains)
            if idx >= 0:
                self.cmbTable.setCurrentIndex(idx)

        # Campos para la lógica (evaluación_itinerario)
        self.cmbFieldX = QComboBox()
        self.cmbFieldY = QComboBox()
        self.cmbFieldL = QComboBox()
        form.addRow('Campo X (eval.):', self.cmbFieldX)
        form.addRow('Campo Y (eval.):', self.cmbFieldY)
        form.addRow('Campo Longitud (eval. m):', self.cmbFieldL)

        # Capa de líneas (track)
        self.cmbLines = QComboBox()
        for lyr in self.lines:
            self.cmbLines.addItem(lyr.name(), lyr)
        form.addRow('Capa de líneas (track):', self.cmbLines)

        # Opciones
        self.chkUnion = QCheckBox('Unir segmentos del track (recorrido único si es posible)')
        self.chkUnion.setChecked(True)
        form.addRow('', self.chkUnion)

        self.chkAux = QCheckBox('Crear capas auxiliares (líneas y puntos)')
        self.chkAux.setChecked(True)
        form.addRow('', self.chkAux)

        # ---- NUEVO: Tabla de "ubicaciones prueba" con selección de campos X/Y
        self.cmbUbicTable = QComboBox()
        for lyr in self.tables:
            self.cmbUbicTable.addItem(lyr.name(), lyr)
        form.addRow('Tabla de ubicaciones (ubicaciones prueba):', self.cmbUbicTable)
        if self.cmbUbicTable.count() > 0:
            idxu = self.cmbUbicTable.findText(TARGET_UBIC_NAME, Qt.MatchContains)
            if idxu >= 0:
                self.cmbUbicTable.setCurrentIndex(idxu)

        self.cmbUbicX = QComboBox()
        self.cmbUbicY = QComboBox()
        form.addRow('Campo X (ubic.):', self.cmbUbicX)
        form.addRow('Campo Y (ubic.):', self.cmbUbicY)

        # Nombre base
        self.txtOutName = QLineEdit('tramos_itinerario_25830')
        form.addRow('Nombre base de capas:', self.txtOutName)

        # >>> Selector CRS al FINAL del formulario (como pediste)
        if HAS_PROJ_WIDGET:
            self.crsWidget = QgsProjectionSelectionWidget()
            self.crsWidget.setCrs(QgsCoordinateReferenceSystem.fromEpsgId(CRS_METRIC_EPSG))
            form.addRow('CRS de coordenadas (tablas):', self.crsWidget)
        else:
            self.txtCrs = QLineEdit(f'EPSG:{CRS_METRIC_EPSG}')
            form.addRow('CRS de coordenadas (tablas):', self.txtCrs)

        layout.addLayout(form)

        # Botones
        btns = QHBoxLayout()
        self.btnRun = QPushButton('Ejecutar')
        self.btnRun.setIcon(load_plugin_icon())
        self.btnCancel = QPushButton('Cancelar')
        btns.addWidget(self.btnRun)
        btns.addWidget(self.btnCancel)
        layout.addLayout(btns)

        # Conexiones
        self.cmbTable.currentIndexChanged.connect(self.populateEvalFieldCombos)
        self.cmbUbicTable.currentIndexChanged.connect(self.populateUbicFieldCombos)
        self.btnRun.clicked.connect(self.runAlgorithm)
        self.btnCancel.clicked.connect(self.reject)

        # Avisos iniciales
        if self.cmbTable.count() == 0:
            QMessageBox.warning(self, 'Falta tabla', 'No se han encontrado tablas (XLSX/ODS) cargadas en QGIS.')
        if self.cmbLines.count() == 0:
            QMessageBox.warning(self, 'Falta capa de líneas', 'No se han encontrado capas de líneas (GPX/otra) cargadas en QGIS.')

        # Inicializar combos
        self.populateEvalFieldCombos()
        self.populateUbicFieldCombos()

    def populateEvalFieldCombos(self):
        self.cmbFieldX.clear(); self.cmbFieldY.clear(); self.cmbFieldL.clear()
        table_layer = self.cmbTable.currentData()
        if not table_layer: return
        field_names = [f.name() for f in table_layer.fields()]
        self.cmbFieldX.addItems(field_names)
        self.cmbFieldY.addItems(field_names)
        self.cmbFieldL.addItems(field_names)
        # Preselecciones por defecto
        def sel(combo, name):
            idx = combo.findText(name, Qt.MatchFixedString)
            if idx >= 0: combo.setCurrentIndex(idx)
        sel(self.cmbFieldX, DEFAULT_FIELD_X)
        sel(self.cmbFieldY, DEFAULT_FIELD_Y)
        sel(self.cmbFieldL, DEFAULT_FIELD_L)

    def populateUbicFieldCombos(self):
        self.cmbUbicX.clear(); self.cmbUbicY.clear()
        ubic_layer = self.cmbUbicTable.currentData()
        if not ubic_layer: return
        field_names = [f.name() for f in ubic_layer.fields()]
        self.cmbUbicX.addItems(field_names)
        self.cmbUbicY.addItems(field_names)
        # Preselecciones por defecto
        def sel(combo, name):
            idx = combo.findText(name, Qt.MatchFixedString)
            if idx >= 0: combo.setCurrentIndex(idx)
        sel(self.cmbUbicX, DEFAULT_FIELD_X)
        sel(self.cmbUbicY, DEFAULT_FIELD_Y)

    def runAlgorithm(self):
        # Entradas principales
        table_layer = self.cmbTable.currentData()
        line_layer = self.cmbLines.currentData()
        field_x = self.cmbFieldX.currentText().strip()
        field_y = self.cmbFieldY.currentText().strip()
        field_l = self.cmbFieldL.currentText().strip()
        # Ubicaciones
        ubic_layer = self.cmbUbicTable.currentData()
        ubic_field_x = self.cmbUbicX.currentText().strip()
        ubic_field_y = self.cmbUbicY.currentText().strip()

        out_base = self.txtOutName.text().strip() or 'tramos_itinerario_25830'
        do_union = self.chkUnion.isChecked()
        do_aux = self.chkAux.isChecked()

        # Validaciones
        if not table_layer or not line_layer:
            QMessageBox.critical(self, 'Error', 'Selecciona una tabla (evaluación) y una capa de líneas.')
            return
        for f in (field_x, field_y, field_l):
            if table_layer.fields().indexFromName(f) < 0:
                QMessageBox.critical(self, 'Error', f'El campo "{f}" no existe en la tabla seleccionada.')
                return

        # CRS compartido
        crs_metric = QgsCoordinateReferenceSystem.fromEpsgId(CRS_METRIC_EPSG)
        if HAS_PROJ_WIDGET:
            crs_table = self.crsWidget.crs()
        else:
            user_crs_text = self.txtCrs.text().strip() or f'EPSG:{CRS_METRIC_EPSG}'
            crs_table = QgsCoordinateReferenceSystem.fromUserInput(user_crs_text)
        if not crs_table.isValid():
            QMessageBox.critical(self, 'Error', 'CRS de las coordenadas de las tablas no válido.')
            return

        crs_lines = line_layer.crs()
        ct_lines_to_25830 = QgsCoordinateTransform(crs_lines, crs_metric, QgsProject.instance())
        ct_table_to_25830 = QgsCoordinateTransform(crs_table, crs_metric, QgsProject.instance())

        # Track a 25830 + unir si procede
        geoms_25830 = []
        for f in line_layer.getFeatures():
            tg = transform_geometry(f.geometry(), ct_lines_to_25830)
            if tg and not tg.isEmpty():
                try:
                    lm = tg.lineMerge()
                    geoms_25830.append(lm if (lm and not lm.isEmpty()) else tg)
                except Exception:
                    geoms_25830.append(tg)

        if not geoms_25830:
            QMessageBox.critical(self, 'Error', 'No se pudieron transformar las geometrías del track a EPSG:25830.')
            return

        if do_union and len(geoms_25830) > 1:
            try:
                uni = QgsGeometry.unaryUnion(geoms_25830)
                if uni and not uni.isEmpty():
                    lm = uni.lineMerge()
                    geoms_25830 = [lm] if (lm and not lm.isEmpty()) else [uni]
            except Exception as e:
                QMessageBox.warning(self, 'Aviso',
                    f'No fue posible unir/mergear todas las líneas. Se continuará con segmentos separados.\nDetalle: {e}')

        # Capas de salida (EPSG:25830)
        tramos_layer = QgsVectorLayer(f'LineString?crs=EPSG:{CRS_METRIC_EPSG}', out_base, 'memory')
        tr_prov = tramos_layer.dataProvider()

        aux_layer = None
        aux_pts_layer = None
        if do_aux:
            aux_layer = QgsVectorLayer(f'LineString?crs=EPSG:{CRS_METRIC_EPSG}', f'{out_base}_aux', 'memory')
            aux_prov = aux_layer.dataProvider()
            aux_pts_layer = QgsVectorLayer(f'Point?crs=EPSG:{CRS_METRIC_EPSG}', f'{out_base}_aux_pts', 'memory')
            aux_pts_prov = aux_pts_layer.dataProvider()

        # --------- CAMPOS DE SALIDA (copiar TODOS los campos de evaluación) ---------
        table_fields = table_layer.fields()
        tr_fields = QgsFields()
        for fld in table_fields:
            tr_fields.append(QgsField(fld.name(), fld.type(), fld.typeName(), fld.length(), fld.precision()))
        tr_fields.append(QgsField('dist_inicio_m', QVariant.Double))
        tr_fields.append(QgsField('dist_fin_m', QVariant.Double))
        tr_prov.addAttributes(tr_fields)
        tramos_layer.updateFields()

        if do_aux:
            aux_fields = QgsFields()
            aux_fields.append(QgsField('tipo', QVariant.String))
            for fld in table_fields:
                aux_fields.append(QgsField(fld.name(), fld.type(), fld.typeName(), fld.length(), fld.precision()))
            aux_prov.addAttributes(aux_fields)
            aux_layer.updateFields()

            aux_pts_fields = QgsFields()
            aux_pts_fields.append(QgsField('tipo', QVariant.String))
            for fld in table_fields:
                aux_pts_fields.append(QgsField(fld.name(), fld.type(), fld.typeName(), fld.length(), fld.precision()))
            aux_pts_fields.append(QgsField('m_medida', QVariant.Double))
            aux_pts_prov.addAttributes(aux_pts_fields)
            aux_pts_layer.updateFields()

        # Índices para la lógica
        idx_x = table_fields.indexFromName(field_x)
        idx_y = table_fields.indexFromName(field_y)
        idx_l = table_fields.indexFromName(field_l)

        # Procesar filas de evaluación_itinerario -> crear TRAMOS y AUX
        total, errores = 0, 0
        error_msgs = []
        recorridos = geoms_25830

        for row in table_layer.getFeatures():
            try:
                x = to_float(row[field_x])
                y = to_float(row[field_y])
                tramo_m = to_float(row[field_l])

                if x is None or y is None or tramo_m is None or tramo_m <= 0:
                    errores += 1; error_msgs.append('Fila con X/Y/Longitud inválidos.'); continue

                # Punto original (tabla) -> 25830
                pt_orig_xy_25830 = transform_point_xy(QgsPointXY(x, y), ct_table_to_25830)
                if pt_orig_xy_25830 is None:
                    errores += 1; error_msgs.append('No se pudo transformar el punto de evaluación a EPSG:25830.'); continue
                pt_orig = QgsGeometry.fromPointXY(pt_orig_xy_25830)

                # Recorrido más cercano y proyección
                min_d = None; best_g = None; best_proj_pt_xy = None
                for g in recorridos:
                    info = g.closestSegmentWithContext(pt_orig.asPoint())
                    if not info: continue
                    d, mp = info[0], info[1]
                    if (min_d is None) or (d < min_d):
                        min_d = d; best_g = g; best_proj_pt_xy = QgsPointXY(mp.x(), mp.y())

                if best_g is None or best_proj_pt_xy is None:
                    errores += 1; error_msgs.append('No se pudo proyectar el punto sobre el track.'); continue

                # Extraer polilíneas robustamente
                polylines = geom_to_polylines_robust(best_g)
                if not polylines:
                    errores += 1; error_msgs.append('Track sin geometría de línea utilizable.'); continue

                # Elegir la polilínea más cercana al punto proyectado
                best_pts, best_pts_dist = None, None
                for pts in polylines:
                    if len(pts) < 2: continue
                    min_local = None
                    for i in range(1, len(pts)):
                        p0, p1 = pts[i-1], pts[i]
                        vx, vy = p1.x() - p0.x(), p1.y() - p0.y()
                        wx, wy = best_proj_pt_xy.x() - p0.x(), best_proj_pt_xy.y() - p0.y()
                        c1 = vx*wx + vy*wy
                        if c1 <= 0:
                            dist = math.hypot(best_proj_pt_xy.x() - p0.x(), best_proj_pt_xy.y() - p0.y())
                        else:
                            c2 = vx*vx + vy*vy
                            if c2 <= c1:
                                dist = math.hypot(best_proj_pt_xy.x() - p1.x(), best_proj_pt_xy.y() - p1.y())
                            else:
                                t = c1 / c2
                                projx = p0.x() + t*vx
                                projy = p0.y() + t*vy
                                dist = math.hypot(best_proj_pt_xy.x() - projx, best_proj_pt_xy.y() - projy)
                        if (min_local is None) or (dist < min_local):
                            min_local = dist
                    if min_local is not None and (best_pts is None or min_local < best_pts_dist):
                        best_pts, best_pts_dist = pts, min_local

                if not best_pts or len(best_pts) < 2:
                    errores += 1; error_msgs.append('Track sin vértices suficientes para recorte.'); continue

                # Medidas y recorte
                best_line_geom = QgsGeometry.fromPolylineXY(best_pts)
                start_dist = best_line_geom.lineLocatePoint(QgsGeometry.fromPointXY(best_proj_pt_xy))
                if start_dist is None or not math.isfinite(start_dist):
                    errores += 1; error_msgs.append('lineLocatePoint devolvió valor no válido.'); continue

                line_len = line_total_length_xy(best_pts)
                if not math.isfinite(line_len) or line_len <= 0:
                    errores += 1; error_msgs.append('Longitud del track no válida.'); continue

                end_dist = start_dist + tramo_m
                if end_dist > line_len:
                    end_dist = line_len

                # Subtramo (inicio→fin) manual
                sub = slice_line_by_measures_polyline(best_pts, start_dist, end_dist)
                if not sub or sub.isEmpty():
                    errores += 1; error_msgs.append('El subtramo resultó vacío (slice manual).'); continue

                # TRAMO: copiar TODOS los campos de evaluación + medidas
                tr_feat = QgsFeature(tramos_layer.fields())
                tr_feat.setGeometry(sub)
                attrs = row.attributes()[:] + [float(start_dist), float(end_dist)]
                tr_feat.setAttributes(attrs)
                tr_prov.addFeatures([tr_feat])
                total += 1

                # AUXILIARES líneas y puntos
                if do_aux:
                    # Línea de inicio (origen -> proyección)
                    aux_start = QgsGeometry.fromPolylineXY([pt_orig_xy_25830, best_proj_pt_xy])
                    a_feat = QgsFeature(aux_layer.fields())
                    a_feat.setGeometry(aux_start)
                    a_attrs = ['inicio'] + row.attributes()[:]
                    a_feat.setAttributes(a_attrs)
                    aux_prov.addFeatures([a_feat])

                    # Marca final perpendicular
                    tick = perpendicular_tick_at(best_pts, end_dist, half_len=3.0)
                    if tick and not tick.isEmpty():
                        b_feat = QgsFeature(aux_layer.fields())
                        b_feat.setGeometry(tick)
                        b_attrs = ['fin'] + row.attributes()[:]
                        b_feat.setAttributes(b_attrs)
                        aux_prov.addFeatures([b_feat])

                    # Punto inicio (proyección exacta)
                    p_start = QgsFeature(aux_pts_layer.fields())
                    p_start.setGeometry(QgsGeometry.fromPointXY(best_proj_pt_xy))
                    p_start_attrs = ['inicio'] + row.attributes()[:] + [float(start_dist)]
                    p_start.setAttributes(p_start_attrs)
                    aux_pts_prov.addFeatures([p_start])

                    # Punto fin (coordenada interpolada)
                    end_point_xy = interpolate_point_along_line(best_pts, end_dist)
                    if end_point_xy:
                        p_end = QgsFeature(aux_pts_layer.fields())
                        p_end.setGeometry(QgsGeometry.fromPointXY(end_point_xy))
                        p_end_attrs = ['fin'] + row.attributes()[:] + [float(end_dist)]
                        p_end.setAttributes(p_end_attrs)
                        aux_pts_prov.addFeatures([p_end])

            except Exception as e:
                errores += 1
                error_msgs.append(str(e))

        # Añadir capas de tramos y auxiliares
        tramos_layer.updateFields(); tramos_layer.updateExtents()
        QgsProject.instance().addMapLayer(tramos_layer)
        if do_aux:
            aux_layer.updateFields(); aux_layer.updateExtents()
            QgsProject.instance().addMapLayer(aux_layer)
            aux_pts_layer.updateFields(); aux_pts_layer.updateExtents()
            QgsProject.instance().addMapLayer(aux_pts_layer)

        # ---- NUEVO: generar capa de puntos desde "ubicaciones prueba" (con X/Y seleccionables) ----
        ubic_total = 0
        if ubic_layer:
            # Validar selección de campos en la tabla de ubicaciones
            if (not ubic_field_x) or (ubic_layer.fields().indexFromName(ubic_field_x) < 0) or \
               (not ubic_field_y) or (ubic_layer.fields().indexFromName(ubic_field_y) < 0):
                QMessageBox.warning(self, 'Aviso ubicaciones',
                    'Selecciona correctamente los campos X/Y de la tabla de ubicaciones.')
            else:
                ubic_pts_name = f'{out_base}_ubicaciones_pts'
                ubic_pts_layer = QgsVectorLayer(f'Point?crs=EPSG:{CRS_METRIC_EPSG}', ubic_pts_name, 'memory')
                ubic_prov = ubic_pts_layer.dataProvider()

                # Copiar TODOS los campos de la tabla de ubicaciones
                ubic_fields = QgsFields()
                for fld in ubic_layer.fields():
                    ubic_fields.append(QgsField(fld.name(), fld.type(), fld.typeName(), fld.length(), fld.precision()))
                ubic_prov.addAttributes(ubic_fields)
                ubic_pts_layer.updateFields()

                # Transformación: misma que eval (crs_table -> 25830)
                for rowu in ubic_layer.getFeatures():
                    try:
                        x = to_float(rowu[ubic_field_x])
                        y = to_float(rowu[ubic_field_y])
                        if x is None or y is None:
                            continue
                        xy_src = QgsPointXY(x, y)
                        xy_25830 = transform_point_xy(xy_src, ct_table_to_25830)
                        if xy_25830 is None:
                            continue
                        feat = QgsFeature(ubic_pts_layer.fields())
                        feat.setGeometry(QgsGeometry.fromPointXY(xy_25830))
                        feat.setAttributes(rowu.attributes()[:])  # todas las columnas
                        ubic_prov.addFeatures([feat])
                        ubic_total += 1
                    except Exception:
                        pass

                ubic_pts_layer.updateFields()
                ubic_pts_layer.updateExtents()
                QgsProject.instance().addMapLayer(ubic_pts_layer)

        # Mensaje final
        msg = (f'Se han creado {total} tramos en EPSG:25830. '
               f'Filas con error (evaluación): {errores}.')
        if ubic_layer:
            msg += f'\nCapa de ubicaciones: {ubic_total} puntos creados.'
        if errores > 0 and error_msgs:
            uniq = []
            for m in error_msgs:
                if m not in uniq: uniq.append(m)
            msg += '\n\nPrincipales causas detectadas:\n- ' + '\n- '.join(uniq[:6])
        QMessageBox.information(self, 'Listo', msg)
        self.accept()
