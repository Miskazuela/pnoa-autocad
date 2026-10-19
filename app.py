"""
========================================================================================
Aplicación Web: Extractor de Ortofotos PNOA (España) para AutoCAD
Desarrollador: Especialista SIG y Desarrollador Senior en Python
Descripción:
    Automatiza la extracción de ortofotografías aéreas georreferenciadas de máxima
    resolución del Plan Nacional de Ortofotografía Aérea (IGN PNOA) a partir de
    polilíneas cerradas delimitadas en planos CAD (.dxf).
    
    Genera para cada polígono la georreferenciación estándar requerida
    por AutoCAD, AutoCAD Map 3D, Civil 3D y BricsCAD:
      1. {nombre}.tif -> Imagen raster descargada del servicio WMS.
      2. {nombre}.tfw -> Archivo de calibración espacial (World File) con coordenadas exactas.

    Incluye:
      - Visor cartográfico interactivo (Satélite y PNOA WMS) para verificar la ubicación del DXF.
      - Sistema de resolución DNS ultra-resiliente (DoH fallback) para prevenir errores
        transitorios de red [Errno 11002 getaddrinfo failed] con www.ign.es.
      - Control estricto de límites de MapServer (máx. 4096 px) y modo mosaico/teselas continuo.

Comando de instalación de dependencias:
    pip install streamlit ezdxf shapely pyproj requests pandas folium streamlit-folium

Comando para ejecutar la aplicación:
    streamlit run app.py
========================================================================================
"""

import io
import os
import re
import ssl
import json
import math
import socket
import zipfile
import urllib.request
from urllib.parse import urlparse
import traceback
import concurrent.futures
from typing import List, Dict, Any, Tuple, Optional

import streamlit as st
import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import ezdxf
from shapely.geometry import Polygon
from pyproj import CRS, Transformer
import folium
from folium.plugins import Draw
from streamlit_folium import st_folium
from PIL import Image, ImageDraw, ImageChops
import xml.etree.ElementTree as ET

# Streamlit Page Config debe ser la primera llamada de Streamlit
st.set_page_config(
    page_title="GeoRaster to CAD | Extractor Georreferenciado Universal",
    page_icon="🌍",
    layout="wide",
    initial_sidebar_state="expanded"
)


# --------------------------------------------------------------------------------------
# 0. SISTEMA DE RESOLUCIÓN DNS ULTRA-RESILIENTE (DOH FALLBACK PARA IGN EN WINDOWS)
# --------------------------------------------------------------------------------------
if os.name == "nt" and not getattr(socket, "_is_resilient_dns_patched", False):
    _orig_getaddrinfo = socket.getaddrinfo
    _dns_cache: Dict[str, str] = {}
    _KNOWN_IGN_IPS = [
        "3.166.160.90",
        "3.166.160.37",
        "3.166.160.84",
        "3.166.160.66",
        "18.173.166.12",
        "18.173.166.45"
    ]

    def _resolve_host_fallback(hostname: str) -> Optional[str]:
        host_lower = str(hostname).lower()
        if not hostname or ("ign.es" not in host_lower and "idee.es" not in host_lower):
            return None
        if hostname in _dns_cache:
            return _dns_cache[hostname]
        
        # 1. Resolver vía Google DoH directamente a la IP 8.8.8.8 (sin requerir DNS local)
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                f"https://8.8.8.8/resolve?name={hostname}&type=A",
                headers={"Host": "dns.google", "User-Agent": "curl/7.68.0"}
            )
            with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
                data = json.loads(r.read().decode())
                for item in data.get("Answer", []):
                    if item.get("type") == 1:
                        ip = item.get("data")
                        _dns_cache[hostname] = ip
                        return ip
        except Exception:
            pass

        # 2. Resolver vía Cloudflare DoH directamente a la IP 1.1.1.1
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            req = urllib.request.Request(
                f"https://1.1.1.1/dns-query?name={hostname}&type=A",
                headers={"Accept": "application/dns-json", "User-Agent": "curl/7.68.0"}
            )
            with urllib.request.urlopen(req, timeout=4, context=ctx) as r:
                data = json.loads(r.read().decode())
                for item in data.get("Answer", []):
                    if item.get("type") == 1:
                        ip = item.get("data")
                        _dns_cache[hostname] = ip
                        return ip
        except Exception:
            pass

        # 3. Fallback estático de IPs CloudFront del IGN
        if "ign.es" in hostname.lower():
            ip = _KNOWN_IGN_IPS[0]
            _dns_cache[hostname] = ip
            return ip

        return None

    def _resilient_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        try:
            return _orig_getaddrinfo(host, port, family, type, proto, flags)
        except socket.gaierror as e:
            fallback_ip = _resolve_host_fallback(str(host))
            if fallback_ip:
                return _orig_getaddrinfo(fallback_ip, port, socket.AF_INET, type, proto, flags)
            raise e

    socket.getaddrinfo = _resilient_getaddrinfo
    socket._is_resilient_dns_patched = True


# --------------------------------------------------------------------------------------
# 1. UTILIDADES Y SANITIZACIÓN DE NOMBRES
# --------------------------------------------------------------------------------------
def sanitize_filename(name: str) -> str:
    """
    Sanitiza nombres de archivo reemplazando caracteres especiales, tildes y espacios
    por guiones bajos, asegurando compatibilidad multiplataforma y con AutoCAD.
    """
    if not name:
        return "ortofoto"
    clean = re.sub(r"[^\w\-]", "_", str(name).strip())
    clean = re.sub(r"_+", "_", clean).strip("_")
    return clean or "ortofoto"


def format_file_size(num_bytes: int) -> str:
    """
    Formatea tamaños de bytes de forma legible y clara (B, KB, MB, GB).
    """
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.2f} MB"


def create_resilient_session(timeout: int = 35) -> requests.Session:
    """
    Crea una sesión HTTP con reintentos exponenciales automáticos para mitigar caídas.
    """
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


# --------------------------------------------------------------------------------------
# 2. LECTURA Y EXTRACCIÓN DE POLÍGONOS CAD (ezdxf & shapely)
# --------------------------------------------------------------------------------------
def load_dxf_document(file_bytes: bytes) -> ezdxf.document.Drawing:
    """
    Carga de forma robusta un archivo DXF desde memoria, normalizando saltos de línea (CRLF)
    y gestionando codificaciones comunes de planos AutoCAD en España (UTF-8, CP1252, Latin-1).
    """
    for encoding in ["utf-8", "cp1252", "latin-1", "iso-8859-1"]:
        try:
            raw_text = file_bytes.decode(encoding, errors="surrogateescape")
            normalized_text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
            doc = ezdxf.read(io.StringIO(normalized_text))
            return doc
        except Exception:
            continue

    try:
        doc, _ = ezdxf.recover.read(io.BytesIO(file_bytes))
        return doc
    except Exception as err:
        raise ValueError(f"No fue posible interpretar el archivo DXF: {err}")


def get_recommended_resolution(area_m2: float) -> Tuple[float, str, str]:
    """
    Calcula la resolución óptima recomendada (m/px) en función del tamaño del área (m²):
      - < 5.000 m² (< 0.5 ha): 0.25 m/px - Muy Alta (Edificación, solares y detalle máximo)
      - 5.000 a 25.000 m² (0.5 a 2.5 ha): 0.50 m/px - Alta (Parcelas residenciales / naves)
      - 25.000 a 150.000 m² (2.5 a 15 ha): 1.00 m/px - Estándar (Urbanizaciones y obras civiles)
      - 150.000 a 1.000.000 m² (15 a 100 ha): 2.00 m/px - Normal (Grandes fincas rústicas)
      - > 1.000.000 m² (> 100 ha): 4.00 m/px - Panorámica (Escala comarcal y territorial)
    """
    if area_m2 < 5000:
        return 0.25, "0.25 m/px (Muy Alta)", "Solares y edificación (< 0.5 ha)"
    elif area_m2 < 25000:
        return 0.50, "0.50 m/px (Alta)", "Parcelas y naves (0.5 a 2.5 ha)"
    elif area_m2 < 150000:
        return 1.00, "1.00 m/px (Estándar)", "Urbanizaciones y obras (2.5 a 15 ha)"
    elif area_m2 < 1000000:
        return 2.00, "2.00 m/px (Normal)", "Grandes fincas e infraestructuras (15 a 100 ha)"
    else:
        return 4.00, "4.00 m/px (Panorámica)", "Escala territorial (> 100 ha)"


def parse_dxf_polygons(file_bytes: bytes, filename: str, service_tag: str = "pnoa") -> List[Dict[str, Any]]:
    """
    Extrae todas las polilíneas cerradas (LWPOLYLINE y POLYLINE con closed=True)
    del espacio modelo del DXF y calcula su Bounding Box, área y vértices.
    """
    doc = load_dxf_document(file_bytes)
    msp = doc.modelspace()
    
    extracted_polygons: List[Dict[str, Any]] = []
    base_file_prefix = os.path.splitext(sanitize_filename(filename))[0]
    polygon_counter = 1

    for entity in msp.query("LWPOLYLINE POLYLINE"):
        try:
            dxftype = entity.dxftype()
            layer = getattr(entity.dxf, "layer", "0")
            pts: List[Tuple[float, float]] = []

            if dxftype == "LWPOLYLINE":
                pts = [(float(p[0]), float(p[1])) for p in entity.get_points("xy")]
            elif dxftype == "POLYLINE":
                pts = [(float(p.x), float(p.y)) for p in entity.points()]

            if len(pts) < 3:
                continue

            is_cad_closed = bool(entity.is_closed)
            is_geom_closed = (abs(pts[0][0] - pts[-1][0]) < 1e-5 and abs(pts[0][1] - pts[-1][1]) < 1e-5)

            if not (is_cad_closed or is_geom_closed):
                continue

            poly = Polygon(pts)
            minx, miny, maxx, maxy = poly.bounds
            width = maxx - minx
            height = maxy - miny

            if width <= 0.001 or height <= 0.001:
                continue

            clean_layer = sanitize_filename(layer)
            clean_tag = sanitize_filename(service_tag)
            output_name = f"{base_file_prefix}_{clean_tag}_{clean_layer}_p{polygon_counter}"

            # Calcular resolución recomendada según el tamaño de la superficie
            rec_res, rec_label, _ = get_recommended_resolution(poly.area)

            extracted_polygons.append({
                "incluir": True,
                "id": polygon_counter,
                "capa": layer,
                "nombre_archivo": output_name,
                "resolucion_m_px": rec_res,
                "calidad_sugerida": rec_label,
                "ancho_m": round(width, 2),
                "alto_m": round(height, 2),
                "area_m2": round(poly.area, 2),
                "num_vertices": len(pts),
                "bounds": (minx, miny, maxx, maxy),
                "pts": pts
            })
            polygon_counter += 1

        except Exception:
            continue

    return extracted_polygons


def extract_kml_bytes_from_kmz(file_bytes: bytes) -> bytes:
    """Extrae el archivo XML .kml principal contenido en un archivo comprimido .kmz."""
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
        kml_files = [n for n in zf.namelist() if n.lower().endswith(".kml")]
        if not kml_files:
            raise ValueError("El archivo KMZ no contiene ningún archivo .kml válido.")
        return zf.read(kml_files[0])


def detect_epsg_from_lonlat(lon: float, lat: float) -> List[Dict[str, Any]]:
    """
    Calcula el sistema de proyección UTM o regional recomendado (EPSG)
    a partir de las coordenadas geográficas reales (Longitud, Latitud WGS 84).
    """
    recommendations: List[Dict[str, Any]] = []
    utm_zone = int(math.floor((lon + 180.0) / 6.0)) + 1
    is_north = (lat >= 0)

    # 1. España Peninsular y Baleares
    if 35.0 <= lat <= 44.5 and -10.0 <= lon <= 5.0:
        zone = 29 if lon <= -6.0 else (30 if lon <= 0.0 else 31)
        recommendations.append({
            "code": 25800 + zone,
            "name": f"ETRS89 / UTM zone {zone}N (EPSG:{25800 + zone})",
            "region": f"🇪🇸 España Peninsular (Huso {zone})",
            "reason": f"Ubicación geográfica detectada en España (Lat: {lat:.4f}°, Lon: {lon:.4f}°).",
            "confidence": "Muy Alta"
        })
    # Islas Canarias
    elif 27.0 <= lat <= 30.0 and -19.0 <= lon <= -13.0:
        recommendations.append({
            "code": 32628,
            "name": "WGS 84 / UTM zone 28N (EPSG:32628)",
            "region": "🇪🇸 Islas Canarias (España)",
            "reason": "Ubicación geográfica en el archipiélago canario.",
            "confidence": "Muy Alta"
        })

    # 2. Colombia
    if -4.5 <= lat <= 13.5 and -80.0 <= lon <= -66.0:
        recommendations.append({
            "code": 9377,
            "name": "MAGNA-SIRGAS / Origen Nacional (EPSG:9377)",
            "region": "🇨🇴 Colombia (Proyección Oficial Nacional)",
            "reason": "Ubicación geográfica dentro del territorio de Colombia.",
            "confidence": "Muy Alta"
        })
        if 4.0 <= lat <= 5.5 and -75.0 <= lon <= -73.5:
            recommendations.append({
                "code": 3116,
                "name": "MAGNA-SIRGAS / Colombia Bogota zone (EPSG:3116)",
                "region": "🇨🇴 Colombia (Bogotá D.C. / Cundinamarca)",
                "reason": "Zona central de Bogotá D.C. y Sabana de Bogotá.",
                "confidence": "Alta"
            })

    # 3. Australia
    if -45.0 <= lat <= -9.0 and 110.0 <= lon <= 155.0:
        if 48 <= utm_zone <= 58:
            recommendations.append({
                "code": 7800 + utm_zone,
                "name": f"GDA2020 / MGA zone {utm_zone} (EPSG:{7800 + utm_zone})",
                "region": f"🇦🇺 Australia (Map Grid of Australia Huso {utm_zone})",
                "reason": f"Ubicación geográfica en Australia (Zona MGA {utm_zone}).",
                "confidence": "Muy Alta"
            })

    # 4. Proyección Universal UTM Mundial
    generic_code = (32600 + utm_zone) if is_north else (32700 + utm_zone)
    hem_str = "Norte" if is_north else "Sur"
    recommendations.append({
        "code": generic_code,
        "name": f"WGS 84 / UTM zone {utm_zone}{'N' if is_north else 'S'} (EPSG:{generic_code})",
        "region": f"🌎 Proyección Universal UTM Huso {utm_zone} {hem_str}",
        "reason": f"Cálculo automático de Huso UTM según longitud ({lon:.4f}°).",
        "confidence": "Alta"
    })
    return recommendations


