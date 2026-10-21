










import json
import math
import re
import warnings
from pathlib import Path
import pandas as pd
import numpy as np
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Tuple

from .exceptions import ChartError, ErrorCode
from .stats_kernels import (
    sanitize_value, sanitize_series, safe_str_list, name_value_pairs,
    gauge_scale, sturges_bins, bin_labels, box_stats, waterfall_walk, pareto_stats, fmt_num,
)
from .template import (
    TOOLTIP_FORMATTER_AXIS,
    BUBBLE_SYMBOLSIZE_PLACEHOLDER,
    BUBBLE_TOOLTIP_PLACEHOLDER,
    ITEM_TOOLTIP_PLACEHOLDER,
    WATERFALL_TOOLTIP_PLACEHOLDER,
    LIQUID_LABEL_PLACEHOLDER,
    DATAZOOM_THRESHOLD,
    ESC_JS_FN,
)



_GEO_DIR = Path(__file__).resolve().parent.parent / 'assets'
_GEO_CACHE: Dict[str, Dict[str, Any]] = {}



_REGION_ALIASES = {
    '北京': '北京市', '北京市': '北京市',
    '天津': '天津市', '天津市': '天津市',
    '河北': '河北省', '河北省': '河北省',
    '山西': '山西省', '山西省': '山西省',
    '内蒙古': '内蒙古自治区', '内蒙古自治区': '内蒙古自治区',
    '辽宁': '辽宁省', '辽宁省': '辽宁省',
    '吉林': '吉林省', '吉林省': '吉林省',
    '黑龙江': '黑龙江省', '黑龙江省': '黑龙江省',
    '上海': '上海市', '上海市': '上海市',
    '江苏': '江苏省', '江苏省': '江苏省',
    '浙江': '浙江省', '浙江省': '浙江省',
    '安徽': '安徽省', '安徽省': '安徽省',
    '福建': '福建省', '福建省': '福建省',
    '江西': '江西省', '江西省': '江西省',
    '山东': '山东省', '山东省': '山东省',
    '河南': '河南省', '河南省': '河南省',
    '湖北': '湖北省', '湖北省': '湖北省',
    '湖南': '湖南省', '湖南省': '湖南省',
    '广东': '广东省', '广东省': '广东省',
    '广西': '广西壮族自治区', '广西壮族自治区': '广西壮族自治区',
    '海南': '海南省', '海南省': '海南省',
    '重庆': '重庆市', '重庆市': '重庆市',
    '四川': '四川省', '四川省': '四川省',
    '贵州': '贵州省', '贵州省': '贵州省',
    '云南': '云南省', '云南省': '云南省',
    '西藏': '西藏自治区', '西藏自治区': '西藏自治区',
    '陕西': '陕西省', '陕西省': '陕西省',
    '甘肃': '甘肃省', '甘肃省': '甘肃省',
    '青海': '青海省', '青海省': '青海省',
    '宁夏': '宁夏回族自治区', '宁夏回族自治区': '宁夏回族自治区',
    '新疆': '新疆维吾尔自治区', '新疆维吾尔自治区': '新疆维吾尔自治区',
    '台湾': '台湾省', '台湾省': '台湾省',
    '香港': '香港特别行政区', '香港特别行政区': '香港特别行政区',
    '澳门': '澳门特别行政区', '澳门特别行政区': '澳门特别行政区',
}





_BUILTIN_ALIASES: Dict[str, Dict[str, str]] = {
    'china': _REGION_ALIASES,
}