def parse_kml_or_kmz_polygons(
    file_bytes: bytes,
    filename: str,
    target_crs_str: str,
    service_tag: str = "pnoa"
) -> Tuple[List[Dict[str, Any]], Optional[Tuple[float, float]]]:
    """
    Extrae polígonos de archivos KML o KMZ de Google Earth, reproyectando las coordenadas
    geográficas WGS 84 (EPSG:4326) al sistema de coordenadas CAD activo (target_crs_str).
    Retorna la lista de polígonos y el centroide promedio (lon, lat) para recomendación inteligente de EPSG.
    """
    is_kmz = filename.lower().endswith(".kmz") or file_bytes[:4] == b"PK\x03\x04"
    if is_kmz:
        kml_bytes = extract_kml_bytes_from_kmz(file_bytes)
    else:
        kml_bytes = file_bytes

    try:
        root = ET.fromstring(kml_bytes)
    except Exception as e:
        raise ValueError(f"Error al interpretar el archivo XML del KML: {e}")

    transformer = Transformer.from_crs("EPSG:4326", target_crs_str, always_xy=True)

    extracted_polygons: List[Dict[str, Any]] = []
    base_file_prefix = os.path.splitext(sanitize_filename(filename))[0]
    polygon_counter = 1
    all_lons: List[float] = []
    all_lats: List[float] = []

    for pm in root.iter():
        if pm.tag.endswith("Placemark"):
            pm_name = f"Parcela_{polygon_counter}"
            for child in pm:
                if child.tag.endswith("name") and child.text:
                    pm_name = child.text.strip()
                    break

            # Buscar coordenadas en Polygon, MultiGeometry, LinearRing, LineString
            for el in pm.iter():
                if el.tag.endswith("coordinates") and el.text:
                    raw_text = el.text.strip()
                    lonlats: List[Tuple[float, float]] = []
                    for token in raw_text.split():
                        parts = token.split(",")
                        if len(parts) >= 2:
                            try:
                                lon = float(parts[0])
                                lat = float(parts[1])
                                if -180.0 <= lon <= 180.0 and -90.0 <= lat <= 90.0:
                                    lonlats.append((lon, lat))
                                    all_lons.append(lon)
                                    all_lats.append(lat)
                            except ValueError:
                                pass

                    if len(lonlats) >= 3:
                        # Asegurar cierre de polígono
                        if lonlats[0] != lonlats[-1]:
                            lonlats.append(lonlats[0])

                        cad_pts: List[Tuple[float, float]] = []
                        for lon, lat in lonlats:
                            try:
                                x, y = transformer.transform(lon, lat)
                                cad_pts.append((x, y))
                            except Exception:
                                pass

                        if len(cad_pts) >= 3:
                            poly = Polygon(cad_pts)
                            if poly.area > 0.01:
                                minx, miny, maxx, maxy = poly.bounds
                                width = maxx - minx
                                height = maxy - miny

                                clean_layer = sanitize_filename(pm_name)
                                clean_tag = sanitize_filename(service_tag)
                                output_name = f"{base_file_prefix}_{clean_tag}_{clean_layer}_p{polygon_counter}"
                                rec_res, rec_label, _ = get_recommended_resolution(poly.area)

                                extracted_polygons.append({
                                    "incluir": True,
                                    "id": polygon_counter,
                                    "capa": pm_name,
                                    "nombre_archivo": output_name,
                                    "resolucion_m_px": rec_res,
                                    "calidad_sugerida": rec_label,
                                    "ancho_m": round(width, 2),
                                    "alto_m": round(height, 2),
                                    "area_m2": round(poly.area, 2),
                                    "num_vertices": len(cad_pts),
                                    "bounds": (minx, miny, maxx, maxy),
                                    "pts": cad_pts,
                                    "origen": "kml"
                                })
                                polygon_counter += 1

    centroid = None
    if all_lons and all_lats:
        centroid = (sum(all_lons) / len(all_lons), sum(all_lats) / len(all_lats))

    return extracted_polygons, centroid


def parse_drawn_features(
    drawings: List[Dict[str, Any]],
    target_crs_str: str,
    start_id: int = 1,
    service_tag: str = "wms"
) -> List[Dict[str, Any]]:
    """
    Convierte las geometrías dibujadas por el usuario en el mapa interactivo (GeoJSON WGS 84)
    a polígonos proyectados en el sistema de coordenadas CAD activo (target_crs_str).
    """
    if not drawings:
        return []

    transformer = Transformer.from_crs("EPSG:4326", target_crs_str, always_xy=True)
    extracted: List[Dict[str, Any]] = []

    for i, feature in enumerate(drawings):
        geom = feature.get("geometry", {})
        gtype = geom.get("type", "")
        coords = geom.get("coordinates", [])

        rings = []
        if gtype == "Polygon" and coords:
            rings = coords[0]
        elif gtype == "MultiPolygon" and coords:
            rings = coords[0][0]

        if len(rings) >= 3:
            cad_pts: List[Tuple[float, float]] = []
            for pt in rings:
                try:
                    lon, lat = float(pt[0]), float(pt[1])
                    x, y = transformer.transform(lon, lat)
                    cad_pts.append((x, y))
                except Exception:
                    pass

            if len(cad_pts) >= 3:
                poly = Polygon(cad_pts)
                if poly.area > 0.01:
                    minx, miny, maxx, maxy = poly.bounds
                    w = maxx - minx
                    h = maxy - miny
                    rec_res, rec_label, _ = get_recommended_resolution(poly.area)
                    curr_id = start_id + i

                    extracted.append({
                        "incluir": True,
                        "id": curr_id,
                        "capa": f"DIBUJO_MAPA_{curr_id}",
                        "nombre_archivo": f"dibujo_mapa_{service_tag}_p{curr_id}",
                        "resolucion_m_px": rec_res,
                        "calidad_sugerida": rec_label,
                        "ancho_m": round(w, 2),
                        "alto_m": round(h, 2),
                        "area_m2": round(poly.area, 2),
                        "num_vertices": len(cad_pts),
                        "bounds": (minx, miny, maxx, maxy),
                        "pts": cad_pts,
                        "es_dibujo": True
                    })

    return extracted


def export_polygons_to_dxf(polygons: List[Dict[str, Any]]) -> bytes:
    """
    Genera un archivo DXF AutoCAD R2010 con las polilíneas cerradas (LWPOLYLINE) y sus capas,
    permitiendo al usuario abrir las geometrías dibujadas o de KML directamente en AutoCAD.
    """
    doc = ezdxf.new("R2010")
    msp = doc.modelspace()
    for p in polygons:
        pts = p.get("pts", [])
        if len(pts) >= 3:
            layer_name = sanitize_filename(str(p.get("capa", "0")))[:31]
            try:
                doc.layers.new(name=layer_name)
            except Exception:
                pass
            pl = msp.add_lwpolyline(pts, close=True)
            pl.dxf.layer = layer_name
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode("utf-8")