def load_builtin_geojson(name: str) -> Dict[str, Any]:

    if name not in _GEO_CACHE:
        geo_file = _GEO_DIR / f'{name}.json'
        if not geo_file.exists():
            raise ChartError(
                f"内置地图资源缺失（assets/{name}.json）",
                ErrorCode.CHART_GENERATION_ERROR,
                details={'suggestion': f'确认 assets/{name}.json 存在；'
                                       '或用 --geo-path 指向自备 GeoJSON 文件'},
            )
        try:
            _GEO_CACHE[name] = json.loads(geo_file.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as e:
            raise ChartError(
                f"地图 GeoJSON 解析失败: {e}",
                ErrorCode.CHART_GENERATION_ERROR,
                details={'suggestion': f'确认 assets/{name}.json 是合法的 GeoJSON'},
            )
    return _GEO_CACHE[name]


def load_china_geojson() -> Dict[str, Any]:

    return load_builtin_geojson('china')


def geojson_region_names(geojson: Dict[str, Any]) -> set:

    return {f['properties']['name'] for f in geojson.get('features', [])
            if f.get('properties', {}).get('name')}


def china_region_names() -> set:

    return geojson_region_names(load_china_geojson())


def resolve_region_name(name: Any, geo_names: Optional[set] = None,
                        aliases: Optional[Dict[str, str]] = None) -> Optional[str]:




    if name is None:
        return None
    n = str(name).strip()
    if not n:
        return None
    if geo_names is None:
        geo_names = china_region_names()
    if aliases is None:
        aliases = _REGION_ALIASES
    if n in geo_names:
        return n
    return aliases.get(n)


@dataclass
class GeoSource:

    map_name: str
    geojson: Dict[str, Any]
    aliases: Dict[str, str]
    source: str  


def resolve_geo(geo: Optional[str] = None, geo_path: Optional[str] = None) -> GeoSource:







    if geo_path:
        p = Path(geo_path)
        if not p.exists():
            raise ChartError(
                f"自备地图文件不存在: {geo_path}",
                ErrorCode.FILE_NOT_FOUND,
                details={'given': geo_path, 'suggestion': '确认 --geo-path 指向一个可读的 GeoJSON 文件'},
            )
        try:
            geojson = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as e:
            raise ChartError(
                f"自备地图 GeoJSON 解析失败: {e}",
                ErrorCode.CHART_GENERATION_ERROR,
                details={'given': geo_path, 'suggestion': '确认文件是合法的 GeoJSON'},
            )
        return GeoSource(map_name=p.stem, geojson=geojson, aliases={}, source=f'file:{geo_path}')

    name = (geo or 'china').strip()
    geojson = load_builtin_geojson(name)
    aliases = _BUILTIN_ALIASES.get(name, {})
    return GeoSource(map_name=name, geojson=geojson, aliases=aliases, source=f'builtin:{name}')


def _collect_coordinates(coords: Any) -> List[List[float]]:




    pts: List[List[float]] = []

    def _walk(x: Any) -> None:
        if not isinstance(x, (list, tuple)):
            return
        if len(x) >= 2 and isinstance(x[0], (int, float)) and isinstance(x[1], (int, float)):
            pts.append([float(x[0]), float(x[1])])
            return
        for item in x:
            _walk(item)

    _walk(coords)
    return pts


def region_centers(geojson: Dict[str, Any]) -> Dict[str, List[float]]:







    centers: Dict[str, List[float]] = {}
    for f in geojson.get('features', []):
        props = f.get('properties') or {}
        name = props.get('name')
        if not name:
            continue
        for key in ('cp', 'center', 'centroid'):
            val = props.get(key)
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                try:
                    centers[name] = [float(val[0]), float(val[1])]
                    break
                except (TypeError, ValueError):
                    continue
        if name in centers:
            continue
        
        geom = f.get('geometry') or {}
        pts = _collect_coordinates(geom.get('coordinates'))
        if pts:
            lngs = [c[0] for c in pts]
            lats = [c[1] for c in pts]
            centers[name] = [(min(lngs) + max(lngs)) / 2, (min(lats) + max(lats)) / 2]
    return centers


def _js_dumps(obj) -> str:






    return json.dumps(obj, ensure_ascii=False).replace('</', '<\\/')


def _labeled_points(df, x_col, num_cols, label_col=None, numeric_color_col=None, x_is_numeric=True):







    
    
    
    mask = df[x_col].notna().to_numpy().copy()
    for c in num_cols:
        mask &= df[c].notna().to_numpy()
    sub = df[mask]
    x_list = sub[x_col].tolist()
    num_lists = [sub[c].tolist() for c in num_cols]
    color_list = sub[numeric_color_col].tolist() if numeric_color_col is not None else None
    label_list = sub[label_col].tolist() if label_col is not None else None
    pts = []
    for i in range(len(sub)):
        xv = sanitize_value(float(x_list[i])) if x_is_numeric else str(x_list[i])
        vals = [xv] + [sanitize_value(float(v)) for v in (lst[i] for lst in num_lists)]
        if color_list is not None:
            cv = color_list[i]
            vals.append(sanitize_value(float(cv)) if pd.notna(cv) else None)
        pt = {'value': vals}
        if label_list is not None:
            lv = label_list[i]
            pt['name'] = '' if pd.isna(lv) else str(lv)
        pts.append(pt)
    return pts


def _point_tooltip_js(dim_names, has_label):

    label_line = "if (p.name) { s += '<b>' + esc(p.name) + '</b><br/>'; }" if has_label else ""
    return (
        "function(p) {\n"
        f"  var names = {_js_dumps(list(dim_names))};\n"
        "  " + ESC_JS_FN +
        "  var fmt = function(v) { return (typeof v === 'number') ? v.toLocaleString() : esc(v); };\n"
        "  var s = '';\n"
        f"  {label_line}\n"
        "  var vals = Array.isArray(p.value) ? p.value : [p.value];\n"
        "  for (var i = 0; i < names.length && i < vals.length; i++) {\n"
        "    s += esc(names[i]) + ': ' + fmt(vals[i]) + '<br/>';\n"
        "  }\n"
        "  return s;\n"
        "}"
    )


def _maybe_rotate_labels(x_data):

    if len(x_data) > 8 or (x_data and max(len(s) for s in x_data) > 6):
        return {'rotate': 30}
    return None


def _all_nonnegative(df: pd.DataFrame, cols: List[str]) -> bool:





    try:
        arr = df[cols].to_numpy(dtype='float64')
    except (ValueError, TypeError):
        return False
    finite = arr[np.isfinite(arr)]
    return bool(finite.size) and bool((finite >= 0).all())


def _key_label_data(vals: List[Any], top_n: int = 3) -> List[Dict[str, Any]]:





    finite = [(i, v) for i, v in enumerate(vals) if v is not None]
    show = set()
    if finite:
        ranked = sorted(finite, key=lambda iv: iv[1], reverse=True)
        show.update(i for i, _ in ranked[:top_n])
        show.add(ranked[0][0])   
        show.add(ranked[-1][0])  
    return [{'value': v, 'label': {'show': i in show}} for i, v in enumerate(vals)]


def _axis_name_graphics(theme, x_name=None, y_names=(), x_bottom=None, x_data_len=0,
                        threshold=DATAZOOM_THRESHOLD):










    fill = theme['graphic_text']
    if x_bottom is None:
        x_bottom = 64 if (x_data_len and x_data_len > threshold) else 42
    graphics = []
    if x_name:
        graphics.append({'id': 'axisName-x', 'type': 'text', 'draggable': True, 'cursor': 'move',
                         'left': 'center', 'bottom': x_bottom,
                         'style': {'text': x_name, 'fontSize': 12, 'fill': fill}})
    for i, name in enumerate(y_names):
        pos = {'left': '6%', 'top': 38} if i == 0 else {'right': '6%', 'top': 38}
        graphics.append({'id': f'axisName-y{i}', 'type': 'text', 'draggable': True, 'cursor': 'move',
                         **pos, 'style': {'text': name, 'fontSize': 12, 'fill': fill}})
    return graphics


@dataclass
class RenderContext:





















    df: pd.DataFrame
    x: Optional[str]
    y: List[str]
    title: str
    texts: Dict[str, str]
    theme: Dict[str, Any]
    lang: str
    label_col: Optional[str] = None
    color_by: Optional[str] = None
    y_scale: bool = False
    sort: str = 'none'
    label_mode: str = 'auto'
    subtitle: Optional[str] = None
    width: int = 900
    height: int = 560
    x_name: Optional[str] = None
    y_names: Optional[List[str]] = None
    series_names: Optional[List[str]] = None
    target: Optional[float] = None
    
    
    
    geo_map_name: str = 'china'
    geo_json: Optional[Dict[str, Any]] = None
    geo_aliases: Dict[str, str] = field(default_factory=dict)
    geo_names: Optional[set] = None
    js: Dict[str, str] = field(default_factory=dict)


class ChartRenderersMixin:





    def _base(self, ctx: RenderContext, x_data_len=0, y_data_len=0):
        theme = ctx.theme
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'axis', 'formatter': TOOLTIP_FORMATTER_AXIS},
            'legend': {'top': 'bottom', 'type': 'scroll'},  
            'grid': {'left': '3%', 'right': '4%', 'bottom': '12%', 'containLabel': True},
            
            'color': list(theme['palette']),
        }
        
        zooms = []
        if x_data_len and x_data_len > DATAZOOM_THRESHOLD:
            zooms.append({'type': 'inside', 'start': 0, 'end': 100})
            zooms.append({'type': 'slider', 'start': 0, 'end': 100, 'height': 20, 'bottom': 8})
            opt['grid']['bottom'] = '20%'
        if y_data_len and y_data_len > DATAZOOM_THRESHOLD:
            zooms.append({'type': 'inside', 'orient': 'vertical', 'start': 0, 'end': 100})
            zooms.append({'type': 'slider', 'orient': 'vertical', 'start': 0, 'end': 100, 'width': 16, 'right': 4})
            opt['grid']['right'] = '8%'
        if zooms:
            opt['dataZoom'] = zooms
            
            opt['legend'] = {'bottom': 30, 'type': 'scroll'}
        return opt

    def _line(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        x_data = safe_str_list(df[x])
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['xAxis'] = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        
        
        if ctx.y_scale:
            opt['yAxis']['scale'] = True
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, y, x_data_len=len(x_data))
        opt['series'] = [
            {'name': col, 'type': 'line', 'smooth': True, 'data': sanitize_series(df[col].tolist())}
            for col in y
        ]
        return opt

    def _bar(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        
        
        if ctx.sort == 'value' and y and pd.api.types.is_numeric_dtype(df[y[0]]):
            df = df.sort_values(y[0], ascending=False, na_position='last')
        x_data = safe_str_list(df[x])
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['xAxis'] = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        
        
        if _all_nonnegative(df, y):
            opt['yAxis']['min'] = 0
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, y, x_data_len=len(x_data))
        opt['series'] = [
            {'name': col, 'type': 'bar', 'data': sanitize_series(df[col].tolist())}
            for col in y
        ]
        if len(y) == 1:
            
            
            key_mode = (ctx.label_mode == 'key'
                        or (ctx.label_mode == 'auto' and len(x_data) > 20))
            if key_mode:
                opt['series'][0]['data'] = _key_label_data(opt['series'][0]['data'])
            opt['series'][0]['label'] = {'show': True, 'position': 'top'}
        return opt

    def _pie(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item', 'formatter': '{a} <br/>{b}: {c} ({d}%)'}
        
        y_col = y[0] if y else df.columns[-1]
        if not pd.api.types.is_numeric_dtype(df[y_col]):
            
            counts = df[x].astype(str).value_counts()
            data = [{'name': str(k), 'value': sanitize_value(float(v))} for k, v in counts.items()]
            y_col = ctx.texts['axis_frequency']
        else:
            data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        
        
        series_name = (ctx.series_names[0] if ctx.series_names else y_col)
        opt['series'] = [{
            'name': series_name, 'type': 'pie', 'radius': ['40%', '70%'], 'data': data,
            'label': {'show': True, 'formatter': '{b}: {c} ({d}%)'},
            'emphasis': {'itemStyle': {'shadowBlur': 10, 'shadowColor': 'rgba(0,0,0,0.5)'}},
        }]
        return opt

    def _scatter(self, ctx: RenderContext):






        df, x, y = ctx.df, ctx.x, ctx.y
        label_col, color_col = ctx.label_col, ctx.color_by
        y_col = y[0] if y else df.columns[-1]
        x_is_numeric = pd.api.types.is_numeric_dtype(df[x])
        numeric_color = color_col is not None and pd.api.types.is_numeric_dtype(df[color_col])

        if x_is_numeric:
            opt = self._base(ctx)
            opt['xAxis'] = {'type': 'value', 'scale': True}
            x_data_len = 0
        else:
            x_data = safe_str_list(df[x])
            x_data_len = len(x_data)
            opt = self._base(ctx, x_data_len=x_data_len)
            opt['xAxis'] = {'type': 'category', 'data': x_data}
        opt['yAxis'] = {'type': 'value', 'scale': True}
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col], x_data_len=x_data_len)

        
        x_disp = ctx.x_name if ctx.x_name else x
        y_disp = (ctx.y_names[0] if ctx.y_names else y_col)
        dims = [x_disp, y_disp] + ([color_col] if numeric_color else [])
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = _point_tooltip_js(dims, has_label=label_col is not None)
        opt['tooltip'] = {'trigger': 'item', 'formatter': ITEM_TOOLTIP_PLACEHOLDER}

        if color_col is not None and not numeric_color:
            
            color_s = df[color_col].where(df[color_col].notna(), ctx.texts['series_uncategorized']).astype(str)
            opt['series'] = [
                {'name': cat, 'type': 'scatter', 'symbolSize': 10,
                 'data': _labeled_points(df[color_s == cat], x, [y_col], label_col, None, x_is_numeric)}
                for cat in color_s.unique()
            ]
        else:
            data = _labeled_points(df, x, [y_col], label_col,
                                   color_col if numeric_color else None, x_is_numeric)
            opt['series'] = [{'name': y_col, 'type': 'scatter', 'data': data, 'symbolSize': 10}]
            if numeric_color:
                cvals = [p['value'][2] for p in data if p['value'][2] is not None]
                if cvals:
                    opt['visualMap'] = {'min': min(cvals), 'max': max(cvals), 'dimension': 2,
                                        'calculable': True, 'orient': 'vertical', 'right': '1%', 'top': 'center'}
                    opt['grid']['right'] = '10%'  
        return opt

    def _area(self, ctx: RenderContext):
        
        
        opt = self._line(replace(ctx, y_scale=False))
        for s in opt['series']:
            s['areaStyle'] = {'opacity': 0.5}
        return opt

    def _radar(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item'}
        
        
        
        
        
        
        
        arr = df[y].to_numpy(dtype='float64')
        with warnings.catch_warnings():
            
            warnings.simplefilter('ignore', RuntimeWarning)
            if arr.shape[1] <= 1:
                try:
                    gm = float(np.nanmax(arr)) * 1.2
                except ValueError:  
                    gm = float('nan')
                row_max = np.full(len(df), gm if (np.isfinite(gm) and gm > 0) else 100.0)
            else:
                row_max = np.nanmax(arr, axis=1) * 1.2
        indicator = []
        for n, m in zip(safe_str_list(df[x]), row_max):
            mv = sanitize_value(float(m))
            indicator.append({'name': n, 'max': mv if mv is not None else 100})
        opt['radar'] = {'indicator': indicator, 'shape': 'polygon'}
        
        
        
        
        
        opt['series'] = []
        for i, c in enumerate(y):
            sname = (ctx.series_names[i] if ctx.series_names and i < len(ctx.series_names) else str(c))
            opt['series'].append({
                'name': sname,
                'type': 'radar',
                'data': [{
                    'name': sname,
                    'value': [0 if pd.isna(v) else sanitize_value(v) for v in df[c].tolist()],
                }],
            })
        return opt

    def _heatmap(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        x_data = safe_str_list(df[x])
        y_data = y
        opt = self._base(ctx, x_data_len=len(y_data), y_data_len=len(x_data))
        
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            f"  var xs = {_js_dumps(y_data)};\n"
            f"  var ys = {_js_dumps(x_data)};\n"
            "  " + ESC_JS_FN +
            "  var fmt = function(v) { return (typeof v === 'number') ? v.toLocaleString() : esc(v); };\n"
            "  return esc(ys[p.value[1]]) + ' × ' + esc(xs[p.value[0]]) + ': ' + fmt(p.value[2]);\n"
            "}"
        )
        opt['tooltip'] = {'position': 'top', 'formatter': ITEM_TOOLTIP_PLACEHOLDER}
        
        arr = np.round(df[y_data].to_numpy(dtype='float64'), 2)
        
        matrix = [[j, i, (float(arr[i, j]) if np.isfinite(arr[i, j]) else None)]
                  for i in range(arr.shape[0]) for j in range(arr.shape[1])]
        finite = arr[np.isfinite(arr)]
        vmin = float(finite.min()) if finite.size else 0
        vmax = float(finite.max()) if finite.size else 100
        opt['xAxis'] = {'type': 'category', 'data': y_data, 'splitArea': {'show': True}}
        rot = _maybe_rotate_labels(y_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'category', 'data': x_data, 'splitArea': {'show': True}}
        
        opt.pop('legend', None)
        
        
        
        grad = ctx.theme['diverging'] if vmin < 0 else ctx.theme['sequential']
        opt['visualMap'] = {'min': vmin, 'max': vmax, 'calculable': True,
                            'orient': 'vertical', 'left': '1%', 'bottom': '10%',
                            'inRange': {'color': list(grad)}}
        opt['grid']['left'] = '10%'  
        opt['series'] = [{'name': ctx.texts['series_heatmap'], 'type': 'heatmap', 'data': matrix, 'label': {'show': True}}]
        return opt

    def _treemap(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item'}
        
        opt.pop('legend', None)
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        opt['series'] = [{'name': ctx.texts['series_treemap'], 'type': 'treemap', 'data': data, 'roam': False, 'breadcrumb': {'show': True}}]
        return opt

    def _graph(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        
        
        source_col = x
        target_col = y[0] if y else None
        weight_col = y[1] if y and len(y) > 1 else None
        if not (source_col and target_col) or source_col not in df.columns or target_col not in df.columns:
            raise ChartError(
                "关系图需要 来源列(x) + 去向列(y) 两列（可选 权重列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'available': list(df.columns),
                         'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<权重列>] 显式指定'},
            )

        node_names = dict.fromkeys(safe_str_list(df[source_col]) + safe_str_list(df[target_col]))
        nodes = [{'name': n} for n in node_names]
        src_list = df[source_col].tolist()
        tgt_list = df[target_col].tolist()
        has_weight = weight_col and weight_col in df.columns
        w_list = df[weight_col].tolist() if has_weight else None
        links = []
        for i in range(len(src_list)):
            link = {'source': str(src_list[i]), 'target': str(tgt_list[i])}
            if has_weight:
                w = sanitize_value(float(w_list[i]))
                if w is not None:
                    link['value'] = w
            links.append(link)

        opt['tooltip'] = {'trigger': 'item'}
        
        opt.pop('legend', None)
        opt['series'] = [{'name': ctx.texts['series_graph'], 'type': 'graph', 'layout': 'force', 'data': nodes, 'links': links,
                          'roam': True, 'label': {'show': True}, 'force': {'repulsion': 200, 'edgeLength': [50, 150]}}]
        return opt

    def _boxplot(self, ctx: RenderContext):
        df, y = ctx.df, ctx.y
        opt = self._base(ctx)
        opt['tooltip'] = {'trigger': 'item', 'axisPointer': {'type': 'shadow'}}
        cols = y if len(y) > 0 else df.select_dtypes(include=[np.number]).columns[:5].tolist()
        box_data = []
        outlier_data = []  
        for cat_idx, col in enumerate(cols):
            s = df[col].dropna()
            if s.empty:
                box_data.append([0, 0, 0, 0, 0])
                continue
            
            st = box_stats(s)
            box_data.append([st['min'], st['q1'], st['median'], st['q3'], st['max']])
            
            for idx, val in st['outliers'].items():
                pt = {'value': [cat_idx, sanitize_value(float(val))]}
                if ctx.label_col is not None:
                    lv = df.loc[idx, ctx.label_col]
                    pt['name'] = '' if pd.isna(lv) else str(lv)
                outlier_data.append(pt)
        opt['xAxis'] = {'type': 'category', 'data': cols, 'boundaryGap': True}
        rot = _maybe_rotate_labels(cols)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            f"  var cols = {_js_dumps(cols)};\n"
            "  " + ESC_JS_FN +
            "  var s = p.name ? '<b>' + esc(p.name) + '</b><br/>' : '';\n"
            "  return s + esc(cols[p.value[0]]) + ': ' + p.value[1];\n"
            "}"
        )
        opt['series'] = [
            {'name': ctx.texts['series_boxplot'], 'type': 'boxplot', 'data': box_data},
            {'name': ctx.texts['series_outliers'], 'type': 'scatter', 'data': outlier_data, 'symbolSize': 8,
             'tooltip': {'formatter': ITEM_TOOLTIP_PLACEHOLDER}},
        ]
        return opt

    def _waterfall(self, ctx: RenderContext):







        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        x_data = safe_str_list(df[x])
        base, heights, signeds, _stats = waterfall_walk(df[y_col].tolist())
        bars = [{'value': h, 'label': {'formatter': s}} for h, s in zip(heights, signeds)]
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['xAxis'] = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col], x_data_len=len(x_data))
        
        opt['legend'] = {'top': 'bottom', 'type': 'scroll', 'data': [y_col]}
        ctx.js[WATERFALL_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            "  " + ESC_JS_FN +
            "  var v = (p.data && p.data.label) ? p.data.label.formatter : p.value;\n"
            f"  return '<b>' + esc(p.name) + '</b><br/>' + esc(p.seriesName) + ': ' + v;\n"
            "}"
        )
        opt['tooltip'] = {'trigger': 'item', 'formatter': WATERFALL_TOOLTIP_PLACEHOLDER}
        opt['series'] = [
            {'name': '__waterfall_base__', 'type': 'bar', 'stack': 'waterfall', 'silent': True,
             'itemStyle': {'color': 'transparent'}, 'emphasis': {'itemStyle': {'color': 'transparent'}},
             'tooltip': {'show': False}, 'data': base},
            {'name': y_col, 'type': 'bar', 'stack': 'waterfall', 'data': bars,
             'label': {'show': True, 'position': 'top'}, 'itemStyle': {'color': ctx.theme['primary']}},
        ]
        return opt

    def _gauge(self, ctx: RenderContext):
        df, y = ctx.df, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "仪表盘需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列，或用 transform_code 生成数值列'},
            )
        value = sanitize_value(float(df[y_col].mean()))
        if value is None:
            value = 0
        
        
        
        if ctx.target:
            max_val = sanitize_value(float(ctx.target))
        else:
            max_val = sanitize_value(gauge_scale(float(df[y_col].max())))
        if max_val is None:
            max_val = 100
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        stops = ctx.theme['gauge_stops']
        
        
        series_name = (ctx.series_names[0] if ctx.series_names else y_col)
        opt['series'] = [{'name': series_name, 'type': 'gauge', 'max': max_val,
                          'detail': {'formatter': '{value}'},
                          'data': [{'value': value, 'name': series_name}],
                          'axisLine': {'lineStyle': {'width': 10, 'color': [[0.3, stops[0]], [0.7, stops[1]], [1, stops[2]]]}}}]
        return opt

    def _sankey(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        
        source_col = x
        target_col = y[0] if y else None
        value_col = y[1] if y and len(y) > 1 else None
        if not (source_col and target_col) or source_col not in df.columns or target_col not in df.columns:
            raise ChartError(
                "桑基图需要 来源列(x) + 去向列(y) 两列（可选 值列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'available': list(df.columns),
                         'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<值列>] 显式指定'},
            )

        nodes, links = [], []
        node_names = dict.fromkeys(safe_str_list(df[source_col]) + safe_str_list(df[target_col]))
        nodes = [{'name': n} for n in node_names]
        src_list = df[source_col].tolist()
        tgt_list = df[target_col].tolist()
        has_value = value_col and value_col in df.columns
        v_list = df[value_col].tolist() if has_value else None
        for i in range(len(src_list)):
            val = 1
            if has_value:
                v = sanitize_value(float(v_list[i]))
                val = v if v is not None else 1
            links.append({'source': str(src_list[i]), 'target': str(tgt_list[i]), 'value': val})

        opt['tooltip'] = {'trigger': 'item'}
        opt['series'] = [{'name': ctx.texts['series_sankey'], 'type': 'sankey', 'data': nodes, 'links': links,
                          'emphasis': {'focus': 'adjacency'}, 'lineStyle': {'curveness': 0.5}}]
        return opt

    def _funnel(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        all_vals = [d['value'] for d in data if d['value'] is not None]
        max_val = max(all_vals) if all_vals else 100
        opt['series'] = [{'name': ctx.texts['series_funnel'], 'type': 'funnel', 'left': '10%', 'top': 60, 'bottom': 60, 'width': '80%',
                          'min': 0, 'max': max_val, 'sort': 'descending', 'gap': 2,
                          'label': {'show': True, 'position': 'inside'},
                          'data': data}]
        return opt

    def _sunburst(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        opt['series'] = [{'name': ctx.texts['series_sunburst'], 'type': 'sunburst', 'data': data, 'radius': [0, '90%'],
                          'label': {'rotate': 'radial'}}]
        return opt

    def _wordcloud(self, ctx: RenderContext):
        df, x, y = ctx.df, ctx.x, ctx.y
        opt = {'title': {'text': ctx.title, 'left': 'center'}, 'color': list(ctx.theme['palette'])}
        y_col = y[0] if y else df.columns[-1]
        data = name_value_pairs(df[x].tolist(), df[y_col].tolist())
        opt['series'] = [{'name': ctx.texts['series_wordcloud'], 'type': 'wordCloud', 'shape': 'circle',
                          'sizeRange': [12, 60], 'rotationRange': [-90, 90], 'rotationStep': 45,
                          'data': data}]
        return opt

    def _histogram(self, ctx: RenderContext):





        df, y = ctx.df, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "直方图需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列，或用 transform_code 生成数值列'},
            )
        s = df[y_col].dropna()
        if s.empty:
            raise ChartError(
                f"列 {y_col} 无有效数值，无法生成直方图",
                ErrorCode.DATA_EMPTY,
                details={'column': y_col, 'suggestion': '选择数值类型的列'},
            )
        counts, edges = sturges_bins(s)
        labels = bin_labels(edges, counts)
        opt = self._base(ctx, x_data_len=len(labels))
        opt['tooltip'] = {'trigger': 'item', 'formatter': '{b}<br/>{c}'}
        opt['xAxis'] = {'type': 'category', 'data': labels}
        rot = _maybe_rotate_labels(labels)
        if rot:
            opt['xAxis']['axisLabel'] = rot
        opt['yAxis'] = {'type': 'value'}
        
        
        opt['graphic'] = _axis_name_graphics(ctx.theme, y_col, [ctx.texts['axis_frequency']], x_data_len=len(labels))
        opt['series'] = [{
            'name': y_col, 'type': 'bar', 'data': counts.tolist(),
            'barCategoryGap': '0%',  
            'itemStyle': {'color': ctx.theme['primary']},
        }]
        return opt

    def _stacked_bar(self, ctx: RenderContext):

        opt = self._bar(ctx)
        for s in opt['series']:
            s['stack'] = 'total'
            s['emphasis'] = {'focus': 'series'}
        return opt

    def _bubble(self, ctx: RenderContext):

        df, x, y = ctx.df, ctx.x, ctx.y
        opt = self._base(ctx)
        if len(y) < 2:
            raise ChartError(
                "气泡图至少需要 2 个 Y 轴数值列（y 值 + size 值）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_y': y, 'suggestion': '提供 --y-axis <y_col> <size_col> 两个数值列'},
            )
        y_col, size_col = y[0], y[1]
        if not pd.api.types.is_numeric_dtype(df[x]):
            raise ChartError(
                f"气泡图的 X 轴需要数值列，当前列 '{x}' 不是数值类型",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_x': x, 'suggestion': '选择数值类型的 X 轴列，或用 transform_code 生成数值列'},
            )
        label_col, color_col = ctx.label_col, ctx.color_by
        numeric_color = color_col is not None and pd.api.types.is_numeric_dtype(df[color_col])
        max_size = float(df[size_col].max())
        if max_size <= 0 or np.isnan(max_size):
            max_size = 1.0
        opt['xAxis'] = {'type': 'value', 'scale': True}
        opt['yAxis'] = {'type': 'value', 'scale': True}
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col])
        
        
        
        
        x_disp = ctx.x_name if ctx.x_name else x
        y0_disp = (ctx.y_names[0] if ctx.y_names and len(ctx.y_names) > 0 else y_col)
        y1_disp = (ctx.y_names[1] if ctx.y_names and len(ctx.y_names) > 1 else size_col)
        dims = [x_disp, y0_disp, y1_disp] + ([color_col] if numeric_color else [])
        ctx.js[BUBBLE_TOOLTIP_PLACEHOLDER] = _point_tooltip_js(dims, has_label=label_col is not None)
        opt['tooltip'] = {'trigger': 'item', 'formatter': BUBBLE_TOOLTIP_PLACEHOLDER}
        ctx.js[BUBBLE_SYMBOLSIZE_PLACEHOLDER] = f'function(v){{ return Math.sqrt(v[2]/{max_size})*50+5; }}'

        def _series(sub):
            return {'type': 'scatter', 'symbolSize': BUBBLE_SYMBOLSIZE_PLACEHOLDER,
                    'data': _labeled_points(sub, x, [y_col, size_col], label_col,
                                            color_col if numeric_color else None, True)}

        if color_col is not None and not numeric_color:
            
            color_s = df[color_col].where(df[color_col].notna(), ctx.texts['series_uncategorized']).astype(str)
            opt['series'] = [dict(_series(df[color_s == cat]), name=cat) for cat in color_s.unique()]
        else:
            opt['series'] = [dict(_series(df), name=ctx.texts['series_bubble'])]
            if numeric_color:
                cvals = [p['value'][3] for p in opt['series'][0]['data'] if p['value'][3] is not None]
                if cvals:
                    opt['visualMap'] = {'min': min(cvals), 'max': max(cvals), 'dimension': 3,
                                        'calculable': True, 'orient': 'vertical', 'right': '1%', 'top': 'center'}
                    opt['grid']['right'] = '10%'  
        return opt

    def _pareto(self, ctx: RenderContext):




        df, x, y = ctx.df, ctx.x, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "帕累托图需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列，或用 transform_code 生成数值列'},
            )
        df_s = df[[x, y_col]].dropna().sort_values(y_col, ascending=False).reset_index(drop=True)
        x_data = safe_str_list(df_s[x])
        vals = sanitize_series(df_s[y_col].tolist())
        cum = pareto_stats(vals)['cum_pct']
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['tooltip'] = {'trigger': 'axis', 'formatter': TOOLTIP_FORMATTER_AXIS}
        x_axis = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            x_axis['axisLabel'] = rot
        opt['xAxis'] = [x_axis]
        opt['yAxis'] = [
            {'type': 'value', 'position': 'left'},
            {'type': 'value', 'max': 100, 'position': 'right',
             'axisLabel': {'formatter': '{value}%'}},
        ]
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [y_col, '%'], x_data_len=len(x_data))
        opt['series'] = [
            {'name': y_col, 'type': 'bar', 'data': vals, 'yAxisIndex': 0,
             'itemStyle': {'color': ctx.theme['primary']}},
            {'name': ctx.texts['series_pareto'], 'type': 'line', 'data': cum, 'yAxisIndex': 1,
             'lineStyle': {'color': ctx.theme['secondary']}, 'symbol': 'circle', 'symbolSize': 6},
        ]
        return opt

    def _combo(self, ctx: RenderContext):

        df, x, y = ctx.df, ctx.x, ctx.y
        if len(y) < 2:
            raise ChartError(
                "组合图至少需要 2 个 Y 轴列（bar 列 + line 列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_y': y, 'suggestion': '提供 --y-axis <bar_col> <line_col> [<line_col> ...]'},
            )
        x_data = safe_str_list(df[x])
        opt = self._base(ctx, x_data_len=len(x_data))
        opt['tooltip'] = {'trigger': 'axis', 'formatter': TOOLTIP_FORMATTER_AXIS}
        bar_col, line_cols = y[0], y[1:]
        x_axis = {'type': 'category', 'data': x_data}
        rot = _maybe_rotate_labels(x_data)
        if rot:
            x_axis['axisLabel'] = rot
        opt['xAxis'] = [x_axis]
        opt['yAxis'] = [
            {'type': 'value', 'position': 'left'},
            {'type': 'value', 'position': 'right',
             'axisLabel': {'formatter': '{value}'}},
        ]
        
        if _all_nonnegative(df, [bar_col]):
            opt['yAxis'][0]['min'] = 0
        opt['graphic'] = _axis_name_graphics(ctx.theme, x, [bar_col, ' / '.join(line_cols)], x_data_len=len(x_data))
        series = [{
            'name': bar_col, 'type': 'bar', 'data': sanitize_series(df[bar_col].tolist()),
            'yAxisIndex': 0, 'itemStyle': {'color': ctx.theme['primary']},
        }]
        line_colors = ctx.theme['palette'][1:5]
        for i, col in enumerate(line_cols):
            series.append({
                'name': col, 'type': 'line', 'data': sanitize_series(df[col].tolist()),
                'yAxisIndex': 1, 'smooth': True,
                'lineStyle': {'color': line_colors[i % len(line_colors)]},
            })
        opt['series'] = series
        return opt

    

    def _venn(self, ctx: RenderContext):





        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        if pd.api.types.is_numeric_dtype(df[y_col]):
            raw = {}
            for n, v in zip(safe_str_list(df[x]), df[y_col].tolist()):
                if n and pd.notna(v):
                    raw[n] = raw.get(n, 0.0) + float(v)
        else:
            raw = {str(k): float(c) for k, c in df[x].astype(str).value_counts().items()}
        sep_re = re.compile(r'[∩&+×]|与')
        
        sets: Dict[str, float] = {}
        compound: List[Tuple[str, float]] = []
        for name, v in raw.items():
            if sep_re.search(name):
                compound.append((name, v))
            else:
                sets[name] = v
        if len(sets) < 2:
            raise ChartError(
                "维恩图至少需要 2 个不含分隔符（∩ & + × 与）的独立集合行",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_sets': list(sets), 'suggestion': '每行一个集合（如 手机用户/电脑用户），交集行命名为 集合A∩集合B'},
            )
        if len(sets) > 3:
            raise ChartError(
                "维恩图最多支持 3 个集合",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_sets': list(sets), 'suggestion': '取最关注的 3 个集合，其余用 pie/treemap 呈现'},
            )
        names = list(sets)
        
        k = 150.0 / max(math.sqrt(v) for v in sets.values())
        radii = {n: k * math.sqrt(sets[n]) for n in names}
        
        
        
        CW, CH = float(ctx.width), float(ctx.height)
        OVERLAP = 0.72  
        centers = {}
        if len(names) == 2:
            a, b = names
            d = OVERLAP * (radii[a] + radii[b])
            centers[a] = (0.0, 0.0)
            centers[b] = (d, 0.0)
        else:
            
            
            a, b, c = names
            d_ab = OVERLAP * (radii[a] + radii[b])
            d_ac = OVERLAP * (radii[a] + radii[c])
            d_bc = OVERLAP * (radii[b] + radii[c])
            centers[a] = (0.0, 0.0)
            centers[b] = (d_ab, 0.0)
            x_c = (d_ab ** 2 + d_ac ** 2 - d_bc ** 2) / (2 * d_ab)
            h2 = d_ac ** 2 - x_c ** 2
            centers[c] = (x_c, -math.sqrt(h2) if h2 > 0 else 0.0)  
        
        min_x = min(centers[n][0] - radii[n] for n in names)
        max_x = max(centers[n][0] + radii[n] for n in names)
        min_y = min(centers[n][1] - radii[n] for n in names)
        max_y = max(centers[n][1] + radii[n] for n in names)
        margin_t, margin_b, side = 80.0, 40.0, 40.0
        scale = min((CW - 2 * side) / (max_x - min_x),
                    (CH - margin_t - margin_b) / (max_y - min_y), 1.0)
        ox = (CW - (max_x - min_x) * scale) / 2
        oy = margin_t + (CH - margin_t - margin_b - (max_y - min_y) * scale) / 2
        for n in names:
            centers[n] = (ox + (centers[n][0] - min_x) * scale,
                          oy + (centers[n][1] - min_y) * scale)
            radii[n] *= scale
        
        gx = sum(centers[n][0] for n in names) / len(names)
        gy = sum(centers[n][1] for n in names) / len(names)

        palette = ctx.theme['palette']
        graphics = []
        for i, n in enumerate(names):
            px, py = centers[n]
            graphics.append({
                'id': f'venn-set-{i}', 'type': 'circle',
                'shape': {'cx': round(px, 1), 'cy': round(py, 1), 'r': round(radii[n], 1)},
                'style': {'fill': palette[i % len(palette)], 'opacity': 0.55},
            })
        
        for i, n in enumerate(names):
            dx, dy = centers[n][0] - gx, centers[n][1] - gy
            dist = math.hypot(dx, dy) or 1.0
            lx, ly = centers[n][0] + dx / dist * radii[n] * 0.45, centers[n][1] + dy / dist * radii[n] * 0.45
            graphics.append({
                'id': f'venn-label-{i}', 'type': 'text',
                'left': round(lx), 'top': round(ly),
                'style': {'text': f'{n}\n{fmt_num(sets[n])}', 'fontSize': 14, 'fontWeight': 'bold',
                          'fill': ctx.theme['graphic_text'], 'align': 'center', 'verticalAlign': 'middle'},
            })
        
        
        for name, v in compound:
            parts = [p.strip() for p in sep_re.split(name) if p.strip()]
            members = []
            for p in parts:
                for n in names:
                    if n not in members and (p == n or p in n or n in p):
                        members.append(n)
                        break
            if len(members) < 2:
                continue
            if len(members) == 2:
                m1, m2 = members[0], members[1]
                x1, y1 = centers[m1]
                x2, y2 = centers[m2]
                d = math.hypot(x2 - x1, y2 - y1) or 1.0
                
                t = ((d - radii[m2]) + radii[m1]) / 2 / d
                t = max(0.2, min(0.8, t))
                mx, my = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            else:
                mx = sum(centers[m][0] for m in members) / len(members)
                my = sum(centers[m][1] for m in members) / len(members)
            graphics.append({
                'type': 'text', 'left': round(mx), 'top': round(my),
                'style': {'text': fmt_num(v), 'fontSize': 12,
                          'fill': ctx.theme['graphic_text'], 'align': 'center', 'verticalAlign': 'middle'},
            })
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'color': list(palette), 'series': [], 'graphic': graphics}
        return opt

    @staticmethod
    def _build_tree(edges):





        child_map: Dict[str, List[str]] = {}
        children_set = set()
        for p, c in edges:
            child_map.setdefault(p, []).append(c)
            children_set.add(c)
        roots = [p for p in child_map if p not in children_set]
        if not roots:
            raise ChartError(
                "层级数据存在循环引用，无法确定根节点",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '检查父/子列，确保至少存在一个只作父节点、从不作子节点的根'},
            )

        def build(name, seen):
            node = {'name': name}
            kids = []
            for c in child_map.get(name, []):
                if c in seen:  
                    continue
                kids.append(build(c, seen | {c}))
            if kids:
                node['children'] = kids
            return node

        return [build(r, {r}) for r in roots]

    def _mindmap(self, ctx: RenderContext):

        df, x, y = ctx.df, ctx.x, ctx.y
        parent_col, child_col = x, y[0]
        edges = [(p, c) for p, c in zip(safe_str_list(df[parent_col]), safe_str_list(df[child_col]))
                 if p and c]
        if not edges:
            raise ChartError(
                "思维导图需要有效的 父→子 边（父/子列均非空）",
                ErrorCode.DATA_EMPTY,
                details={'parent_col': parent_col, 'child_col': child_col},
            )
        roots = self._build_tree(edges)
        theme = ctx.theme
        palette = theme['palette']
        
        if len(roots) == 1:
            tree_data = roots[0]
        else:
            tree_data = {'name': '', 'children': roots,
                         'label': {'show': False}, 'lineStyle': {'width': 0}, 'itemStyle': {'color': 'transparent'}}

        def paint(node, color, is_root=False):
            node['itemStyle'] = {'color': color, 'borderColor': color}
            node['label'] = {'fontSize': 14 if is_root else 12,
                             'fontWeight': 'bold' if is_root else 'normal',
                             'color': theme['graphic_text'] or '#333'}
            node['symbolSize'] = 16 if is_root else 9
            for c in node.get('children', []):
                paint(c, color)
        
        top = tree_data.get('children', [])
        if tree_data.get('name') != '':
            paint(tree_data, theme['primary'], is_root=True)
            for i, c in enumerate(tree_data.get('children', [])):
                paint(c, palette[(i + 1) % len(palette)])
        else:
            for i, c in enumerate(top):
                paint(c, palette[i % len(palette)], is_root=True)
                for gc in c.get('children', []):
                    paint(gc, palette[i % len(palette)])
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'tooltip': {'trigger': 'item', 'triggerOn': 'mousemove'},
               'color': list(palette),
               'series': [{'name': ctx.texts['series_mindmap'], 'type': 'tree', 'data': [tree_data],
                           'orient': 'LR', 'left': '8%', 'right': '22%', 'top': '8%', 'bottom': '8%',
                           'symbol': 'circle', 'edgeShape': 'curve',
                           'lineStyle': {'width': 2, 'curveness': 0.5},
                           'label': {'position': 'right', 'distance': 5},
                           'leaves': {'label': {'position': 'right', 'distance': 5}},
                           'expandAndCollapse': False,
                           'initialTreeDepth': -1,
                           'animationDuration': 400}]}
        return opt

    def _orgchart(self, ctx: RenderContext):

        df, x, y = ctx.df, ctx.x, ctx.y
        parent_col, child_col = x, y[0]
        edges = [(p, c) for p, c in zip(safe_str_list(df[parent_col]), safe_str_list(df[child_col]))
                 if p and c]
        if not edges:
            raise ChartError(
                "组织架构图需要有效的 父→子 边（父/子列均非空）",
                ErrorCode.DATA_EMPTY,
                details={'parent_col': parent_col, 'child_col': child_col},
            )
        roots = self._build_tree(edges)
        primary = ctx.theme['primary']
        if len(roots) == 1:
            tree_data = roots[0]
        else:
            tree_data = {'name': '', 'children': roots,
                         'label': {'show': False}, 'lineStyle': {'width': 0},
                         'itemStyle': {'color': 'transparent', 'borderColor': 'transparent'}}

        def paint(node):
            node['symbol'] = 'rect'
            node['symbolSize'] = [72, 30]
            node['itemStyle'] = {'color': primary, 'borderColor': primary}
            node['label'] = {'position': 'inside', 'color': '#fff', 'fontSize': 12,
                             'overflow': 'truncate', 'width': 68}
            for c in node.get('children', []):
                paint(c)
        paint(tree_data)
        
        if tree_data.get('name') == '':
            tree_data['symbolSize'] = [0, 0]
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'tooltip': {'trigger': 'item', 'triggerOn': 'mousemove'},
               'color': [primary],
               'series': [{'name': ctx.texts['series_orgchart'], 'type': 'tree', 'data': [tree_data],
                           'orient': 'TB', 'left': '10%', 'right': '10%', 'top': '10%', 'bottom': '12%',
                           'edgeShape': 'polyline', 'lineStyle': {'width': 1.5},
                           'expandAndCollapse': False,
                           'initialTreeDepth': -1,
                           'animationDuration': 400}]}
        return opt

    def _liquid(self, ctx: RenderContext):







        df, y = ctx.df, ctx.y
        num_cols = df.select_dtypes(include=[np.number]).columns
        y_col = y[0] if y else (num_cols[0] if len(num_cols) else None)
        if y_col is None:
            raise ChartError(
                "水波图需要至少一个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供数值类型的列（如完成率），或用 transform_code 生成数值列'},
            )
        value = float(df[y_col].mean())
        
        
        denom = float(ctx.target) if ctx.target else gauge_scale(float(df[y_col].max()))
        frac = max(0.0, min(1.0, value / denom if denom else 0.0))
        pct = round(frac * 100, 1)
        waves = [round(frac, 4), round(frac * 0.9, 4), round(frac * 0.78, 4)]
        primary = ctx.theme['primary']
        
        
        series_name = (ctx.series_names[0] if ctx.series_names else y_col)
        
        
        ctx.js[LIQUID_LABEL_PLACEHOLDER] = (
            f"function() {{ return '{pct}%' + '\\n' + chartOption.series[0].name; }}"
        )
        opt = {'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
               'series': [{'name': series_name, 'type': 'liquidFill', 'data': waves,
                           'radius': '72%', 'center': ['50%', '52%'],
                           'color': [primary],
                           'backgroundStyle': {'color': ctx.theme['card_bg']},
                           'outline': {'show': True, 'borderDistance': 6,
                                       'itemStyle': {'borderWidth': 2, 'borderColor': primary}},
                           'label': {'fontSize': 34, 'fontWeight': 'bold',
                                     'color': primary, 'position': ['50%', '50%'],
                                     'formatter': LIQUID_LABEL_PLACEHOLDER},
                           'rippleEffect': {'period': 3000}}]}
        return opt

    

    def _map(self, ctx: RenderContext):







        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        geo_names = ctx.geo_names if ctx.geo_names is not None else geojson_region_names(ctx.geo_json or {})
        aliases = ctx.geo_aliases
        
        agg: Dict[str, float] = {}
        for n, v in zip(df[x].tolist(), df[y_col].tolist()):
            if pd.isna(v):
                continue
            full = resolve_region_name(n, geo_names, aliases)
            if full is None:
                continue
            try:
                agg[full] = agg.get(full, 0.0) + float(v)
            except (TypeError, ValueError):
                continue
        if not agg:
            raise ChartError(
                "地图数据为空：地区列无法与内置地图区域对齐",
                ErrorCode.DATA_EMPTY,
                details={'given_x': x,
                         'suggestion': '地区列使用地图区域全称（china 支持 北京/广东/新疆 等简称），'
                                       '或用 transform_code 归一化'},
            )
        data = [{'name': k, 'value': sanitize_value(v)} for k, v in agg.items()]
        vals = [d['value'] for d in data if d['value'] is not None]
        vmin = min(vals) if vals else 0
        vmax = max(vals) if vals else 100
        if vmin == vmax:  
            vmax = vmin + 1 if vmin is not None else 100
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'item', 'formatter': '{b}: {c}'},
            'color': list(ctx.theme['palette']),
            'visualMap': {'min': vmin, 'max': vmax, 'calculable': True, 'orient': 'vertical',
                          'left': '1%', 'bottom': '8%',
                          'inRange': {'color': list(ctx.theme['sequential'])}},
            'series': [{
                'name': ctx.texts['series_map'], 'type': 'map', 'map': ctx.geo_map_name,
                'roam': True, 'data': data,
                'label': {'show': False},
                'emphasis': {'label': {'show': True}, 'itemStyle': {'areaColor': ctx.theme['secondary']}},
            }],
        }
        return opt

    def _lines(self, ctx: RenderContext):






        df = ctx.df
        source_col = ctx.x
        target_col = ctx.y[0] if ctx.y else None
        value_col = ctx.y[1] if ctx.y and len(ctx.y) > 1 else None
        if not (source_col and target_col) or source_col not in df.columns or target_col not in df.columns:
            raise ChartError(
                "航线图需要 来源列(source) + 去向列(target)（可选 值列）",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'available': list(df.columns),
                         'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<值列>] 显式指定'},
            )
        geo_names = ctx.geo_names if ctx.geo_names is not None else geojson_region_names(ctx.geo_json or {})
        aliases = ctx.geo_aliases
        
        
        centers = region_centers(ctx.geo_json or {})
        data = []
        src_list = df[source_col].tolist()
        tgt_list = df[target_col].tolist()
        has_value = value_col and value_col in df.columns
        v_list = df[value_col].tolist() if has_value else None
        for i in range(len(src_list)):
            fs = resolve_region_name(src_list[i], geo_names, aliases)
            ft = resolve_region_name(tgt_list[i], geo_names, aliases)
            if fs is None or ft is None:
                continue
            c1 = centers.get(fs)
            c2 = centers.get(ft)
            if c1 is None or c2 is None:
                
                continue
            item = {'coords': [c1, c2], 'fromName': fs, 'toName': ft}
            if has_value:
                v = sanitize_value(float(v_list[i]))
                if v is not None:
                    item['value'] = v
            data.append(item)
        if not data:
            raise ChartError(
                "航线图数据为空：来源/去向列无法对齐到地图区域",
                ErrorCode.DATA_EMPTY,
                details={'suggestion': '来源/去向使用地图区域全称（china 支持 北京/广东 等简称）'},
            )
        ctx.js[ITEM_TOOLTIP_PLACEHOLDER] = (
            "function(p) {\n"
            "  var d = p.data || {};\n"
            "  return (d.fromName || '') + ' → ' + (d.toName || '')"
            " + (d.value != null ? ': ' + d.value : '');\n"
            "}"
        )
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'item', 'formatter': ITEM_TOOLTIP_PLACEHOLDER},
            'color': list(ctx.theme['palette']),
            'geo': {'map': ctx.geo_map_name, 'roam': True, 'label': {'show': False},
                    'itemStyle': {'areaColor': ctx.theme['card_bg']}},
            'series': [{
                'name': ctx.texts['series_lines'], 'type': 'lines', 'data': data,
                'effect': {'show': True, 'period': 4, 'trailLength': 0.3, 'symbol': 'arrow', 'symbolSize': 6},
                'lineStyle': {'width': 1.5, 'opacity': 0.6, 'curveness': 0.2},
            }],
        }
        return opt

    def _effect_scatter(self, ctx: RenderContext):

        opt = self._scatter(ctx)
        for s in opt.get('series', []):
            if s.get('type') == 'scatter':
                s['type'] = 'effectScatter'
                s.setdefault('rippleEffect', {'scale': 3.5, 'brushType': 'stroke'})
                s.setdefault('showEffectOn', 'render')
        return opt

    def _calendar(self, ctx: RenderContext):




        df, x, y = ctx.df, ctx.x, ctx.y
        y_col = y[0] if y else df.columns[-1]
        dates = pd.to_datetime(df[x], errors='coerce')
        mask = dates.notna() & df[y_col].notna()
        data = []
        for d, v in zip(dates[mask].tolist(), df[y_col][mask].tolist()):
            data.append([d.strftime('%Y-%m-%d'), sanitize_value(float(v))])
        if not data:
            raise ChartError(
                "日历热力图需要可解析为日期的 X 轴列，且至少一个有效数据点",
                ErrorCode.DATA_EMPTY,
                details={'given_x': x,
                         'suggestion': 'X 轴使用日期列（如 2024-01-01），或用 transform_code 生成日期列'},
            )
        vmin = min(v for _, v in data if v is not None)
        vmax = max(v for _, v in data if v is not None)
        if vmin == vmax:
            vmax = vmin + 1
        year = int(dates.dropna().min().year)
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'item'},
            'visualMap': {'min': vmin, 'max': vmax, 'calculable': True, 'orient': 'vertical',
                          'left': '1%', 'top': 'center',
                          'inRange': {'color': list(ctx.theme['sequential'])}},
            'calendar': {'top': 60, 'left': 60, 'right': 20, 'range': str(year),
                         'cellSize': ['auto', 16], 'yearLabel': {'show': True}},
            'series': [{
                'name': ctx.texts['series_calendar'], 'type': 'heatmap',
                'coordinateSystem': 'calendar', 'data': data,
            }],
        }
        return opt

    def _pictorial_bar(self, ctx: RenderContext):

        opt = self._bar(ctx)
        for s in opt.get('series', []):
            if s.get('type') == 'bar':
                s['type'] = 'pictorialBar'
                s['symbol'] = 'arrow'
                s['symbolRepeat'] = True
                s['symbolSize'] = [18, 8]
                s['symbolMargin'] = 3
                s['symbolClip'] = True
                s['symbolPosition'] = 'start'
        return opt

    def _theme_river(self, ctx: RenderContext):




        df, x, y = ctx.df, ctx.x, ctx.y
        if len(y) < 1:
            raise ChartError(
                "主题河流图至少需要 1 个数值列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'suggestion': '提供 --y-axis <数值列> [<数值列> ...]'},
            )
        dates = pd.to_datetime(df[x], errors='coerce')
        if dates.notna().sum() == 0:
            raise ChartError(
                "主题河流图需要可解析为时间/日期的 X 轴列",
                ErrorCode.CHART_CONFIG_ERROR,
                details={'given_x': x,
                         'suggestion': 'X 轴使用日期列（如 2024-01-01），或用 transform_code 生成日期列'},
            )
        data = []
        for i in range(len(df)):
            d = dates.iloc[i]
            if pd.isna(d):
                continue
            ds = d.strftime('%Y-%m-%d')
            for col in y:
                v = df[col].iloc[i]
                if pd.notna(v):
                    data.append([ds, sanitize_value(float(v)), col])
        if not data:
            raise ChartError("主题河流图无有效数据", ErrorCode.DATA_EMPTY)
        opt = {
            'title': {'text': ctx.title, 'left': 'center', 'textStyle': {'fontSize': 16}},
            'tooltip': {'trigger': 'axis', 'axisPointer': {'type': 'line', 'lineStyle': {'color': 'rgba(0,0,0,0.2)', 'width': 1}}},
            'singleAxis': {'type': 'time', 'boundaryGap': ['5%', '5%']},
            'series': [{
                'name': ctx.texts['series_theme_river'], 'type': 'themeRiver',
                'data': data, 'label': {'show': False},
                'emphasis': {'itemStyle': {'shadowBlur': 20, 'shadowColor': 'rgba(0,0,0,0.2)'}},
            }],
        }
        return opt