# --------------------------------------------------------------------------------------
# 2.1 RECOMENDACIÓN INTELIGENTE DE PROYECCIÓN CARTOGRÁFICA (CRS / EPSG)
# --------------------------------------------------------------------------------------
def detect_recommended_epsg(
    bounds: Tuple[float, float, float, float],
    layer_names: Optional[List[str]] = None,
    raw_text: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Analiza las coordenadas espaciales (X, Y), nombres de capas y metadatos del DXF
    para determinar y recomendar los Sistemas de Coordenadas de Referencia (EPSG/CRS)
    más probables a nivel mundial y regional.
    
    Retorna una lista de recomendaciones ordenadas por probabilidad/confianza.
    """
    recommendations: List[Dict[str, Any]] = []
    minx, miny, maxx, maxy = bounds
    cx = (minx + maxx) / 2.0
    cy = (miny + maxy) / 2.0

    search_corpus = ""
    if layer_names:
        search_corpus += " " + " ".join(layer_names)
    if raw_text:
        search_corpus += " " + raw_text[:50000]
    search_corpus_upper = search_corpus.upper()

    # 1. BÚSQUEDA EXPLÍCITA EN METADATOS Y CAPAS (MÁXIMA PRIORIDAD)
    explicit_codes: List[int] = []

    # Patrón EPSG: 4 o 5 dígitos precedidos de EPSG
    for m in re.finditer(r"(?:EPSG|[A-Z]*EPSG)[_\-\s:]*(\d{4,5})", search_corpus_upper):
        code = int(m.group(1))
        if code not in explicit_codes:
            explicit_codes.append(code)

    # Patrón MGA zone (Australia)
    for m in re.finditer(r"\bMGA[_\-\s]*(\d{2})\b", search_corpus_upper):
        zone = int(m.group(1))
        if 48 <= zone <= 58:
            if (7800 + zone) not in explicit_codes:
                explicit_codes.append(7800 + zone) # GDA2020
            if (28300 + zone) not in explicit_codes:
                explicit_codes.append(28300 + zone) # GDA94

    # Patrón UTM zone (ej: UTM 30N, UTM30, UTM 55S)
    for m in re.finditer(r"\bUTM[_\-\s]*(\d{1,2})\s*([NSns]?)\b", search_corpus_upper):
        zone = int(m.group(1))
        hem = m.group(2).upper()
        if 1 <= zone <= 60:
            if hem == "S" or cy > 5000000:
                if 49 <= zone <= 56:
                    if (7800 + zone) not in explicit_codes:
                        explicit_codes.append(7800 + zone)
                else:
                    code_utm_s = 32700 + zone
                    if code_utm_s not in explicit_codes:
                        explicit_codes.append(code_utm_s)
            else:
                if zone in [28, 29, 30, 31]:
                    if zone == 28:
                        if 32628 not in explicit_codes:
                            explicit_codes.append(32628)
                    else:
                        if (25800 + zone) not in explicit_codes:
                            explicit_codes.append(25800 + zone)
                else:
                    code_utm_n = 32600 + zone
                    if code_utm_n not in explicit_codes:
                        explicit_codes.append(code_utm_n)

    # Validar códigos explícitos encontrados con pyproj
    for code in explicit_codes:
        try:
            crs_obj = CRS.from_epsg(code)
            recommendations.append({
                "code": code,
                "name": crs_obj.name,
                "region": crs_obj.area_of_use.name if crs_obj.area_of_use else "Definido en plano CAD",
                "reason": f"Detectado explícitamente en capas o metadatos del archivo DXF.",
                "confidence": "Muy Alta"
            })
        except Exception:
            pass

    if recommendations:
        return recommendations

    # 2. ANÁLISIS GEOMÉTRICO BASADO EN COORDENADAS (X, Y)
    # A. Coordenadas Geográficas (Grados decimales WGS84)
    if -180.0 <= minx <= 180.0 and -180.0 <= maxx <= 180.0 and -90.0 <= miny <= 90.0 and -90.0 <= maxy <= 90.0:
        recommendations.append({
            "code": 4326,
            "name": "WGS 84 (Coordenadas Geográficas en Grados)",
            "region": "🌎 Cobertura Global",
            "reason": f"Las coordenadas (X={cx:.4f}°, Y={cy:.4f}°) se encuentran dentro del rango angular mundial (-180° a 180°, -90° a 90°).",
            "confidence": "Muy Alta"
        })
        return recommendations

    # B. Colombia - Origen Nacional Único (MAGNA-SIRGAS EPSG:9377)
    if 4000000 <= cx <= 6000000 and 1000000 <= cy <= 3500000:
        recommendations.append({
            "code": 9377,
            "name": "MAGNA-SIRGAS / Origen Nacional (EPSG:9377)",
            "region": "🇨🇴 Colombia (Sistema Oficial Único)",
            "reason": f"Coordenadas proyectadas características de Colombia con Falso Este ~5.000.000 m y Falso Norte ~2.000.000 m.",
            "confidence": "Muy Alta"
        })
        return recommendations

    # B2. Colombia - Bogotá D.C. / MAGNA-SIRGAS Bogotá (EPSG:3116)
    if 700000 <= cx <= 1300000 and 700000 <= cy <= 1300000:
        recommendations.append({
            "code": 3116,
            "name": "MAGNA-SIRGAS / Colombia Bogota zone (EPSG:3116)",
            "region": "🇨🇴 Colombia - Bogotá D.C. y Cundinamarca",
            "reason": f"Coordenadas características de Bogotá (X={cx:,.0f} m, Y={cy:,.0f} m) con origen Falso Este 1.000.000 m y Falso Norte 1.000.000 m.",
            "confidence": "Muy Alta"
        })
        return recommendations

    # C. Hemisferio Sur - Australia (UTM False Northing = 10.000.000 m)
    # Latitudes de Australia (-44° a -10° S) -> Y entre 5.100.000 m y 8.900.000 m; X entre 150.000 m y 850.000 m.
    if 5000000 <= cy <= 9000000 and 150000 <= cx <= 850000:
        text_lower = search_corpus.lower()
        pref_zone = None
        if any(w in text_lower for w in ["sydney", "nsw", "brisbane", "gold coast", "qld", "queensland"]):
            pref_zone = 56
        elif any(w in text_lower for w in ["melbourne", "victoria", "vic", "tasmania", "hobart", "act", "canberra"]):
            pref_zone = 55
        elif any(w in text_lower for w in ["adelaide", "south australia", "sa"]):
            pref_zone = 54
        elif any(w in text_lower for w in ["perth", "western australia", "wa"]):
            pref_zone = 50

        aus_zones = [55, 56, 54, 50, 51, 52, 53, 49]
        if pref_zone and pref_zone in aus_zones:
            aus_zones.remove(pref_zone)
            aus_zones.insert(0, pref_zone)

        zone_names = {
            55: "Victoria, Melbourne, NSW, QLD",
            56: "Sydney, Brisbane, Gold Coast, NSW Este",
            54: "South Australia, Adelaide",
            50: "Western Australia, Perth",
            51: "Western Australia interior",
            52: "NT / SA Central",
            53: "Northern Territory, Darwin, Alice Springs",
            49: "Western Australia Oeste"
        }

        for idx, z in enumerate(aus_zones[:4]):
            gda2020_code = 7800 + z
            recommendations.append({
                "code": gda2020_code,
                "name": f"GDA2020 / MGA zone {z} (EPSG:{gda2020_code})",
                "region": f"🇦🇺 Australia ({zone_names.get(z, f'Zone {z}')})",
                "reason": f"Coordenadas UTM del Hemisferio Sur (Y={cy:,.0f} m, X={cx:,.0f} m) típicas de Australia.",
                "confidence": "Alta" if idx == 0 else "Media",
                "alt_code": 28300 + z,
                "alt_name": f"GDA94 / MGA zone {z} (EPSG:{28300 + z})"
            })
        return recommendations

    # D. España Peninsular y Europa (UTM Husos 29, 30, 31)
    # Latitudes 35.8° a 44° N -> Y entre 3.850.000 m y 4.900.000 m; X entre 150.000 m y 850.000 m.
    if 3850000 <= cy <= 4900000 and 150000 <= cx <= 850000:
        text_lower = search_corpus.lower()
        pref_spain_zone = 30
        if any(w in text_lower for w in ["galicia", "coruña", "pontevedra", "ourense", "lugo", "huelva", "vigo", "asturias"]):
            pref_spain_zone = 29
        elif any(w in text_lower for w in ["catalunya", "cataluña", "barcelona", "girona", "tarragona", "lleida", "baleares", "mallorca", "menorca", "ibiza"]):
            pref_spain_zone = 31

        spain_zones = [30, 29, 31]
        if pref_spain_zone != 30:
            spain_zones.remove(pref_spain_zone)
            spain_zones.insert(0, pref_spain_zone)

        spain_info = {
            30: ("ETRS89 / UTM zone 30N (EPSG:25830)", "🇪🇸 España Peninsular (Centro, Madrid, Andalucía, Valencia, Norte)", "Muy Alta" if pref_spain_zone == 30 else "Alta"),
            29: ("ETRS89 / UTM zone 29N (EPSG:25829)", "🇪🇸 España (Galicia, Huelva y Asturias Occidental)", "Alta" if pref_spain_zone == 29 else "Media"),
            31: ("ETRS89 / UTM zone 31N (EPSG:25831)", "🇪🇸 España (Cataluña, Baleares y Franja Oriental)", "Alta" if pref_spain_zone == 31 else "Media")
        }

        for z in spain_zones:
            epsg_sp = 25800 + z
            name, reg, conf = spain_info[z]
            recommendations.append({
                "code": epsg_sp,
                "name": name,
                "region": reg,
                "reason": f"Coordenadas UTM características de España y Europa (Y={cy:,.0f} m, X={cx:,.0f} m).",
                "confidence": conf
            })
        return recommendations

    # E. Islas Canarias (UTM Huso 28N)
    # Latitudes 27.5° a 29.5° N -> Y entre 3.000.000 m y 3.350.000 m; X entre 150.000 m y 750.000 m.
    if 3000000 <= cy <= 3350000 and 150000 <= cx <= 750000:
        recommendations.append({
            "code": 32628,
            "name": "WGS 84 / UTM zone 28N (EPSG:32628)",
            "region": "🇪🇸 Islas Canarias (España) / África Noroeste",
            "reason": f"Coordenadas UTM del archipiélago canario (Y={cy:,.0f} m, X={cx:,.0f} m).",
            "confidence": "Muy Alta"
        })
        recommendations.append({
            "code": 4083,
            "name": "REGCAN95 / UTM zone 28N (EPSG:4083)",
            "region": "🇪🇸 Islas Canarias (Red Geodésica Oficial REGCAN95)",
            "reason": "Referencia geodésica oficial de las Islas Canarias.",
            "confidence": "Alta"
        })
        return recommendations

    # F. México (UTM Husos 11N a 16N)
    if 1550000 <= cy <= 3600000 and 150000 <= cx <= 850000:
        recommendations.append({
            "code": 6369,
            "name": "ITRF2008 / UTM zone 14N (EPSG:6369)",
            "region": "🇲🇽 México (Zona Central / CDMX / Puebla / Veracruz)",
            "reason": f"Rango de coordenadas UTM común en México y Centroamérica (Y={cy:,.0f} m).",
            "confidence": "Media"
        })
        recommendations.append({
            "code": 6367,
            "name": "ITRF2008 / UTM zone 12N (EPSG:6367)",
            "region": "🇲🇽 México (Noroeste / Sonora / Sinaloa)",
            "reason": "Zona 12N para estados del noroeste de México.",
            "confidence": "Media"
        })
        return recommendations

    # G. Web Mercator Pseudo-Mercator (EPSG:3857)
    if abs(cx) > 1000000 or abs(cy) > 1000000:
        recommendations.append({
            "code": 3857,
            "name": "WGS 84 / Pseudo-Mercator (EPSG:3857)",
            "region": "🌎 Cobertura Global (Mapas Web)",
            "reason": "Valores métricos extensos compatibles con la proyección Web Mercator estándar.",
            "confidence": "Baja"
        })

    return recommendations


# --------------------------------------------------------------------------------------
# 3. CATÁLOGO DE SERVICIOS CARTOGRÁFICOS Y SATELITALES (MUNDIAL Y NACIONAL)
# --------------------------------------------------------------------------------------
SERVICES_CATALOG: Dict[str, Dict[str, Any]] = {
    "google_sat": {
        "name": "🌍 Google Satélite (Mundial - Máxima Resolución)",
        "type": "xyz",
        "url": "https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        "layer": "",
        "tag": "google_sat",
        "badge": "Google Satélite",
        "description": "Fotografía satelital mundial de Google de alta resolución sin rótulos. Cobertura global (Australia, América, Europa, Asia y resto del mundo).",
        "folium_name": "🌍 Google Satélite (Google Maps)",
    },
    "google_hybrid": {
        "name": "🌍 Google Híbrido (Mundial - Satélite + Vías y Nombres)",
        "type": "xyz",
        "url": "https://{s}.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        "layer": "",
        "tag": "google_hybrid",
        "badge": "Google Híbrido",
        "description": "Satélite de Google con red de carreteras, calles principales y toponimia sobreimpresas.",
        "folium_name": "🌍 Google Híbrido (Satélite + Vías)",
    },
    "esri_sat": {
        "name": "🛰️ Esri World Imagery (Mundial - Alta Resolución)",
        "type": "xyz",
        "url": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "layer": "",
        "tag": "esri_sat",
        "badge": "Esri Satélite",
        "description": "Ortofotografía satelital global de Esri / Maxar de alta resolución.",
        "folium_name": "🛰️ Esri World Imagery",
    },
    "custom": {
        "name": "⚙️ Servidor WMS Universal (Cualquier país / organismo del mundo)",
        "type": "wms",
        "url": "",
        "layer": "",
        "tag": "wms_custom",
        "badge": "WMS Universal",
        "description": "Introduce la URL y capa de cualquier servidor WMS del mundo (gobiernos estatales, catastro, Australia, etc.).",
        "folium_name": "⚙️ WMS Universal",
    },
    "pnoa": {
        "name": "🇪🇸 IGN - Ortofoto Aérea PNOA (España - Máxima Resolución)",
        "type": "wms",
        "url": "https://www.ign.es/wms-inspire/pnoa-ma",
        "layer": "OI.OrthoimageCoverage",
        "tag": "pnoa",
        "badge": "Ortofoto PNOA",
        "description": "Ortofotografías aéreas oficiales de España de máxima resolución del PNOA. Ideal para urbanismo y edificación.",
        "folium_name": "🇪🇸 Ortofoto PNOA WMS (IGN)",
    },
    "mapa_raster": {
        "name": "🗺️ IGN - Mapa Ráster / MTN Topográfico (España)",
        "type": "wms",
        "url": "https://www.ign.es/wms-inspire/mapa-raster",
        "layer": "mtn_rasterizado",
        "tag": "mtn_raster",
        "badge": "Mapa Ráster MTN",
        "description": "Cartografía topográfica oficial con curvas de nivel, toponimia y altitudes.",
        "folium_name": "🗺️ IGN Mapa Ráster MTN Topográfico",
    },
    "mdt_relieve": {
        "name": "🏔️ IGN - Modelo Digital del Terreno Relieve (España)",
        "type": "wms",
        "url": "https://servicios.idee.es/wms-inspire/mdt",
        "layer": "EL.GridCoverage",
        "tag": "mdt_relieve",
        "badge": "Relieve MDT",
        "description": "Sombreado continuo del terreno derivado de LiDAR y MDT para estudios de pendiente.",
        "folium_name": "🏔️ IGN Relieve Sombreado MDT",
    }
}


def compute_georeferencing_parameters(
    bounds: Tuple[float, float, float, float],
    buffer_pct: float,
    pixel_size: float,
    max_pixels_lado: int = 4000,
    max_pixels_totales: int = 16000000
) -> Dict[str, Any]:
    """
    Calcula el Bounding Box expandido por el buffer porcentual, pre-valida y escala
    las dimensiones en píxeles garantizando que NUNCA superen el límite de 4096 px
    impuesto por el servidor MapServer del IGN PNOA.
    """
    minx, miny, maxx, maxy = bounds

    # 1 & 2: Buffer porcentual
    dx = (maxx - minx) * buffer_pct
    dy = (maxy - miny) * buffer_pct
    bbox_buf = (minx - dx, miny - dy, maxx + dx, maxy + dy)
    width_m = bbox_buf[2] - bbox_buf[0]
    height_m = bbox_buf[3] - bbox_buf[1]

    # Forzar límite estricto del servidor WMS del IGN (máx. 4096 px)
    # Capped en 4000 px para evitar fallos por redondeo
    server_max_side = min(int(max_pixels_lado), 4000)
    server_max_total = min(int(max_pixels_totales), 16000000)

    ancho_px_ideal = width_m / pixel_size
    alto_px_ideal = height_m / pixel_size

    factor = min(
        server_max_side / ancho_px_ideal,
        server_max_side / alto_px_ideal,
        (server_max_total / (ancho_px_ideal * alto_px_ideal)) ** 0.5,
        1.0
    )

    ancho_px = min(server_max_side, max(1, round(ancho_px_ideal * factor)))
    alto_px = min(server_max_side, max(1, round(alto_px_ideal * factor)))

    pixel_x = width_m / ancho_px
    pixel_y = - (height_m / alto_px)
    x_center_ul = bbox_buf[0] + (pixel_x / 2.0)
    y_center_ul = bbox_buf[3] + (pixel_y / 2.0)

    tfw_content = (
        f"{pixel_x:.10f}\n"
        f"0.0000000000\n"
        f"0.0000000000\n"
        f"{pixel_y:.10f}\n"
        f"{x_center_ul:.10f}\n"
        f"{y_center_ul:.10f}\n"
    )

    return {
        "bbox_buf": bbox_buf,
        "width_m": width_m,
        "height_m": height_m,
        "ancho_px": ancho_px,
        "alto_px": alto_px,
        "pixel_x": pixel_x,
        "pixel_y": pixel_y,
        "tfw_content": tfw_content,
        "scaled": factor < 0.999,
        "factor": factor,
        "ancho_px_ideal": ancho_px_ideal,
        "alto_px_ideal": alto_px_ideal,
        "tile_suffix": ""
    }


def compute_tiled_georeferencing(
    bounds: Tuple[float, float, float, float],
    buffer_pct: float,
    pixel_size: float,
    max_tile_side: int = 4000
) -> List[Dict[str, Any]]:
    """
    Subdivide un Bounding Box extenso en una cuadrícula continua de teselas contiguas
    de máximo 4000 px cada una, preservando exactamente la resolución de píxel solicitada.
    """
    minx, miny, maxx, maxy = bounds
    dx = (maxx - minx) * buffer_pct
    dy = (maxy - miny) * buffer_pct
    bbox_buf = (minx - dx, miny - dy, maxx + dx, maxy + dy)
    width_m = bbox_buf[2] - bbox_buf[0]
    height_m = bbox_buf[3] - bbox_buf[1]

    ancho_px_ideal = width_m / pixel_size
    alto_px_ideal = height_m / pixel_size

    # Si cabe en una sola imagen de <= 4000 px, retornar una sola
    if ancho_px_ideal <= max_tile_side and alto_px_ideal <= max_tile_side:
        res = compute_georeferencing_parameters(bounds, buffer_pct, pixel_size, max_tile_side)
        res["tile_suffix"] = ""
        return [res]

    nx = max(1, math.ceil(ancho_px_ideal / max_tile_side))
    ny = max(1, math.ceil(alto_px_ideal / max_tile_side))

    tiles = []
    tile_w_m = width_m / nx
    tile_h_m = height_m / ny

    for r in range(ny):
        for c in range(nx):
            sub_minx = bbox_buf[0] + c * tile_w_m
            sub_maxx = sub_minx + tile_w_m
            sub_maxy = bbox_buf[3] - r * tile_h_m
            sub_miny = sub_maxy - tile_h_m

            w_px = min(max_tile_side, max(1, round(tile_w_m / pixel_size)))
            h_px = min(max_tile_side, max(1, round(tile_h_m / pixel_size)))

            pix_x = tile_w_m / w_px
            pix_y = - (tile_h_m / h_px)
            x_c = sub_minx + (pix_x / 2.0)
            y_c = sub_maxy + (pix_y / 2.0)

            tfw = (
                f"{pix_x:.10f}\n"
                f"0.0000000000\n"
                f"0.0000000000\n"
                f"{pix_y:.10f}\n"
                f"{x_c:.10f}\n"
                f"{y_c:.10f}\n"
            )

            tiles.append({
                "bbox_buf": (sub_minx, sub_miny, sub_maxx, sub_maxy),
                "width_m": tile_w_m,
                "height_m": tile_h_m,
                "ancho_px": w_px,
                "alto_px": h_px,
                "pixel_x": pix_x,
                "pixel_y": pix_y,
                "tfw_content": tfw,
                "scaled": False,
                "tile_suffix": f"_t{r+1}_{c+1}" if (nx > 1 or ny > 1) else ""
            })

    return tiles


@st.cache_data(ttl=600, show_spinner=False)
def fetch_wms_service_layers(clean_url: str) -> List[Tuple[str, str]]:
    """
    Consulta el GetCapabilities del servidor WMS para extraer automáticamente
    las capas disponibles con su código técnico y título legible.
    """
    clean_url = clean_url.split("?")[0].strip()
    if not clean_url or not clean_url.startswith("http"):
        return []
    try:
        session = create_resilient_session(timeout=8)
        resp = session.get(clean_url, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"}, timeout=8)
        if resp.status_code != 200:
            return []
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        layers = []
        for el in root.iter():
            if el.tag.endswith("Layer"):
                name_el = el.find("{*}Name")
                title_el = el.find("{*}Title")
                if name_el is not None and name_el.text:
                    n = name_el.text.strip()
                    t = title_el.text.strip() if title_el is not None and title_el.text else n
                    if not n.startswith("<![CDATA") and n.upper() != "WMS":
                        if not any(x[0] == n for x in layers):
                            layers.append((n, t))
        return layers
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def fetch_wms_server_limits(clean_url: str) -> Tuple[Optional[int], Optional[int]]:
    """
    Inspecciona el documento GetCapabilities del servidor WMS para extraer límites
    nativos de dimensiones (MaxWidth y MaxHeight), previniendo errores HTTP 400 por exceso de píxeles.
    """
    clean_url = clean_url.split("?")[0].strip()
    if not clean_url or not clean_url.startswith("http"):
        return None, None
    try:
        session = create_resilient_session(timeout=8)
        resp = session.get(clean_url, params={"SERVICE": "WMS", "REQUEST": "GetCapabilities"}, timeout=8)
        if resp.status_code != 200:
            return None, None
        import xml.etree.ElementTree as ET
        root = ET.fromstring(resp.content)
        max_w, max_h = None, None
        for el in root.iter():
            tag = el.tag.lower()
            if tag.endswith("maxwidth") and el.text and el.text.strip().isdigit():
                max_w = int(el.text.strip())
            elif tag.endswith("maxheight") and el.text and el.text.strip().isdigit():
                max_h = int(el.text.strip())
        return max_w, max_h
    except Exception:
        return None, None


def get_compatible_crs_codes(crs_str: str) -> List[str]:
    """
    Retorna una lista priorizada de códigos CRS matemáticamente equivalentes o compatibles
    (con diferencia milimétrica en la cuadrícula de proyección UTM), asegurando interoperabilidad
    con servidores WMS internacionales (Australia Geoscience DEA, España IGN, Colombia IGAC, EE.UU. USGS).
    """
    candidates = [crs_str]
    m = re.search(r"(\d+)", crs_str)
    if not m:
        return candidates
    code = int(m.group(1))

    # Australia: MGA 2020 (7848-7858), MGA 94 (28348-28358), WGS 84 UTM Sur (32748-32758)
    if 7848 <= code <= 7858:
        z = code - 7800
        candidates.extend([f"EPSG:{32700 + z}", f"EPSG:{28300 + z}"])
    elif 28348 <= code <= 28358:
        z = code - 28300
        candidates.extend([f"EPSG:{32700 + z}", f"EPSG:{7800 + z}"])
    elif 32748 <= code <= 32758:
        z = code - 32700
        candidates.extend([f"EPSG:{7800 + z}", f"EPSG:{28300 + z}"])

    # España / Europa: ETRS89 UTM Norte (25828-25832), WGS 84 UTM Norte (32628-32632), ED50 (23028-23032)
    elif 25828 <= code <= 25832:
        z = code - 25800
        candidates.extend([f"EPSG:{32600 + z}", f"EPSG:{23000 + z}"])
    elif 23028 <= code <= 23032:
        z = code - 23000
        candidates.extend([f"EPSG:{25800 + z}", f"EPSG:{32600 + z}"])
    elif 32628 <= code <= 32632:
        z = code - 32600
        candidates.extend([f"EPSG:{25800 + z}", f"EPSG:{23000 + z}"])

    # Genérico UTM Norte / Sur
    elif 32601 <= code <= 32660:
        z = code - 32600
        if 28 <= z <= 32:
            candidates.append(f"EPSG:{25800 + z}")
    elif 32701 <= code <= 32760:
        z = code - 32700
        if 48 <= z <= 58:
            candidates.extend([f"EPSG:{7800 + z}", f"EPSG:{28300 + z}"])

    seen = set()
    res = []
    for c in candidates:
        if c not in seen:
            seen.add(c)
            res.append(c)
    return res


def fetch_single_wms_call(
    session: requests.Session,
    clean_url: str,
    wms_layer: str,
    crs_to_use: str,
    bbox_tuple: Tuple[float, float, float, float],
    w: int,
    h: int,
    timeout: int = 30
) -> Tuple[bool, str, Optional[bytes], Optional[Image.Image]]:
    """
    Intenta descargar una tesela o imagen WMS individual probando versiones OGC (1.3.0 y 1.1.1)
    y formatos (TIFF, PNG, JPEG), parseando de forma robusta cualquier excepción XML del servidor.
    """
    minx, miny, maxx, maxy = bbox_tuple
    bbox_xy = f"{minx},{miny},{maxx},{maxy}"
    bbox_yx = f"{miny},{minx},{maxy},{maxx}"
    is_yx = False
    try:
        crs_obj = CRS.from_user_input(crs_to_use)
        if crs_obj.axis_info and len(crs_obj.axis_info) >= 2:
            first_dir = str(crs_obj.axis_info[0].direction).lower()
            if "north" in first_dir or "lat" in first_dir:
                is_yx = True
    except Exception:
        pass

    primary_130_bbox = bbox_yx if is_yx else bbox_xy
    fallback_130_bbox = bbox_xy if is_yx else bbox_yx
    bbox_111 = bbox_xy

    attempts = [
        ("1.3.0", "image/tiff", "CRS", primary_130_bbox),
        ("1.3.0", "image/png", "CRS", primary_130_bbox),
        ("1.1.1", "image/tiff", "SRS", bbox_111),
        ("1.1.1", "image/png", "SRS", bbox_111),
        ("1.3.0", "image/tiff", "CRS", fallback_130_bbox),
        ("1.3.0", "image/png", "CRS", fallback_130_bbox),
        ("1.3.0", "image/jpeg", "CRS", primary_130_bbox),
        ("1.1.1", "image/jpeg", "SRS", bbox_111)
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "image/tiff,image/png,image/jpeg,image/*,*/*;q=0.8"
    }
    last_err = ""
    for ver, fmt, crs_param, req_bbox in attempts:
        params = {
            "SERVICE": "WMS",
            "VERSION": ver,
            "REQUEST": "GetMap",
            "LAYERS": wms_layer,
            "STYLES": "",
            "FORMAT": fmt,
            crs_param: crs_to_use,
            "BBOX": req_bbox,
            "WIDTH": w,
            "HEIGHT": h,
            "TRANSPARENT": "TRUE"
        }
        try:
            resp = session.get(clean_url, params=params, headers=headers, timeout=timeout)
            content_type = resp.headers.get("Content-Type", "").lower()
            start_bytes = resp.content[:600]

            if (
                "xml" in content_type
                or start_bytes.startswith(b"<?xml")
                or b"<ServiceException" in start_bytes
                or b"<ExceptionReport" in start_bytes
            ):
                text = resp.text
                m = re.search(r"<ServiceException[^>]*>(.*?)</ServiceException>", text, re.DOTALL)
                if m:
                    last_err = m.group(1).strip()
                else:
                    m2 = re.search(r"<ExceptionText[^>]*>(.*?)</ExceptionText>", text, re.DOTALL)
                    if m2:
                        last_err = m2.group(1).strip()
                    else:
                        last_err = text[:250].replace("\n", " ").strip()

                # Si el error es por CRS inválido o dimensiones excedidas, detener reintentos de formato
                if any(k in last_err.lower() for k in ["invalidcrs", "exceeds supported maximum", "greater than maximum supported"]):
                    return False, last_err, None, None
                continue

            if resp.status_code != 200:
                last_err = f"Código HTTP {resp.status_code}"
                continue

            is_image = (
                "image" in content_type
                or start_bytes.startswith(b"\x89PNG")
                or start_bytes.startswith(b"II*\x00")
                or start_bytes.startswith(b"MM\x00*")
                or start_bytes.startswith(b"\xff\xd8")
            )
            if is_image:
                try:
                    img = Image.open(io.BytesIO(resp.content))
                    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                        extrema = img.getextrema()
                        alpha_ext = extrema[3] if img.mode == "RGBA" else (extrema[1] if img.mode == "LA" else None)
                        if alpha_ext and alpha_ext[1] == 0:
                            last_err = "El servidor devolvió un mosaico vacío (100% transparente) sin datos en estas coordenadas."
                            continue
                    return True, "", resp.content, img
                except Exception as e:
                    last_err = f"Error decodificando imagen: {e}"
                    continue
        except Exception as req_err:
            last_err = str(req_err)
            continue
    return False, last_err, None, None


def fetch_wms_tiled_subblocks(
    session: requests.Session,
    clean_url: str,
    wms_layer: str,
    crs_to_use: str,
    bbox_tuple: Tuple[float, float, float, float],
    total_w: int,
    total_h: int,
    max_tile_side: int = 512,
    timeout: int = 30
) -> Tuple[bool, str, Optional[Image.Image]]:
    """
    Subdivide una petición WMS en una cuadrícula de subtelas concurrentes cuando el servidor
    impone límites de tamaño máximo (ej. 512x512 en Geoscience Australia) y las ensambla en una sola imagen.
    """
    minx, miny, maxx, maxy = bbox_tuple
    n_cols = max(1, int(math.ceil(total_w / max_tile_side)))
    n_rows = max(1, int(math.ceil(total_h / max_tile_side)))

    col_widths = []
    w_rem = total_w
    for c in range(n_cols):
        cw = w_rem // (n_cols - c)
        col_widths.append(cw)
        w_rem -= cw

    row_heights = []
    h_rem = total_h
    for r in range(n_rows):
        rh = h_rem // (n_rows - r)
        row_heights.append(rh)
        h_rem -= rh

    x_res = (maxx - minx) / total_w
    y_res = (maxy - miny) / total_h

    tiles_tasks = []
    curr_y_px = 0
    curr_y_coord = maxy
    for r, rh in enumerate(row_heights):
        next_y_coord = curr_y_coord - (rh * y_res)
        curr_x_px = 0
        curr_x_coord = minx
        for c, cw in enumerate(col_widths):
            next_x_coord = curr_x_coord + (cw * x_res)
            tile_bbox = (curr_x_coord, next_y_coord, next_x_coord, curr_y_coord)
            tiles_tasks.append((c, r, curr_x_px, curr_y_px, cw, rh, tile_bbox))
            curr_x_coord = next_x_coord
            curr_x_px += cw
        curr_y_coord = next_y_coord
        curr_y_px += rh

    canvas = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    tile_error = None

    def fetch_subtile(task):
        c, r, x_px, y_px, cw, rh, sub_bbox = task
        ok, err_msg, raw_bytes, img_obj = fetch_single_wms_call(
            session, clean_url, wms_layer, crs_to_use, sub_bbox, cw, rh, timeout=timeout
        )
        if ok and img_obj:
            return x_px, y_px, img_obj
        raise RuntimeError(err_msg or f"Fallo en subtela ({c},{r})")

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(8, len(tiles_tasks))) as executor:
        future_map = {executor.submit(fetch_subtile, t): t for t in tiles_tasks}
        for fut in concurrent.futures.as_completed(future_map):
            try:
                x_px, y_px, img_obj = fut.result()
                canvas.paste(img_obj.convert("RGB"), (x_px, y_px))
            except Exception as e:
                tile_error = str(e)

    if tile_error:
        return False, tile_error, None
    return True, "", canvas


def fetch_wms_rectified_3857(
    session: requests.Session,
    clean_url: str,
    wms_layer: str,
    crs_str: str,
    bbox_tuple: Tuple[float, float, float, float],
    total_w: int,
    total_h: int,
    max_tile_side: int = 512,
    timeout: int = 30
) -> bytes:
    """
    Fallback universal: Si el servidor WMS rechaza todas las proyecciones UTM locales pero soporta
    Web Mercator (EPSG:3857), descarga la imagen en EPSG:3857 y la rectifica subpíxel al encuadre CAD.
    """
    minx, miny, maxx, maxy = bbox_tuple
    corners = [(minx, maxy), (minx, miny), (maxx, miny), (maxx, maxy)]
    t_3857 = Transformer.from_crs(crs_str, "EPSG:3857", always_xy=True)
    c_3857 = [t_3857.transform(x, y) for x, y in corners]
    b_minx = min(c[0] for c in c_3857)
    b_maxx = max(c[0] for c in c_3857)
    b_miny = min(c[1] for c in c_3857)
    b_maxy = max(c[1] for c in c_3857)

    n_cols = max(1, int(math.ceil(total_w / max_tile_side)))
    n_rows = max(1, int(math.ceil(total_h / max_tile_side)))
    col_w = [total_w // n_cols] * n_cols
    col_w[-1] += total_w - sum(col_w)
    row_h = [total_h // n_rows] * n_rows
    row_h[-1] += total_h - sum(row_h)

    x_res = (b_maxx - b_minx) / total_w
    y_res = (b_maxy - b_miny) / total_h

    canvas_3857 = Image.new("RGB", (total_w, total_h), (255, 255, 255))
    curr_y = b_maxy
    curr_y_px = 0
    for r, rh in enumerate(row_h):
        next_y = curr_y - (rh * y_res)
        curr_x = b_minx
        curr_x_px = 0
        for c, cw in enumerate(col_w):
            next_x = curr_x + (cw * x_res)
            params = {
                "SERVICE": "WMS",
                "VERSION": "1.3.0",
                "REQUEST": "GetMap",
                "LAYERS": wms_layer,
                "STYLES": "",
                "FORMAT": "image/png",
                "CRS": "EPSG:3857",
                "BBOX": f"{curr_x},{next_y},{next_x},{curr_y}",
                "WIDTH": cw,
                "HEIGHT": rh,
                "TRANSPARENT": "TRUE"
            }
            resp = session.get(clean_url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
            if resp.status_code == 200 and not b"<ServiceException" in resp.content[:300]:
                tile_img = Image.open(io.BytesIO(resp.content)).convert("RGB")
                canvas_3857.paste(tile_img, (curr_x_px, curr_y_px))
            curr_x = next_x
            curr_x_px += cw
        curr_y = next_y
        curr_y_px += rh

    quad_data = []
    for cx, cy in c_3857:
        px = (cx - b_minx) / (b_maxx - b_minx) * total_w
        py = (b_maxy - cy) / (b_maxy - b_miny) * total_h
        quad_data.extend([px, py])

    rectified = canvas_3857.transform((total_w, total_h), Image.QUAD, tuple(quad_data), resample=Image.BICUBIC)
    out = io.BytesIO()
    rectified.save(out, format="TIFF")
    return out.getvalue()


def fetch_wms_ortho(
    session: requests.Session,
    wms_url: str,
    wms_layer: str,
    crs_str: str,
    bbox_buf: Tuple[float, float, float, float],
    ancho_px: int,
    alto_px: int,
    timeout: int = 35
) -> bytes:
    """
    Ejecuta la descarga GetMap bajo los estándares OGC WMS (1.3.0 y 1.1.1) con resolución
    automática de proyecciones equivalentes (UTM/MGA), particionado adaptativo de teselas
    según límites del servidor (MaxWidth/MaxHeight) y fallback universal en EPSG:3857.
    """
    clean_url = wms_url.split("?")[0].strip()
    if not clean_url:
        raise ValueError("La URL del servidor WMS está vacía. Por favor introduce una URL válida en la barra lateral.")

    host = urlparse(clean_url).netloc or "WMS"
    ancho_px = min(4000, max(1, int(ancho_px)))
    alto_px = min(4000, max(1, int(alto_px)))

    # 1. Obtener límites de dimensiones nativas del servidor WMS
    srv_w, srv_h = fetch_wms_server_limits(clean_url)
    max_tile = min(srv_w or 4000, srv_h or 4000, 4000)

    # 2. Generar lista priorizada de códigos CRS compatibles
    candidate_crss = get_compatible_crs_codes(crs_str)
    last_error = ""

    # 3. Intentar con cada CRS candidato
    for cand_crs in candidate_crss:
        # Petición directa si entra en los límites del servidor
        if ancho_px <= max_tile and alto_px <= max_tile:
            ok, err_msg, raw_bytes, img_obj = fetch_single_wms_call(
                session, clean_url, wms_layer, cand_crs, bbox_buf, ancho_px, alto_px, timeout=timeout
            )
            if ok:
                if raw_bytes and (raw_bytes.startswith(b"II*\x00") or raw_bytes.startswith(b"MM\x00*")):
                    return raw_bytes
                out_tif = io.BytesIO()
                img_obj.save(out_tif, format="TIFF")
                return out_tif.getvalue()

            last_error = err_msg
            if "invalidcrs" in err_msg.lower():
                continue

            # Comprobar si el servidor impone un límite de dimensiones no declarado en GetCapabilities
            m_lim = re.search(r"(?:exceeds supported maximum|greater than maximum supported|maximum allowed width|maxwidth)\s*(\d+)", err_msg, re.I)
            if m_lim:
                max_tile = min(max_tile, int(m_lim.group(1)))

        # Subparticionado en cuadrícula concurrente si excede el límite del servidor
        if ancho_px > max_tile or alto_px > max_tile:
            ok_t, err_t, canvas = fetch_wms_tiled_subblocks(
                session, clean_url, wms_layer, cand_crs, bbox_buf, ancho_px, alto_px, max_tile_side=max_tile, timeout=timeout
            )
            if ok_t and canvas:
                out_tif = io.BytesIO()
                canvas.save(out_tif, format="TIFF")
                return out_tif.getvalue()

            last_error = err_t
            if "invalidcrs" in err_t.lower():
                continue

    # 4. Fallback universal en EPSG:3857 con rectificación si las proyecciones UTM fueron rechazadas
    if "invalidcrs" in last_error.lower():
        try:
            return fetch_wms_rectified_3857(
                session, clean_url, wms_layer, crs_str, bbox_buf, ancho_px, alto_px, max_tile_side=max_tile, timeout=timeout
            )
        except Exception as e_3857:
            last_error = f"Fallo en rectificación EPSG:3857: {e_3857}"

    # 5. Diagnóstico guiado si la capa no existe en el servidor
    if "LayerNotDefined" in last_error or "unacceptable layer names" in last_error.lower():
        available = fetch_wms_service_layers(clean_url)
        if available:
            layer_sample = ", ".join([f"'{n}' ({t})" if n != t else f"'{n}'" for n, t in available[:8]])
            if len(available) > 8:
                layer_sample += f", ... (+{len(available)-8} más)"
            raise ValueError(
                f"Servidor WMS ({host}): La capa solicitada '{wms_layer}' no existe en este servidor.\n\n"
                f"📋 Capas válidas en este servidor: {layer_sample}\n\n"
                f"👉 Por favor selecciona o introduce una de estas capas (ej: '{available[0][0]}') en la barra lateral."
            )

    raise ValueError(f"Servidor WMS ({host}): {last_error or 'No fue posible obtener imagen en los formatos disponibles (TIFF/PNG/JPEG)'}")


def fetch_xyz_ortho(
    session: requests.Session,
    tile_url_template: str,
    crs_str: str,
    bbox_buf: Tuple[float, float, float, float],
    ancho_px: int,
    alto_px: int,
    timeout: int = 25
) -> bytes:
    """
    Descarga ortofotografía satelital desde servidores de teselas XYZ estándar (Google Maps / Esri)
    en Web Mercator (EPSG:3857) y rectifica con precisión subpíxel al Bounding Box y resolución
    exactos del sistema de coordenadas local del dibujo (EPSG:25830, etc.), retornando un archivo TIFF.
    """
    ancho_px = min(4000, max(1, int(ancho_px)))
    alto_px = min(4000, max(1, int(alto_px)))

    t_3857 = Transformer.from_crs(crs_str, "EPSG:3857", always_xy=True)
    t_4326 = Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)

    minx, miny, maxx, maxy = bbox_buf
    target_res_x = (maxx - minx) / ancho_px
    target_res_y = (maxy - miny) / alto_px
    target_res = min(target_res_x, target_res_y)

    lon_c, lat_c = t_4326.transform((minx + maxx) / 2.0, (miny + maxy) / 2.0)
    cos_lat = max(0.05, math.cos(math.radians(lat_c)))

    # Resolución en el ecuador a Zoom 0 es 156543.03392 m/px
    if target_res > 0:
        raw_zoom = math.log2((156543.03392 * cos_lat) / target_res)
        zoom = round(raw_zoom)
    else:
        zoom = 18
    zoom = max(1, min(20, int(zoom)))

    # 4 esquinas del recuadro proyectado en UTM: UL, LL, LR, UR
    corners = [
        (minx, maxy),  # Upper-Left
        (minx, miny),  # Lower-Left
        (maxx, miny),  # Lower-Right
        (maxx, maxy)   # Upper-Right
    ]
    corners_3857 = [t_3857.transform(x, y) for x, y in corners]

    origin_shift = 20037508.342789244

    def get_pixel_coords(z_level: int):
        s_world = 256.0 * (2 ** z_level)
        px_list = []
        for x, y in corners_3857:
            px = (x + origin_shift) / (2.0 * origin_shift) * s_world
            py = (origin_shift - y) / (2.0 * origin_shift) * s_world
            px_list.append((px, py))
        return px_list

    px_corners = get_pixel_coords(zoom)
    min_px_x = min(p[0] for p in px_corners)
    max_px_x = max(p[0] for p in px_corners)
    min_px_y = min(p[1] for p in px_corners)
    max_px_y = max(p[1] for p in px_corners)

    tile_x_min = int(math.floor(min_px_x / 256.0))
    tile_x_max = int(math.floor(max_px_x / 256.0))
    tile_y_min = int(math.floor(min_px_y / 256.0))
    tile_y_max = int(math.floor(max_px_y / 256.0))

    # Control de seguridad: si son más de 64 teselas, retroceder nivel de zoom
    while (tile_x_max - tile_x_min + 1) * (tile_y_max - tile_y_min + 1) > 64 and zoom > 2:
        zoom -= 1
        px_corners = get_pixel_coords(zoom)
        min_px_x = min(p[0] for p in px_corners)
        max_px_x = max(p[0] for p in px_corners)
        min_px_y = min(p[1] for p in px_corners)
        max_px_y = max(p[1] for p in px_corners)
        tile_x_min = int(math.floor(min_px_x / 256.0))
        tile_x_max = int(math.floor(max_px_x / 256.0))
        tile_y_min = int(math.floor(min_px_y / 256.0))
        tile_y_max = int(math.floor(max_px_y / 256.0))

    canvas_w = max(256, (tile_x_max - tile_x_min + 1) * 256)
    canvas_h = max(256, (tile_y_max - tile_y_min + 1) * 256)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (230, 230, 230))

    def fetch_single_tile(tx, ty):
        sub = "mt" + str((tx + ty) % 4)
        url = tile_url_template.format(x=tx, y=ty, z=zoom, s=sub)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
        }
        try:
            resp = session.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200 and len(resp.content) > 100:
                return tx, ty, resp.content
        except Exception:
            pass
        return tx, ty, None

    tile_coords = [(tx, ty) for ty in range(tile_y_min, tile_y_max + 1) for tx in range(tile_x_min, tile_x_max + 1)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(tile_coords) or 1)) as pool:
        futures = [pool.submit(fetch_single_tile, tx, ty) for tx, ty in tile_coords]
        for fut in concurrent.futures.as_completed(futures):
            tx, ty, data = fut.result()
            if data:
                try:
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    cx = (tx - tile_x_min) * 256
                    cy = (ty - tile_y_min) * 256
                    canvas.paste(img, (cx, cy))
                except Exception:
                    pass

    # Coordenadas relativas en el lienzo para las 4 esquinas: UL, LL, LR, UR
    quad_data = []
    for px, py in px_corners:
        quad_data.append(px - (tile_x_min * 256.0))
        quad_data.append(py - (tile_y_min * 256.0))

    rectified = canvas.transform(
        (ancho_px, alto_px),
        Image.QUAD,
        tuple(quad_data),
        resample=Image.BICUBIC
    )

    out_buf = io.BytesIO()
    rectified.save(out_buf, format="TIFF")
    return out_buf.getvalue()


# --------------------------------------------------------------------------------------
# 4. MAPA INTERACTIVO DE CONFIRMACIÓN DE UBICACIÓN
# --------------------------------------------------------------------------------------
def get_crs_default_center(crs_str: str) -> Tuple[float, float, int]:
    """Obtiene latitud, longitud y nivel de zoom aproximados para centrar el mapa según el CRS activo."""
    try:
        c = CRS.from_user_input(crs_str)
        a = c.area_of_use
        if a and a.west is not None and a.east is not None and a.south is not None and a.north is not None:
            lat = max(-80.0, min(84.0, (a.south + a.north) / 2.0))
            lon = (a.west + a.east) / 2.0
            return lat, lon, 7
    except Exception:
        pass
    return 40.4168, -3.7038, 6


def generate_preview_map(
    polygons: Optional[List[Dict[str, Any]]] = None,
    crs_str: str = "EPSG:25830",
    buffer_pct: float = 0.04,
    active_service_key: str = "google_sat",
    custom_wms_url: str = "",
    custom_wms_layer: str = "",
    custom_wms_tag: str = "wms_custom",
    enable_draw: bool = True
) -> folium.Map:
    """
    Crea un mapa interactivo con ortofotografía satelital y capas oficiales del IGN.
    Permite visualizar polígonos existentes (DXF/KML) y trazar nuevas parcelas directamente
    en el visor mediante la barra de herramientas de dibujo (Draw: polígonos y rectángulos).
    """
    has_polys = bool(polygons)
    all_lats: List[float] = []
    all_lons: List[float] = []
    converted_polygons = []

    if has_polys:
        try:
            transformer = Transformer.from_crs(crs_str, "EPSG:4326", always_xy=True)
            for p in polygons:
                pts = p.get("pts", [])
                bounds = p.get("bounds")
                if not pts or not bounds:
                    continue

                latlon_ring = []
                for x, y in pts:
                    try:
                        lon, lat = transformer.transform(x, y)
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            latlon_ring.append([lat, lon])
                            all_lats.append(lat)
                            all_lons.append(lon)
                    except Exception:
                        continue

                # Marco rectangular ortogonal exacto de la salida TIF con buffer
                minx, miny, maxx, maxy = bounds
                dx = (maxx - minx) * buffer_pct
                dy = (maxy - miny) * buffer_pct
                bbox_buf = (minx - dx, miny - dy, maxx + dx, maxy + dy)
                width_salida = bbox_buf[2] - bbox_buf[0]
                height_salida = bbox_buf[3] - bbox_buf[1]
                bbox_corners = [
                    (bbox_buf[0], bbox_buf[1]),
                    (bbox_buf[2], bbox_buf[1]),
                    (bbox_buf[2], bbox_buf[3]),
                    (bbox_buf[0], bbox_buf[3])
                ]

                bbox_latlon = []
                for x, y in bbox_corners:
                    try:
                        lon, lat = transformer.transform(x, y)
                        if -90 <= lat <= 90 and -180 <= lon <= 180:
                            bbox_latlon.append([lat, lon])
                            all_lats.append(lat)
                            all_lons.append(lon)
                    except Exception:
                        continue

                if len(latlon_ring) >= 3:
                    converted_polygons.append({
                        "info": p,
                        "locations": latlon_ring,
                        "bbox_locations": bbox_latlon,
                        "width_salida": round(width_salida, 1),
                        "height_salida": round(height_salida, 1),
                        "center": [sum(pt[0] for pt in latlon_ring)/len(latlon_ring), sum(pt[1] for pt in latlon_ring)/len(latlon_ring)]
                    })
        except Exception:
            pass

    if all_lats and all_lons:
        center_lat = sum(all_lats) / len(all_lats)
        center_lon = sum(all_lons) / len(all_lons)
        zoom_start = 15
    else:
        center_lat, center_lon, zoom_start = get_crs_default_center(crs_str)

    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=zoom_start,
        control_scale=True
    )

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="🌍 Google Satélite (Mundial)",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
        attr="Google Maps",
        name="🌍 Google Híbrido (Satélite + Vías)",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri Satellite",
        name="🛰️ Esri World Imagery",
        overlay=False,
        control=True
    ).add_to(m)

    folium.TileLayer(
        tiles="OpenStreetMap",
        name="🗺️ Callejero OpenStreetMap",
        overlay=False,
        control=True
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://www.ign.es/wms-inspire/pnoa-ma",
        layers="OI.OrthoimageCoverage",
        fmt="image/png",
        transparent=True,
        name="🇪🇸 Ortofoto PNOA WMS (IGN)",
        overlay=True,
        control=True,
        show=(active_service_key == "pnoa")
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://www.ign.es/wms-inspire/mapa-raster",
        layers="mtn_rasterizado",
        fmt="image/png",
        transparent=True,
        name="🗺️ IGN Mapa Ráster MTN Topográfico",
        overlay=True,
        control=True,
        show=(active_service_key == "mapa_raster")
    ).add_to(m)

    folium.WmsTileLayer(
        url="https://servicios.idee.es/wms-inspire/mdt",
        layers="EL.GridCoverage",
        fmt="image/png",
        transparent=True,
        name="🏔️ IGN Modelo Digital Relieve (MDT)",
        overlay=True,
        control=True,
        show=(active_service_key == "mdt_relieve")
    ).add_to(m)

    if active_service_key == "custom" and custom_wms_url and custom_wms_layer:
        try:
            folium.WmsTileLayer(
                url=custom_wms_url.split("?")[0].strip(),
                layers=custom_wms_layer,
                fmt="image/png",
                transparent=True,
                name=f"⚙️ WMS Personalizado ({custom_wms_tag})",
                overlay=True,
                control=True,
                show=True
            ).add_to(m)
        except Exception:
            pass

    colors = ["#f59e0b", "#06b6d4", "#10b981", "#ec4899", "#8b5cf6", "#3b82f6"]
    for i, poly_item in enumerate(converted_polygons):
        p_info = poly_item["info"]
        col = colors[i % len(colors)]

        # 1. Polígono del Marco de la Imagen de Salida (TIF resultante con buffer)
        if len(poly_item["bbox_locations"]) == 4:
            bbox_popup_html = f"""
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; line-height: 1.5; min-width: 210px; color: #f8fafc;">
                <div style="color: {col}; font-size: 14px; font-weight: 700; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 6px;">🖼️ Imagen de Salida TIF #{p_info['id']}</div>
                <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Archivo:</b> <span style="font-family: monospace;">{p_info['nombre_archivo']}.tif</span></div>
                <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Encuadre:</b> {poly_item['width_salida']} × {poly_item['height_salida']} m</div>
                <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Buffer perimetral:</b> {round(buffer_pct * 100)}%</div>
                <div><b style="color: #94a3b8;">Calidad recomendada:</b> <span style="color: #10b981; font-weight: 600;">{p_info.get('calidad_sugerida', '1.00 m/px')}</span></div>
            </div>
            """

            folium.Polygon(
                locations=poly_item["bbox_locations"],
                color=col,
                weight=2,
                dash_array="6, 6",
                fill=True,
                fill_color=col,
                fill_opacity=0.10,
                popup=folium.Popup(bbox_popup_html, max_width=320),
                tooltip=f"🖼️ Salida #{p_info['id']} | {poly_item['width_salida']}m × {poly_item['height_salida']}m"
            ).add_to(m)

        # 2. Polígono de la Geometría CAD (Parcela interior)
        popup_html = f"""
        <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; font-size: 13px; line-height: 1.5; min-width: 190px; color: #f8fafc;">
            <div style="color: {col}; font-size: 14px; font-weight: 700; border-bottom: 1px solid #334155; padding-bottom: 4px; margin-bottom: 6px;">📐 Geometría CAD #{p_info['id']}</div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Capa:</b> <span style="background: #334155; padding: 1px 5px; border-radius: 4px; font-family: monospace;">{p_info['capa']}</span></div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Nombre:</b> {p_info['nombre_archivo']}</div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Dimensiones:</b> {p_info['ancho_m']} × {p_info['alto_m']} m</div>
            <div style="margin-bottom: 3px;"><b style="color: #94a3b8;">Área:</b> <span style="color: #38bdf8; font-weight: 600;">{p_info['area_m2']:,} m²</span> ({(p_info['area_m2']/10000):.2f} ha)</div>
            <div><b style="color: #94a3b8;">Calidad sugerida:</b> <span style="color: #10b981; font-weight: 600;">{p_info.get('calidad_sugerida', '1.00 m/px')}</span></div>
        </div>
        """

        folium.Polygon(
            locations=poly_item["locations"],
            color=col,
            weight=3,
            fill=True,
            fill_color=col,
            fill_opacity=0.35,
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=f"📐 Parcela #{p_info['id']} | {p_info['capa']} ({p_info['ancho_m']}m × {p_info['alto_m']}m)"
        ).add_to(m)

        folium.CircleMarker(
            location=poly_item["center"],
            radius=6,
            color="#ffffff",
            weight=2,
            fill=True,
            fill_color=col,
            fill_opacity=0.9,
            tooltip=f"Centroide Polígono #{p_info['id']}"
        ).add_to(m)

    if all_lats and all_lons:
        min_lat, max_lat = min(all_lats), max(all_lats)
        min_lon, max_lon = min(all_lons), max(all_lons)
        m.fit_bounds([[min_lat, min_lon], [max_lat, max_lon]])

    # Barra de herramientas para dibujar polígonos o rectángulos libres en el mapa
    if enable_draw:
        Draw(
            export=False,
            filename="poligono.geojson",
            position="topleft",
            draw_options={
                "polyline": False,
                "rectangle": True,
                "polygon": True,
                "circle": False,
                "marker": False,
                "circlemarker": False
            },
            edit_options={"edit": True, "remove": True}
        ).add_to(m)

    folium.LayerControl(position="topright", collapsed=False).add_to(m)

    return m


# --------------------------------------------------------------------------------------
# 5. INTERFAZ GRÁFICA STREAMLIT
# --------------------------------------------------------------------------------------
def render_ui():
    """Construye y gestiona la interfaz interactiva de Streamlit."""

    st.markdown("""
    <style>
        /* Encabezado principal en Modo Oscuro */
        .main-header {
            background: linear-gradient(135deg, #091e3a 0%, #0f172a 50%, #1e293b 100%);
            border: 1px solid #334155;
            padding: 1.8rem 2rem;
            border-radius: 14px;
            color: #ffffff;
            margin-bottom: 1.5rem;
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
        }
        .main-header h1 {
            color: #38bdf8 !important;
            margin: 0;
            font-size: 2.1rem;
            font-weight: 700;
            letter-spacing: -0.02em;
        }
        .main-header p {
            color: #cbd5e1 !important;
            margin: 0.5rem 0 0 0;
            font-size: 1.05rem;
        }

        /* Botón de descarga principal */
        .stDownloadButton button {
            background: linear-gradient(135deg, #10b981 0%, #059669 100%) !important;
            color: white !important;
            font-weight: bold !important;
            font-size: 1.05rem !important;
            padding: 0.75rem 2rem !important;
            border-radius: 10px !important;
            border: none !important;
            box-shadow: 0 4px 14px rgba(16, 185, 129, 0.35) !important;
            transition: all 0.2s ease !important;
        }
        .stDownloadButton button:hover {
            background: linear-gradient(135deg, #34d399 0%, #047857 100%) !important;
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(16, 185, 129, 0.45) !important;
        }

        /* Ajustes de contenedores y desplegables */
        div[data-testid="stExpander"] {
            border: 1px solid #334155 !important;
            background-color: #1e293b !important;
            border-radius: 10px !important;
        }
        div[data-testid="stExpander"] details summary {
            color: #f1f5f9 !important;
        }

        /* Métricas */
        div[data-testid="stMetricValue"] {
            color: #38bdf8 !important;
        }

        /* Leaflet Popups oscuros */
        .leaflet-popup-content-wrapper, .leaflet-popup-tip {
            background: #1e293b !important;
            color: #f8fafc !important;
            box-shadow: 0 10px 25px rgba(0,0,0,0.6) !important;
            border: 1px solid #334155 !important;
        }
        .leaflet-container {
            border-radius: 12px;
            border: 1px solid #334155;
        }
    </style>
    """, unsafe_allow_html=True)

    # Sincronización segura de estados pendientes antes de instanciar widgets de Streamlit
    if "pending_epsg_code" in st.session_state:
        new_code = st.session_state.pop("pending_epsg_code")
        st.session_state["active_epsg_code"] = int(new_code)
        st.session_state["sidebar_epsg_input"] = str(new_code)
        if int(new_code) not in [25829, 25830, 25831, 32628]:
            st.session_state["selected_service_idx"] = 0

    if "pending_custom_wms_layer" in st.session_state:
        st.session_state["custom_wms_layer_input"] = str(st.session_state.pop("pending_custom_wms_layer"))

    if "active_epsg_code" not in st.session_state:
        st.session_state["active_epsg_code"] = 25830
    if "sidebar_epsg_input" not in st.session_state:
        st.session_state["sidebar_epsg_input"] = str(st.session_state["active_epsg_code"])

    # ----------------------------------------------------------------------------------
    # BARRA LATERAL (SIDEBAR): CONFIGURACIÓN GLOBAL
    # ----------------------------------------------------------------------------------
    st.sidebar.header("⚙️ Configuración Global")

    # 1. Sistema de Referencia de Coordenadas (CRS / Proyección)
    st.sidebar.subheader("1. Proyección Cartográfica (CRS)")
    
    crs_mode = st.sidebar.radio(
        "Modo de selección del CRS:",
        options=["Código EPSG directo (Cualquier país)", "Preajustes regionales comunes"],
        index=0,
        horizontal=True,
        help="Introduce directamente el código EPSG de tu plano (ej: Australia 7855, España 25830, Colombia 9377) o usa un preajuste."
    )

    regional_presets = {
        "🇦🇺 Australia - GDA2020 / MGA zone 55 (EPSG:7855)": 7855,
        "🇦🇺 Australia - GDA2020 / MGA zone 56 (EPSG:7856)": 7856,
        "🇦🇺 Australia - GDA2020 / MGA zone 54 (EPSG:7854)": 7854,
        "🇦🇺 Australia - GDA94 / MGA zone 55 (EPSG:28355)": 28355,
        "🇦🇺 Australia - GDA94 / MGA zone 56 (EPSG:28356)": 28356,
        "🇪🇸 España - ETRS89 / UTM 30N (EPSG:25830)": 25830,
        "🇪🇸 España - ETRS89 / UTM 29N (Galicia) (EPSG:25829)": 25829,
        "🇪🇸 España - ETRS89 / UTM 31N (Cataluña/Baleares) (EPSG:25831)": 25831,
        "🇪🇸 Canarias - WGS 84 / UTM 28N (EPSG:32628)": 32628,
        "🌎 Global - WGS 84 / UTM 30N (EPSG:32630)": 32630,
        "🌎 Global - WGS 84 / Web Mercator (EPSG:3857)": 3857,
        "🌎 Global - WGS 84 Geográficas (EPSG:4326)": 4326,
        "🇲🇽 México - ITRF2008 / UTM 14N (EPSG:6369)": 6369,
        "🇨🇴 Colombia - MAGNA-SIRGAS Origen Nacional (EPSG:9377)": 9377,
        "🇨🇴 Colombia - Bogotá / MAGNA Bogotá (EPSG:3116)": 3116,
        "🇨🇱 Chile - SIRGAS-Chile / UTM 19S (EPSG:5361)": 5361,
        "🇦🇷 Argentina - POSGAR 07 / Faja 4 (EPSG:5346)": 5346,
        "🇺🇸 USA - NAD83 / UTM zone 18N (EPSG:26918)": 26918,
        "🇺🇸 USA - NAD83 / UTM zone 10N (EPSG:26910)": 26910
    }

    if crs_mode == "Código EPSG directo (Cualquier país)":
        epsg_raw = st.sidebar.text_input(
            "Código EPSG de tu plano CAD:",
            key="sidebar_epsg_input",
            help="Ejemplos mundiales: 7855 o 28355 (Australia), 25830 (España), 32618 (Colombia/Panamá/USA), 32719 (Chile/Perú), 32630 (Europa/África), 6369 (México)."
        ).strip().upper().replace("EPSG:", "").strip()

        try:
            epsg_code = int(epsg_raw)
            st.session_state["active_epsg_code"] = epsg_code
        except ValueError:
            epsg_code = st.session_state.get("active_epsg_code", 25830)
            st.sidebar.warning("⚠️ Código numérico no válido. Usando EPSG:25830 por defecto.")
    else:
        preset_names = list(regional_presets.keys())
        preset_codes = list(regional_presets.values())
        curr_code = st.session_state.get("active_epsg_code", 25830)
        default_preset_idx = preset_codes.index(curr_code) if curr_code in preset_codes else 0

        preset_label = st.sidebar.selectbox(
            "Selecciona proyección regional:",
            options=preset_names,
            index=default_preset_idx
        )
        epsg_code = regional_presets[preset_label]
        st.session_state["active_epsg_code"] = epsg_code

    crs_str = f"EPSG:{epsg_code}"

    try:
        pyproj_crs = CRS.from_epsg(epsg_code)
        crs_name = pyproj_crs.name
        area_name = pyproj_crs.area_of_use.name if pyproj_crs.area_of_use else "Global / No especificado"
        st.sidebar.markdown(f"""
        <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #059669; border-radius: 8px; padding: 8px 12px; margin-top: 5px; margin-bottom: 10px;">
            <div style="font-weight: 700; color: #10b981; font-size: 13px;">✅ EPSG:{epsg_code} Activo</div>
            <div style="color: #f1f5f9; font-size: 12px; font-weight: 600;">{crs_name}</div>
            <div style="color: #94a3b8; font-size: 11px; margin-top: 2px;">📍 Ámbito: {area_name[:55]}...</div>
        </div>
        """, unsafe_allow_html=True)
    except Exception as crs_err:
        st.sidebar.error(f"⚠️ EPSG:{epsg_code} no reconocido: {crs_err}")

    # 2. Buffer porcentual de encuadre
    st.sidebar.subheader("2. Margen de Encuadre (Buffer)")
    buffer_slider = st.sidebar.slider(
        "Buffer porcentual (%):",
        min_value=0,
        max_value=15,
        value=4,
        step=1,
        help="Margen perimetral adicional (%) alrededor del polígono para no cortar bordes de obra o parcela."
    )
    buffer_pct = buffer_slider / 100.0

    # 3. Estrategia para áreas extensas (> 4000 px)
    st.sidebar.subheader("3. Estrategia para Áreas Extensas")
    large_area_mode = st.sidebar.radio(
        "Si la imagen excede el límite del IGN (4000 px):",
        options=[
            "Ajustar a 4000 px (Imagen única)",
            "Dividir en mosaico / teselas (Máxima resolución)"
        ],
        index=0,
        help=(
            "El servidor del IGN rechaza peticiones mayores a 4096 px. "
            "'Ajustar a 4000 px' escala suavemente para mantener un único archivo .tif. "
            "'Dividir en mosaico' crea teselas contiguas respetando la resolución milimétrica exacta."
        )
    )

    # 4. Servicio Cartográfico y Satelital (WMS IGN / Google Satélite / Esri)
    st.sidebar.subheader("4. Servicio Cartográfico / Satelital")
    service_keys = list(SERVICES_CATALOG.keys())
    service_labels = [SERVICES_CATALOG[k]["name"] for k in service_keys]

    default_serv_idx = st.session_state.get("selected_service_idx", 0)
    if default_serv_idx >= len(service_labels):
        default_serv_idx = 0

    selected_service_label = st.sidebar.selectbox(
        "Capa o servicio a descargar:",
        options=service_labels,
        index=default_serv_idx,
        help=(
            "Selecciona la fuente de imagen para tu plano CAD:\n"
            "- Ortofoto Aérea PNOA (IGN España - Vuelo oficial de máxima resolución)\n"
            "- Google Satélite (Fotografía satelital mundial de alta resolución)\n"
            "- Google Híbrido (Satélite con carreteras, autopistas y nombres)\n"
            "- Esri World Imagery (Imágenes satelitales globales de alta resolución)\n"
            "- Mapa Ráster IGN (Cartografía MTN25/MTN50 oficial con curvas de nivel)\n"
            "- Modelo Digital del Terreno (Sombreado continuo de relieve LiDAR/MDT)\n"
            "- Personalizado (Cualquier servidor WMS 1.3.0)"
        )
    )

    selected_service_key = service_keys[service_labels.index(selected_service_label)]
    st.session_state["selected_service_idx"] = service_labels.index(selected_service_label)
    service_info = SERVICES_CATALOG[selected_service_key]

    if selected_service_key == "custom":
        st.sidebar.markdown("""
        <div style="background: rgba(56, 189, 248, 0.1); border-left: 3px solid #38bdf8; padding: 6px 10px; border-radius: 4px; margin-bottom: 8px; font-size: 12px; color: #cbd5e1;">
            💡 <b>Conexión WMS Universal:</b> Puedes conectar cualquier servidor de cartografía u ortofotos oficial del mundo (Australia, Europa, América, etc.).
        </div>
        """, unsafe_allow_html=True)
        wms_url = st.sidebar.text_input(
            "URL base del servicio WMS:",
            value=st.session_state.get("custom_wms_url_val", ""),
            placeholder="https://servidor-geoportal.com/.../WMSServer",
            help="URL base del servicio OGC WMS (sin parámetros después del signo ?)"
        ).split("?")[0].strip()
        st.session_state["custom_wms_url_val"] = wms_url

        # Detección y exploración inteligente de capas publicadas por el servidor
        detected_layers = fetch_wms_service_layers(wms_url) if (wms_url and wms_url.startswith("http")) else []

        # Si el usuario cambió la URL del WMS, sincronizar automáticamente a la primera capa
        last_url = st.session_state.get("last_custom_wms_url", "")
        if wms_url and wms_url != last_url:
            st.session_state["last_custom_wms_url"] = wms_url
            if detected_layers:
                st.session_state["custom_wms_layer_input"] = detected_layers[0][0]

        if detected_layers:
            layer_labels = [f"{n} ({t})" if n != t and t else n for n, t in detected_layers]
            layer_names = [n for n, t in detected_layers]

            def _on_detected_layer_change():
                sel = st.session_state.get("custom_detected_layer_select")
                if sel and sel != "(Escribir o editar abajo)":
                    idx = layer_labels.index(sel)
                    st.session_state["pending_custom_wms_layer"] = layer_names[idx]

            st.sidebar.selectbox(
                "📋 Capas disponibles detectadas en este servidor:",
                options=["(Escribir o editar abajo)"] + layer_labels,
                key="custom_detected_layer_select",
                on_change=_on_detected_layer_change,
                help="Selecciona una capa detectada en el servidor WMS para rellenar automáticamente el campo."
            )

        if "custom_wms_layer_input" not in st.session_state:
            st.session_state["custom_wms_layer_input"] = detected_layers[0][0] if detected_layers else "0"

        wms_layer = st.sidebar.text_input(
            "Nombre técnico de la capa (Layer):",
            key="custom_wms_layer_input",
            placeholder="0, 1 o 0,1,2,3",
            help="Identificador exacto de la capa en el servidor WMS (ej: 0, 1, 0,1,2,3, ortho2020funcion, etc.)"
        ).strip()
        st.session_state["custom_wms_layer_val"] = wms_layer

        wms_tag = st.sidebar.text_input(
            "Etiqueta para archivos (Tag):",
            value="wms_custom",
            help="Prefijo corto que se incluirá en los nombres de archivo .tif y .tfw"
        ).strip()
    else:
        st.sidebar.caption(f"ℹ️ **{service_info['badge']}:** {service_info['description']}")
        with st.sidebar.expander("⚙️ Ver detalles técnicos del servicio", expanded=False):
            if service_info.get("type") == "xyz":
                info_tech = f"Tipo: Servidor de teselas XYZ (Web Mercator EPSG:3857)\nURL Plantilla: {service_info['url']}"
            else:
                info_tech = f"Tipo: OGC WMS 1.3.0\nURL: {service_info['url']}\nCapa: {service_info['layer']}"
                if selected_service_key == "mapa_raster":
                    info_tech += "\nEndpoint WMTS: https://www.ign.es/wmts/mapa-raster"
            st.code(info_tech, language="text")
        wms_url = service_info["url"]
        wms_layer = service_info.get("layer", "")
        wms_tag = service_info["tag"]

    # 5. Límites de seguridad
    with st.sidebar.expander("🛡️ Límites de Seguridad de Descarga", expanded=False):
        max_pixels_lado = st.number_input(
            "Máx. píxeles por lado:",
            min_value=1000,
            max_value=4000,
            value=4000,
            step=250,
            help="Límite del servidor IGN: Máximo 4000 px para evitar rechazos por MapServer (MAXSIZE=4096)."
        )
        max_pixels_totales = st.number_input(
            "Máx. píxeles acumulados:",
            min_value=1000000,
            max_value=16000000,
            value=16000000,
            step=1000000,
            help="Límite acumulado de resolución (ancho × alto) de seguridad."
        )

    # ----------------------------------------------------------------------------------
    # ENCABEZADO Y EXPLICACIÓN PARA USUARIOS DE AUTOCAD
    # ----------------------------------------------------------------------------------
    st.markdown("""
    <div class="main-header">
        <h1>🌍 GeoRaster to CAD | Extractor Georreferenciado Universal</h1>
        <p>Extracción y georreferenciación de <b>cualquier servidor WMS del mundo</b>, Google Satélite, Esri y cartografía oficial para AutoCAD, Civil 3D y BricsCAD en formato <b>TIF + TFW</b>.</p>
    </div>
    """, unsafe_allow_html=True)

    with st.expander("📖 Guía de uso rápido y cómo insertar en AutoCAD / Civil 3D", expanded=False):
        st.markdown("""
        **Instrucciones para delineantes, topógrafos e ingenieros de cualquier país:**
        1. **Define la proyección (CRS)**: En la barra lateral, escribe directamente el código **EPSG** de tu plano (ej. `7855` para Australia GDA2020, `25830` para España ETRS89, `9377` para Colombia MAGNA, `32618` para WGS84 UTM 18N, etc.) o elige un preajuste regional.
        2. **Selecciona la fuente de imagen**: Elige **Google Satélite** (mundial limpio), **Google Híbrido** (con vías y nombres), **Esri World Imagery**, **Cualquier servidor WMS del mundo** o servicios nacionales (PNOA/IGN).
        3. **Carga tu archivo `.dxf`**: El dibujo debe contener polilíneas cerradas (`LWPOLYLINE` o `POLYLINE`) que delimiten el ámbito de trabajo o parcelas.
        4. **Verifica la ubicación en el visor interactivo**: Confirma visualmente que las geometrías caen sobre la imagen en la posición real de tu proyecto y revisa el recuadro de salida.
        5. **Descarga el `.zip`**: Contiene los archivos georreferenciados para cada polígono:
           - **`.tif`**: Imagen ráster recortada en máxima resolución.
           - **`.tfw`**: Archivo *World File* de calibración espacial con coordenadas UTM/proyectadas exactas.
        
        **Cómo insertar en AutoCAD en su posición proyectada exacta:**
        - **AutoCAD Map 3D / Civil 3D**: Ejecuta el comando `_MAPIINSERT` (o ve a *Insertar* -> *Imagen ráster*). Al seleccionar los archivos `.tif`, AutoCAD detectará automáticamente los archivos `.tfw` asociados e insertará las ortofotos en sus **coordenadas reales de proyecto**.
        - **AutoCAD Estándar / LT**: Inserta mediante el comando `_IMAGEATTACH` (`ENLAZARIMG`).
        - **Consejo para minutas o parcelas en diagonal**: Para recortar la ortofoto siguiendo la forma exacta de una minuta inclinada en AutoCAD, usa el comando nativo `_IMAGECLIP` (`DELIMIMG`) -> *Nuevo contorno* (`N`) -> *Seleccionar polilínea* (`S`) y toca tu polilínea. AutoCAD ocultará los bordes sobrantes al instante manteniendo la georreferenciación perfecta.
        """)

    if "processed_zip_data" not in st.session_state:
        st.session_state["processed_zip_data"] = None
    if "processed_zip_name" not in st.session_state:
        st.session_state["processed_zip_name"] = None
    if "processed_summary" not in st.session_state:
        st.session_state["processed_summary"] = []
    if "demo_active" not in st.session_state:
        st.session_state["demo_active"] = False
    if "draw_only_mode" not in st.session_state:
        st.session_state["draw_only_mode"] = False
    if "persisted_drawings" not in st.session_state:
        st.session_state["persisted_drawings"] = []
    if "draw_version" not in st.session_state:
        st.session_state["draw_version"] = 0
    if "is_vector_exportable" not in st.session_state:
        st.session_state["is_vector_exportable"] = False

    # ----------------------------------------------------------------------------------
    # CARGA DE ARCHIVO (DXF / KML / KMZ) Y ACCIONES RÁPIDAS
    # ----------------------------------------------------------------------------------
    col_up, col_demo = st.columns([2.8, 1.4])

    with col_up:
        uploaded_file = st.file_uploader(
            "📁 Carga tu plano AutoCAD (DXF) o polígonos Google Earth (KML / KMZ):",
            type=["dxf", "kml", "kmz"],
            help="Sube un archivo DXF con polilíneas cerradas, o un archivo KML / KMZ exportado desde Google Earth."
        )

    with col_demo:
        st.write("")
        st.markdown("<b style='font-size: 13px; color: #94a3b8;'>⚡ Acciones rápidas:</b>", unsafe_allow_html=True)
        col_d1, col_d2, col_d3 = st.columns(3)
        with col_d1:
            if st.button("✏️ Dibujar", help="Abre el visor para trazar polígonos directamente sin archivo", use_container_width=True):
                st.session_state["draw_only_mode"] = True
                st.session_state["demo_active"] = False
                st.session_state["processed_zip_data"] = None
        with col_d2:
            if st.button("🇪🇸 Madrid", help="Genera plano DXF demo en Madrid (EPSG:25830)", use_container_width=True):
                st.session_state["demo_active"] = "madrid"
                st.session_state["draw_only_mode"] = False
                st.session_state["pending_epsg_code"] = 25830
                st.session_state["processed_zip_data"] = None
                st.rerun()
        with col_d3:
            if st.button("🇦🇺 Australia", help="Genera plano DXF demo en Melbourne (EPSG:7855)", use_container_width=True):
                st.session_state["demo_active"] = "australia"
                st.session_state["draw_only_mode"] = False
                st.session_state["pending_epsg_code"] = 7855
                st.session_state["processed_zip_data"] = None
                st.rerun()

    file_polygons: List[Dict[str, Any]] = []
    dxf_display_name = ""
    is_vector_exportable = False
    kml_centroid: Optional[Tuple[float, float]] = None
    raw_dxf_snippet = ""
    dxf_bytes = None

    if uploaded_file is not None:
        st.session_state["demo_active"] = False
        st.session_state["draw_only_mode"] = False
        filename = uploaded_file.name
        ext = os.path.splitext(filename)[1].lower()
        file_bytes = uploaded_file.getvalue()
        dxf_display_name = filename

        try:
            if ext in (".kml", ".kmz"):
                with st.spinner("Leyendo polígonos de Google Earth (KML/KMZ)..."):
                    file_polygons, kml_centroid = parse_kml_or_kmz_polygons(
                        file_bytes, filename, target_crs_str=crs_str, service_tag=wms_tag
                    )
                is_vector_exportable = True
                if not file_polygons:
                    st.warning("⚠️ No se encontraron polígonos cerrados en el archivo KML/KMZ. Comprueba que contiene geometrías tipo Polygon o rutas cerradas en Google Earth.")
            elif ext == ".dxf":
                with st.spinner("Leyendo entidades del plano DXF..."):
                    file_polygons = parse_dxf_polygons(file_bytes, filename, service_tag=wms_tag)
                dxf_bytes = file_bytes
                raw_dxf_snippet = file_bytes[:100000].decode("latin-1", errors="ignore")
                if not file_polygons:
                    st.warning("""
                    ⚠️ **No se encontraron polilíneas cerradas en el espacio modelo del archivo DXF.**
                    
                    **Recomendaciones para AutoCAD:**
                    - Comprueba que las parcelas son entidades `LWPOLYLINE` o `POLYLINE`.
                    - Selecciona la polilínea, abre la paleta de Propiedades (`Ctrl+1`) y verifica que **Cerrada = Sí**.
                    - En la línea de comandos, ejecuta `EDITPOL` (`PEDIT`) y elige la opción **Cerrar**.
                    """)
        except Exception as e:
            st.error(f"❌ Error al procesar el archivo `{filename}`: {e}")
            with st.expander("Detalle del error técnico"):
                st.code(traceback.format_exc())

    elif st.session_state.get("demo_active"):
        demo_mode = st.session_state.get("demo_active")
        if demo_mode == "australia":
            demo_doc = ezdxf.new("R2010")
            demo_msp = demo_doc.modelspace()
            p1 = [(320650, 5812850), (320750, 5812850), (320750, 5812950), (320650, 5812950)]
            poly1 = demo_msp.add_lwpolyline(p1, close=True)
            poly1.dxf.layer = "PARCELA_MELBOURNE_VIC"

            p2 = [(321100, 5813200), (321280, 5813200), (321280, 5813350), (321100, 5813350)]
            poly2 = demo_msp.add_lwpolyline(p2, close=True)
            poly2.dxf.layer = "AMBITO_OBRA_AUSTRALIA"

            out_str = io.StringIO()
            demo_doc.write(out_str)
            dxf_bytes = out_str.getvalue().encode("utf-8")
            dxf_display_name = "demo_melbourne_australia.dxf"
            st.info("💡 Modo de demostración activo: Plano con 2 geometrías en Melbourne, Australia.")
        else:
            demo_doc = ezdxf.new("R2010")
            demo_msp = demo_doc.modelspace()
            p1 = [(441300, 4478100), (441360, 4478100), (441360, 4478150), (441300, 4478150)]
            poly1 = demo_msp.add_lwpolyline(p1, close=True)
            poly1.dxf.layer = "SOLAR_EDIFICACION"

            p2 = [(441800, 4473800), (441920, 4473800), (441920, 4473900), (441800, 4473900)]
            poly2 = demo_msp.add_lwpolyline(p2, close=True)
            poly2.dxf.layer = "PARCELA_INDUSTRIAL"

            p3 = [(441300, 4476800), (441600, 4476980), (441480, 4477180), (441180, 4477000)]
            poly3 = demo_msp.add_lwpolyline(p3, close=True)
            poly3.dxf.layer = "AMBITO_OBRA"

            out_str = io.StringIO()
            demo_doc.write(out_str)
            dxf_bytes = out_str.getvalue().encode("utf-8")
            dxf_display_name = "demo_madrid_pnoa.dxf"
            st.info("💡 Modo de demostración activo: Plano con 3 geometrías en Madrid (EPSG:25830).")

        file_polygons = parse_dxf_polygons(dxf_bytes, dxf_display_name, service_tag=wms_tag)
        raw_dxf_snippet = dxf_bytes[:100000].decode("latin-1", errors="ignore")
        is_vector_exportable = True

    # Integrar geometrías dibujadas interactivamente en el mapa
    persisted_drawings = st.session_state.get("persisted_drawings", [])
    drawn_polys: List[Dict[str, Any]] = []
    if persisted_drawings:
        drawn_polys = parse_drawn_features(
            persisted_drawings,
            target_crs_str=crs_str,
            start_id=len(file_polygons) + 1,
            service_tag=wms_tag
        )
        is_vector_exportable = True

    extracted_polygons = file_polygons + drawn_polys
    if not dxf_display_name:
        dxf_display_name = "trazado_mapa.dxf" if drawn_polys else "proyecto.dxf"

    # ----------------------------------------------------------------------------------
    # RECOMENDACIÓN INTELIGENTE DE PROYECCIÓN CARTOGRÁFICA (CRS / EPSG)
    # ----------------------------------------------------------------------------------
    rec_crs_list: List[Dict[str, Any]] = []
    if kml_centroid is not None:
        rec_crs_list = detect_epsg_from_lonlat(kml_centroid[0], kml_centroid[1])
    elif persisted_drawings and not file_polygons:
        all_draw_lons: List[float] = []
        all_draw_lats: List[float] = []
        for d in persisted_drawings:
            coords = d.get("geometry", {}).get("coordinates", [])
            def _extract_c(c_arr):
                for item in c_arr:
                    if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[0], (int, float)):
                        all_draw_lons.append(float(item[0]))
                        all_draw_lats.append(float(item[1]))
                    elif isinstance(item, (list, tuple)):
                        _extract_c(item)
            _extract_c(coords)
        if all_draw_lons and all_draw_lats:
            rec_crs_list = detect_epsg_from_lonlat(
                sum(all_draw_lons) / len(all_draw_lons),
                sum(all_draw_lats) / len(all_draw_lats)
            )
    elif file_polygons:
        all_minx = min(p["bounds"][0] for p in file_polygons)
        all_miny = min(p["bounds"][1] for p in file_polygons)
        all_maxx = min(p["bounds"][2] for p in file_polygons)
        all_maxy = min(p["bounds"][3] for p in file_polygons)
        total_bounds = (all_minx, all_miny, all_maxx, all_maxy)
        layers_found = list(set(p["capa"] for p in file_polygons))
        rec_crs_list = detect_recommended_epsg(total_bounds, layer_names=layers_found, raw_text=raw_dxf_snippet)

    if rec_crs_list:
        top_rec = rec_crs_list[0]
        if epsg_code == top_rec["code"]:
            st.markdown(f"""
            <div style="background: rgba(16, 185, 129, 0.12); border: 1px solid #059669; border-radius: 10px; padding: 12px 16px; margin: 12px 0 16px 0;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 18px;">✅</span>
                    <div style="color: #10b981; font-weight: 700; font-size: 14px;">
                        Proyección Activa Verificada: Coincide con EPSG:{epsg_code} ({top_rec['name']})
                    </div>
                </div>
                <div style="color: #cbd5e1; font-size: 12px; margin-top: 3px; padding-left: 26px;">
                    📍 <b>Ámbito:</b> {top_rec['region']} &mdash; <i>{top_rec['reason']}</i>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(30, 41, 59, 0.95) 0%, rgba(15, 23, 42, 0.98) 100%);
                        border: 2px solid #38bdf8; border-radius: 12px; padding: 16px 20px; margin: 12px 0 16px 0;
                        box-shadow: 0 8px 24px rgba(56, 189, 248, 0.18);">
                <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px; margin-bottom: 8px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 22px;">💡</span>
                        <span style="color: #38bdf8; font-size: 1.15rem; font-weight: 700;">
                            Sugerencia Inteligente de Coordenadas: ¿Tu plano es EPSG:{top_rec['code']}?
                        </span>
                    </div>
                    <span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 6px; border: 1px solid rgba(56, 189, 248, 0.4);">
                        Confianza {top_rec['confidence']}
                    </span>
                </div>
                <div style="color: #f1f5f9; font-size: 0.95rem; font-weight: 600; margin-bottom: 4px;">
                    🎯 <b>{top_rec['name']}</b> &mdash; <span style="color: #94a3b8; font-weight: 400;">{top_rec['region']}</span>
                </div>
                <div style="color: #cbd5e1; font-size: 0.88rem; margin-bottom: 12px; line-height: 1.4;">
                    {top_rec['reason']} Actualmente tienes seleccionada en la barra lateral la proyección <b>{crs_str}</b>.
                </div>
            </div>
            """, unsafe_allow_html=True)

            c_btn_top, c_btn_alts = st.columns([1.6, 2.4])
            with c_btn_top:
                btn_label = f"✨ Aplicar recomendada: EPSG:{top_rec['code']}"
                if st.button(btn_label, type="primary", use_container_width=True, key=f"btn_apply_{top_rec['code']}"):
                    st.session_state["pending_epsg_code"] = top_rec["code"]
                    st.rerun()

            with c_btn_alts:
                if len(rec_crs_list) > 1:
                    alts = rec_crs_list[1:3]
                    alt_cols = st.columns(len(alts))
                    for i, alt in enumerate(alts):
                        with alt_cols[i]:
                            alt_name_short = alt['name'].split('(')[0].replace("GDA2020 / ", "").replace("ETRS89 / ", "").strip()
                            if st.button(f"Probar EPSG:{alt['code']} ({alt_name_short})", use_container_width=True, key=f"btn_alt_{alt['code']}", help=f"{alt['name']} - {alt['region']}"):
                                st.session_state["pending_epsg_code"] = alt["code"]
                                st.rerun()

            if len(rec_crs_list) > 3 or any("alt_code" in r for r in rec_crs_list):
                with st.expander("🔍 Ver otras opciones geodésicas detectadas (ej. GDA94 / Husos secundarios)", expanded=False):
                    for r in rec_crs_list:
                        if "alt_code" in r:
                            c_a1, c_a2 = st.columns([3, 1])
                            c_a1.write(f"**{r['alt_name']}** &mdash; {r['region']}")
                            if c_a2.button(f"Aplicar EPSG:{r['alt_code']}", key=f"btn_apply_alt_{r['alt_code']}", use_container_width=True):
                                st.session_state["pending_epsg_code"] = r["alt_code"]
                                st.rerun()

    # ----------------------------------------------------------------------------------
    # VISOR CARTOGRÁFICO INTERACTIVO Y HERRAMIENTA DE TRAZADO
    # ----------------------------------------------------------------------------------
    st.markdown("---")
    col_map_h, col_map_btn = st.columns([3, 1])
    with col_map_h:
        st.markdown(f"### 🗺️ Visor Cartográfico y Trazado de Áreas ({service_info['badge']})")
        st.caption(
            "Verifica la ubicación de tus geometrías CAD/KML (**contorno sólido**) y el **recuadro de la imagen TIF de salida** (**línea discontinua** con buffer). "
            "Para trazar una nueva parcela directamente en el mapa, usa las herramientas de **polígono o rectángulo** en la barra superior izquierda (✏️)."
        )
    with col_map_btn:
        st.write("")
        if st.session_state.get("persisted_drawings"):
            if st.button("🗑️ Limpiar dibujos del mapa", use_container_width=True, help="Elimina los polígonos dibujados manualmente"):
                st.session_state["persisted_drawings"] = []
                st.session_state["draw_version"] = st.session_state.get("draw_version", 0) + 1
                st.session_state["processed_zip_data"] = None
                st.rerun()

    draw_ver = st.session_state.get("draw_version", 0)
    preview_map = generate_preview_map(
        polygons=extracted_polygons if extracted_polygons else None,
        crs_str=crs_str,
        buffer_pct=buffer_pct,
        active_service_key=selected_service_key,
        custom_wms_url=wms_url if selected_service_key == "custom" else "",
        custom_wms_layer=wms_layer if selected_service_key == "custom" else "",
        custom_wms_tag=wms_tag if selected_service_key == "custom" else "custom",
        enable_draw=True
    )

    if preview_map is not None:
        map_output = st_folium(
            preview_map,
            use_container_width=True,
            height=480,
            returned_objects=["all_drawings", "last_active_drawing"],
            key=f"cad_map_v{draw_ver}"
        )

        if map_output and map_output.get("all_drawings"):
            leaflet_drawings = map_output.get("all_drawings")
            saved_drawings = list(st.session_state.get("persisted_drawings", []))
            saved_signatures = {
                json.dumps(f.get("geometry", {}).get("coordinates", [])) for f in saved_drawings
            }
            any_added = False
            for feat in leaflet_drawings:
                coords = feat.get("geometry", {}).get("coordinates", [])
                sig = json.dumps(coords)
                if sig not in saved_signatures:
                    saved_drawings.append(feat)
                    saved_signatures.add(sig)
                    any_added = True
            if any_added:
                st.session_state["persisted_drawings"] = saved_drawings
                st.session_state["draw_only_mode"] = True
                st.rerun()
    else:
        st.info("ℹ️ No fue posible proyectar las geometrías sobre el mapa. Comprueba que el CRS coincida con las coordenadas del plano.")

    # ----------------------------------------------------------------------------------
    # TABLA DE PERSONALIZACIÓN Y RESOLUCIÓN
    # ----------------------------------------------------------------------------------
    if not extracted_polygons:
        st.info(
            "👆 **¿Cómo empezar?** Puedes:\n"
            "- Cargar un archivo **AutoCAD (.dxf)** con polilíneas cerradas.\n"
            "- Cargar un archivo **Google Earth (.kml / .kmz)** con parcelas o polígonos.\n"
            "- O trazar directamente una parcela en el visor usando la herramienta de **polígono o rectángulo** en la barra superior izquierda del mapa (✏️)."
        )
    else:
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        layers_found = list(set(p["capa"] for p in extracted_polygons))
        col_m1.metric("Polígonos detectados", len(extracted_polygons))
        col_m2.metric("Capas / Orígenes", len(layers_found))
        col_m3.metric("Proyección activa", crs_str)
        col_m4.metric("Servicio activo", service_info["badge"])

        # Inicializar y sincronizar el estado de la tabla
        state_key = f"df_{dxf_display_name}_{len(extracted_polygons)}_{crs_str}_{wms_tag}"
        if state_key not in st.session_state:
            table_data = []
            for p in extracted_polygons:
                row_copy = dict(p)
                row_copy.pop("pts", None)
                table_data.append(row_copy)
            st.session_state[state_key] = pd.DataFrame(table_data)

        active_df = st.session_state[state_key]

        st.markdown("---")
        st.markdown("### 📋 Personalización de Polígonos y Recomendación de Calidad")

        with st.expander("💡 Guía de Calidad Recomendada de Imagen según el Tamaño del Área", expanded=False):
            st.markdown("""
            La aplicación analiza el área ($m^2$ y hectáreas) de cada polígono CAD y asigna automáticamente la resolución óptima recomendada para obtener el máximo nivel de detalle sin sobrecargar la memoria ni exceder los límites de descarga del IGN:
            
            | Superficie de la Geometría | Nivel de Calidad | Resolución Sugerida ($m/px$) | Tipo de Proyecto / Uso Habitual |
            | :--- | :--- | :--- | :--- |
            | **< 5.000 m²** (< 0.5 ha) | 🌟 **Muy Alta** | `0.25 m/px` | Solares urbanos, parcelas pequeñas, edificación y detalle fino |
            | **5.000 a 25.000 m²** (0.5 a 2.5 ha) | 🔍 **Alta** | `0.50 m/px` | Parcelas y naves industriales, urbanizaciones compactas |
            | **25.000 a 150.000 m²** (2.5 a 15 ha) | 📐 **Estándar** | `1.00 m/px` | Obras lineales medianas, polígonos, desarrollos urbanísticos |
            | **150.000 a 1.000.000 m²** (15 a 100 ha) | 🚜 **Normal** | `2.00 m/px` | Grandes fincas rústicas, parques solares, infraestructuras |
            | **> 1.000.000 m²** (> 100 ha) | 🗺️ **Panorámica** | `4.00 m/px` | Escala territorial, términos municipales, cuencas |
            
            *Nota: Cada fila ha sido inicializada automáticamente con la resolución recomendada. Puedes ajustar los valores a tu gusto de manera individual o por lotes.*
            """)

        # 1. Ajuste rápido de resolución por lote
        r1, r2, r3 = st.columns([2.0, 1.3, 1.3])
        with r1:
            preset_res = st.selectbox(
                "Resolución rápida sugerida:",
                options=[
                    "Mantener selección individual",
                    "🪄 Recomendada según área (Auto)",
                    "0.25 m/px - Muy Alta (< 0.5 ha)",
                    "0.50 m/px - Alta (0.5 a 2.5 ha)",
                    "1.00 m/px - Estándar (2.5 a 15 ha)",
                    "2.00 m/px - Normal (15 a 100 ha)",
                    "4.00 m/px - Panorámica (> 100 ha)"
                ],
                index=0
            )

        with r2:
            st.write("")
            st.write("")
            btn_apply_all = st.button("📏 Aplicar a todos", use_container_width=True)

        with r3:
            st.write("")
            st.write("")
            btn_apply_rec = st.button("🪄 Calidad sugerida", use_container_width=True, help="Restaura la resolución recomendada según el área en m² de cada polígono")

        # 2. Barra de selección rápida de polígonos
        total_polys = len(active_df)
        selected_count = int(active_df["incluir"].sum()) if "incluir" in active_df.columns else 0

        s1, s2, s3, s4 = st.columns([2.0, 1.2, 1.2, 1.0])
        with s1:
            st.markdown(
                f"<div style='padding-top: 6px; font-weight: 600; font-size: 13.5px; color: #38bdf8;'>"
                f"📍 <b>{selected_count}</b> de <b>{total_polys}</b> polígono(s) marcado(s)"
                f"</div>",
                unsafe_allow_html=True
            )
        with s2:
            btn_select_all = st.button("✅ Seleccionar todo", use_container_width=True, help="Marca todos los polígonos de la tabla")
        with s3:
            btn_deselect_all = st.button("⬜ Deseleccionar todo", use_container_width=True, help="Desmarca todos los polígonos de la tabla")
        with s4:
            btn_invert_sel = st.button("🔄 Invertir", use_container_width=True, help="Invierte la selección actual de polígonos")

        editor_ver = st.session_state.get(f"ver_{state_key}", 0)

        if btn_select_all:
            active_df["incluir"] = True
            st.session_state[state_key] = active_df
            st.session_state[f"ver_{state_key}"] = editor_ver + 1
            st.rerun()

        if btn_deselect_all:
            active_df["incluir"] = False
            st.session_state[state_key] = active_df
            st.session_state[f"ver_{state_key}"] = editor_ver + 1
            st.rerun()

        if btn_invert_sel:
            active_df["incluir"] = ~active_df["incluir"].astype(bool)
            st.session_state[state_key] = active_df
            st.session_state[f"ver_{state_key}"] = editor_ver + 1
            st.rerun()

        if btn_apply_rec:
            for idx, row in active_df.iterrows():
                rec_res, rec_label, _ = get_recommended_resolution(float(row.get("area_m2", 0)))
                active_df.at[idx, "resolucion_m_px"] = rec_res
                active_df.at[idx, "calidad_sugerida"] = rec_label
            st.session_state[state_key] = active_df
            st.session_state[f"ver_{state_key}"] = editor_ver + 1
            st.rerun()

        if btn_apply_all and preset_res != "Mantener selección individual":
            if "Recomendada" in preset_res:
                for idx, row in active_df.iterrows():
                    rec_res, rec_label, _ = get_recommended_resolution(float(row.get("area_m2", 0)))
                    active_df.at[idx, "resolucion_m_px"] = rec_res
                    active_df.at[idx, "calidad_sugerida"] = rec_label
            else:
                val = float(preset_res.split(" ")[0])
                active_df["resolucion_m_px"] = val
            st.session_state[state_key] = active_df
            st.session_state[f"ver_{state_key}"] = editor_ver + 1
            st.rerun()

        column_config = {
            "incluir": st.column_config.CheckboxColumn(
                "Descargar",
                help="Marcar para incluir en la descarga",
                default=True
            ),
            "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
            "capa": st.column_config.TextColumn("Capa / Nombre", disabled=True, width="medium"),
            "area_m2": st.column_config.NumberColumn(
                "Área (m²)",
                disabled=True,
                format="%.1f m²",
                help="Superficie total encerrada por el polígono"
            ),
            "calidad_sugerida": st.column_config.TextColumn(
                "Calidad Sugerida",
                help="Resolución recomendada por el sistema según el área de la geometría",
                disabled=True,
                width="medium"
            ),
            "resolucion_m_px": st.column_config.NumberColumn(
                "Resolución (m/px)",
                help="Tamaño de píxel en metros (Personalizable: Muy Alta 0.25, Alta 0.50, Estándar 1.00, Normal 2.00, Panorámica 4.00 o manual)",
                min_value=0.1,
                max_value=20.0,
                step=0.25,
                format="%.2f m/px",
                required=True,
                width="medium"
            ),
            "nombre_archivo": st.column_config.TextColumn(
                "Nombre Base Archivo",
                help="Nombre que recibirán los archivos .tif y .tfw",
                required=True,
                width="large"
            ),
            "ancho_m": st.column_config.NumberColumn("Ancho (m)", disabled=True, format="%.1f m"),
            "alto_m": st.column_config.NumberColumn("Alto (m)", disabled=True, format="%.1f m"),
            "num_vertices": st.column_config.NumberColumn("Vértices", disabled=True),
            "bounds": None
        }

        column_order = [
            "incluir", "id", "capa",
            "area_m2", "calidad_sugerida", "resolucion_m_px",
            "nombre_archivo", "ancho_m", "alto_m", "num_vertices"
        ]

        edited_df = st.data_editor(
            active_df,
            column_config=column_config,
            column_order=column_order,
            hide_index=True,
            use_container_width=True,
            num_rows="fixed",
            key=f"editor_{state_key}_{editor_ver}"
        )
        st.session_state[state_key] = edited_df

        selected_rows = edited_df[edited_df["incluir"] == True].to_dict("records")
        if len(selected_rows) == 0:
            st.warning("⚠️ No has seleccionado ningún polígono para descargar. Marca las casillas en la tabla o pulsa '✅ Seleccionar todo'.")
        else:
            st.info(f"📍 **{len(selected_rows)}** polígono(s) seleccionado(s) listos para descargar.")

        # ------------------------------------------------------------------------------
        # BOTÓN DE DESCARGA WMS / SATÉLITE
        # ------------------------------------------------------------------------------
        st.write("")
        btn_process = st.button(
            f"🚀 Descargar Cartografía ({service_info['badge']}) y Generar Georreferenciación",
            type="primary",
            use_container_width=True,
            disabled=(len(selected_rows) == 0)
        )

        if btn_process:
            if selected_service_key == "custom":
                if not wms_url.strip():
                    st.error("⚠️ Debes introducir la URL de tu servidor WMS en la barra lateral para continuar.")
                    st.stop()
                if not wms_layer.strip():
                    st.error("⚠️ Debes introducir el identificador técnico de la capa (Layer) en la barra lateral.")
                    st.stop()

            st.session_state["processed_zip_data"] = None
            st.session_state["processed_summary"] = []

            progress_bar = st.progress(0.0)
            status_text = st.empty()
            log_expander = st.expander("📝 Detalle del procesamiento en tiempo real", expanded=True)

            session = create_resilient_session(timeout=35)
            zip_buffer = io.BytesIO()

            success_count = 0
            summary_log = []
            used_names = set()
            total_count = len(selected_rows)

            base_dxf_stem = os.path.splitext(sanitize_filename(dxf_display_name))[0]
            if not base_dxf_stem:
                base_dxf_stem = "proyecto"

            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                # Si las geometrías fueron dibujadas en el mapa o provienen de KML/KMZ, exportar vector CAD complementario
                pts_map = {p["id"]: p.get("pts", []) for p in extracted_polygons}
                polys_for_dxf = []
                for r in selected_rows:
                    r_pts = pts_map.get(r["id"], [])
                    if r_pts:
                        polys_for_dxf.append({
                            "capa": r.get("capa", "0"),
                            "pts": r_pts
                        })

                if is_vector_exportable and polys_for_dxf:
                    try:
                        dxf_vector_bytes = export_polygons_to_dxf(polys_for_dxf)
                        zf.writestr(f"vector_{base_dxf_stem}.dxf", dxf_vector_bytes)
                        log_expander.info(f"📐 Archivo CAD vectorial incluido en el ZIP: `vector_{base_dxf_stem}.dxf` ({len(polys_for_dxf)} polígono(s) cerrados).")
                    except Exception as dxf_err:
                        log_expander.warning(f"⚠️ No se pudo generar vector DXF complementario: {dxf_err}")

                for idx, row in enumerate(selected_rows):
                    progress_bar.progress(idx / total_count)

                    clean_base = sanitize_filename(row["nombre_archivo"])
                    pixel_size = float(row["resolucion_m_px"])
                    bounds = row["bounds"]

                    # Determinar tareas de descarga (única o teselas)
                    if "mosaico" in large_area_mode.lower():
                        tile_jobs = compute_tiled_georeferencing(
                            bounds=bounds,
                            buffer_pct=buffer_pct,
                            pixel_size=pixel_size,
                            max_tile_side=4000
                        )
                    else:
                        single_job = compute_georeferencing_parameters(
                            bounds=bounds,
                            buffer_pct=buffer_pct,
                            pixel_size=pixel_size,
                            max_pixels_lado=max_pixels_lado,
                            max_pixels_totales=max_pixels_totales
                        )
                        tile_jobs = [single_job]

                    for job in tile_jobs:
                        suffix = job.get("tile_suffix", "")
                        final_name = f"{clean_base}{suffix}"
                        
                        counter = 1
                        while final_name in used_names:
                            final_name = f"{clean_base}{suffix}_{counter}"
                            counter += 1
                        used_names.add(final_name)

                        status_text.markdown(
                            f"⏳ **Descargando [{idx + 1}/{total_count}] ({service_info['badge']}):** `{final_name}.tif` "
                            f"({job['ancho_px']} × {job['alto_px']} px, res: {abs(job['pixel_x']):.2f} m/px)..."
                        )

                        try:
                            if service_info.get("type") == "xyz":
                                img_bytes = fetch_xyz_ortho(
                                    session=session,
                                    tile_url_template=service_info["url"],
                                    crs_str=crs_str,
                                    bbox_buf=job["bbox_buf"],
                                    ancho_px=job["ancho_px"],
                                    alto_px=job["alto_px"]
                                )
                            else:
                                img_bytes = fetch_wms_ortho(
                                    session=session,
                                    wms_url=wms_url,
                                    wms_layer=wms_layer,
                                    crs_str=crs_str,
                                    bbox_buf=job["bbox_buf"],
                                    ancho_px=job["ancho_px"],
                                    alto_px=job["alto_px"]
                                )

                            zf.writestr(f"{final_name}.tif", img_bytes)
                            zf.writestr(f"{final_name}.tfw", job["tfw_content"].encode("utf-8"))

                            size_kb = len(img_bytes) / 1024.0
                            scaled_note = " (ajustado al límite del IGN)" if job.get("scaled", False) else ""
                            log_expander.success(
                                f"✅ [{final_name}] Descargado ({job['ancho_px']} × {job['alto_px']} px, "
                                f"{size_kb:.1f} KB, res: {abs(job['pixel_x']):.3f} m/px){scaled_note}"
                            )

                            summary_log.append({
                                "Archivo": final_name,
                                "Servicio": service_info["badge"],
                                "Dimensiones (px)": f"{job['ancho_px']} × {job['alto_px']}",
                                "Extensión (m)": f"{job['width_m']:.1f} × {job['height_m']:.1f}",
                                "Resolución Real": f"{abs(job['pixel_x']):.3f} m/px",
                                "Estado": "Descargado",
                                "Detalle": f"{size_kb:.1f} KB"
                            })
                            success_count += 1

                        except Exception as err:
                            err_msg = str(err)
                            log_expander.error(f"❌ [{final_name}] Error: {err_msg}")
                            summary_log.append({
                                "Archivo": final_name,
                                "Servicio": service_info["badge"],
                                "Dimensiones (px)": f"{job['ancho_px']} × {job['alto_px']}",
                                "Extensión (m)": f"{job['width_m']:.1f} × {job['height_m']:.1f}",
                                "Resolución Real": "-",
                                "Estado": "Error",
                                "Detalle": err_msg
                            })

            progress_bar.progress(1.0)
            status_text.empty()

            if success_count > 0:
                zip_buffer.seek(0)
                st.session_state["processed_zip_data"] = zip_buffer.getvalue()
                st.session_state["processed_zip_name"] = f"cartografia_{wms_tag}_{base_dxf_stem}.zip"
                st.session_state["processed_summary"] = summary_log
                st.session_state["is_vector_exportable"] = is_vector_exportable
                st.balloons()
            else:
                st.error("No se pudo descargar ninguna imagen cartográfica. Verifica la conectividad con el servicio WMS y las coordenadas.")

    # ----------------------------------------------------------------------------------
    # ENTREGA DE RESULTADOS: BOTÓN DE DESCARGA FINAL
    # ----------------------------------------------------------------------------------
    if st.session_state.get("processed_zip_data") is not None:
        st.markdown("---")
        st.markdown("### 📦 Descarga de Resultados")

        c1, c2 = st.columns([2, 1])
        with c1:
            st.success(f"🎉 **¡Paquete de georreferenciación ({service_info['badge']}) generado exitosamente!**")
            st.markdown(
                f"El paquete ZIP contiene la cartografía **{service_info['name']}** en archivos **`.tif` + `.tfw`** listos para ser "
                "insertados en AutoCAD mediante `_MAPIINSERT` o `_IMAGEATTACH`."
            )
            if st.session_state.get("is_vector_exportable"):
                st.info(
                    "📐 **¡Incluye archivo CAD vectorial complementario!**\n\n"
                    "El archivo `.zip` incluye `vector_*.dxf` con las líneas de las parcelas proyectadas en las coordenadas oficiales de tu plano. "
                    "Puedes abrirlo directamente en AutoCAD o Civil 3D e insertar las ortofotos mediante `_MAPIINSERT` para una concordancia perfecta."
                )
            st.info(
                "💡 **Consejo para minutas o ámbitos en diagonal en AutoCAD:**\n\n"
                "Para recortar la imagen siguiendo la forma exacta de tu minuta en el dibujo, usa el comando nativo `_IMAGECLIP` (`DELIMIMG`) -> *Nuevo contorno* (`N`) -> *Seleccionar polilínea* (`S`) y selecciona tu polilínea. AutoCAD ocultará las esquinas sobrantes al instante manteniendo la georreferenciación perfecta."
            )
            st.download_button(
                label=f"📥 Descargar Paquete ZIP para AutoCAD ({service_info['badge']})",
                data=st.session_state["processed_zip_data"],
                file_name=st.session_state["processed_zip_name"],
                mime="application/zip",
                use_container_width=True
            )

        with c2:
            zip_bytes = len(st.session_state["processed_zip_data"])
            st.metric("Tamaño del archivo ZIP", format_file_size(zip_bytes))
            if zip_bytes < 5000:
                st.warning("⚠️ Tamaño muy reducido (< 5 KB): Comprueba que el CRS y las coordenadas del plano DXF coincidan con la cobertura geográfica del servidor WMS.")

        if st.session_state.get("processed_summary"):
            st.write("")
            st.markdown("#### 📑 Resumen de Archivos Generados")
            st.dataframe(pd.DataFrame(st.session_state["processed_summary"]), use_container_width=True, hide_index=True)

    # Pie de página
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #94a3b8; font-size: 0.85rem; padding: 1.5rem 0; border-top: 1px solid #334155; margin-top: 2rem;">
        <strong style="color: #38bdf8;">AutoCAD PNOA OrthoExtractor</strong> | Integración WMS INSPIRE del Instituto Geográfico Nacional (IGN España)<br>
        Herramienta de automatización SIG para topografía, ingeniería civil y arquitectura.
    </div>
    """, unsafe_allow_html=True)


# --------------------------------------------------------------------------------------
# PUNTO DE ENTRADA PRINCIPAL
# --------------------------------------------------------------------------------------
render_ui()
