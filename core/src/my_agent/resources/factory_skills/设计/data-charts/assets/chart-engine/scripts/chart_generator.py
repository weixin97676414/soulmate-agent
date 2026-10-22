









import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from enum import Enum

from .exceptions import ChartError, ErrorCode, SmartChartsError
from .renderers import ChartRenderersMixin, RenderContext, resolve_geo, geojson_region_names
from .template import HTMLTemplateMixin
from .texts import get_texts
from .plot_stats import compute_plot_stats, stats_spreadsheet
from .themes import THEMES
from .data_transformer import DataTransformer


class ChartType(Enum):
    LINE = 'line'
    BAR = 'bar'
    PIE = 'pie'
    SCATTER = 'scatter'
    AREA = 'area'
    RADAR = 'radar'
    HEATMAP = 'heatmap'
    TREEMAP = 'treemap'
    GRAPH = 'graph'
    BOXPLOT = 'boxplot'
    WATERFALL = 'waterfall'
    GAUGE = 'gauge'
    SANKEY = 'sankey'
    FUNNEL = 'funnel'
    SUNBURST = 'sunburst'
    WORDCLOUD = 'wordcloud'
    HISTOGRAM = 'histogram'
    STACKED_BAR = 'stacked_bar'
    BUBBLE = 'bubble'
    PARETO = 'pareto'
    COMBO = 'combo'
    VENN = 'venn'
    MINDMAP = 'mindmap'
    ORGCHART = 'orgchart'
    LIQUID = 'liquid'
    SPREADSHEET = 'spreadsheet'
    MAP = 'map'
    LINES = 'lines'
    EFFECT_SCATTER = 'effect_scatter'
    CALENDAR = 'calendar'
    PICTORIAL_BAR = 'pictorial_bar'
    THEME_RIVER = 'theme_river'






_AGG_REQUIRED_TYPES = frozenset({
    'line', 'bar', 'area', 'stacked_bar', 'combo', 'pareto', 'pictorial_bar', 'theme_river',
    'pie', 'treemap', 'funnel', 'sunburst', 'wordcloud', 'venn', 'map', 'waterfall', 'radar',
    'calendar',
})


class ChartGenerator(ChartRenderersMixin, HTMLTemplateMixin):


    def __init__(self, output_dir: str = './charts_output', theme: str = 'default'):
        if theme not in THEMES:
            raise ChartError(
                f"不支持的主题: {theme}",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'given': theme,
                    'supported': list(THEMES.keys()),
                    'suggestion': f"从 available 主题中选择: {', '.join(THEMES.keys())}",
                },
            )
        self.output_dir = Path(output_dir)
        self._theme = THEMES[theme]
        self._dir_ready = False

    def _ensure_output_dir(self):
        if not self._dir_ready:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._dir_ready = True

    def generate_chart(
        self,
        df: pd.DataFrame,
        chart_type: str,
        title: Optional[str] = None,
        x_axis: Optional[str] = None,
        y_axis: Optional[List[str]] = None,
        transform_code: Optional[str] = None,
        width: int = 900,
        height: int = 560,
        lang: Optional[str] = None,
        label_col: Optional[str] = None,
        color_by: Optional[str] = None,
        annotation: Optional[str] = None,
        subtitle: Optional[str] = None,
        sort: str = 'none',
        y_scale: bool = False,
        label: str = 'auto',
        dry_run: bool = False,
        target: Optional[float] = None,
        x_name: Optional[str] = None,
        y_names: Optional[List[str]] = None,
        series_names: Optional[List[str]] = None,
        geo: Optional[str] = None,
        geo_path: Optional[str] = None,
        extra_advisories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:

























        try:
            
            
            
            
            source_rows = int(len(df))
            if df.empty:
                raise ChartError("数据为空", ErrorCode.DATA_EMPTY)
            if lang is not None and lang not in ('zh', 'en'):
                raise ChartError(
                    f"不支持的 lang: {lang}，支持: zh / en",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': lang, 'supported': ['zh', 'en'],
                             'suggestion': '省略 --lang 让语言跟随数据自动检测，或显式传 zh / en'},
                )
            try:
                ct = ChartType(chart_type)
            except ValueError:
                supported = [t.value for t in ChartType]
                raise ChartError(
                    f"不支持的图表类型: {chart_type}，支持: {supported}",
                    ErrorCode.CHART_TYPE_UNSUPPORTED,
                    details={
                        'given': chart_type,
                        'supported': supported,
                        'suggestion': '参考 SKILL.md 图表类型表',
                    },
                )

            if transform_code:
                df = DataTransformer().transform(df, transform_code)

            if sort not in ('none', 'value'):
                raise ChartError(
                    f"不支持的 sort: {sort}，支持: none / value",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': sort, 'supported': ['none', 'value'],
                             'suggestion': 'none=保持数据原序（默认）；value=按第一个数值 Y 列降序（仅 bar/stacked_bar）'},
                )
            if label not in ('auto', 'all', 'key'):
                raise ChartError(
                    f"不支持的 label: {label}，支持: auto / all / key",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={'given': label, 'supported': ['auto', 'all', 'key'],
                             'suggestion': 'auto=类别>20 时只标关键值（默认）；all=全部标注；key=只标 top3 与极值'},
                )

            texts, lang_resolved = get_texts(lang, df)
            if title is None:
                title = texts['default_title']
            
            
            
            if annotation is None or not str(annotation).strip():
                annotation = texts['default_annotation'].format(n=len(df))
                annotation_source = 'default'
            else:
                annotation_source = 'user'

            if ct is ChartType.SPREADSHEET:
                return self._generate_spreadsheet(
                    df, title, x_axis, y_axis, width, height, texts, lang_resolved,
                    annotation, dry_run, subtitle=subtitle,
                    annotation_source=annotation_source, target=target,
                    extra_advisories=extra_advisories,
                )

            gen = getattr(self, f'_{ct.value}', None)
            if gen is None:
                
                raise ChartError(
                    f"暂不支持该图表类型: {chart_type}",
                    ErrorCode.CHART_TYPE_UNSUPPORTED,
                    details={'given': chart_type},
                )

            x_axis, y_axis = self._prepare_axes(df, chart_type, x_axis, y_axis)

            
            assumptions = []
            for param, col in (('label_col', label_col), ('color_by', color_by)):
                if col is not None and col not in df.columns:
                    raise ChartError(
                        f"{param} 字段不存在: {col}",
                        ErrorCode.CHART_CONFIG_ERROR,
                        details={
                            'given': col,
                            'available': list(df.columns),
                            'suggestion': '从 available 列中选择一个已存在的列',
                        },
                    )
            
            
            if chart_type in ('graph', 'sankey'):
                
                
                pass

            
            
            
            geo_fields: Dict[str, Any] = {}
            if chart_type in ('map', 'lines'):
                gs = resolve_geo(geo, geo_path)
                geo_fields = {
                    'geo_map_name': gs.map_name,
                    'geo_json': gs.geojson,
                    'geo_aliases': gs.aliases,
                    'geo_names': geojson_region_names(gs.geojson),
                }

            ctx = RenderContext(
                df=df, x=x_axis, y=y_axis, title=title, texts=texts, theme=self._theme,
                lang=lang_resolved, label_col=label_col, color_by=color_by,
                y_scale=y_scale, sort=sort, label_mode=label, subtitle=subtitle,
                width=width, height=height,
                x_name=x_name, y_names=y_names, series_names=series_names,
                target=target,
                **geo_fields,
            )
            advisories = []
            
            
            
            
            
            
            
            if x_axis and x_axis in df.columns and chart_type in _AGG_REQUIRED_TYPES:
                n_rows, n_x = int(len(df)), int(df[x_axis].nunique(dropna=False))
                if n_rows > n_x:
                    vc = df[x_axis].value_counts()
                    advisories.append(
                        f'疑似未聚合：x 轴「{x_axis}」只有 {n_x} 个取值却是 {n_rows} 行数据'
                        f'（如「{vc.index[0]}」占 {int(vc.iloc[0])} 行）。'
                        f'此时 plot_stats 的 max/min/mean 是行级统计，不代表该「{x_axis}」的合计或均值；'
                        f'若要按「{x_axis}」维度下结论，请先 --transform-code 聚合'
                        f"（如 result = df.groupby('{x_axis}')['<数值列>'].sum().reset_index()）"
                    )
            
            if ct is ChartType.PIE:
                n_cat = int(df[x_axis].nunique())
                if n_cat > 8:
                    advisories.append(
                        f'饼图类别数为 {n_cat}（>8），人眼难以比较角度；'
                        '建议改用 bar --sort value 做精确对比，或用 transform 聚合小类'
                    )
            
            if ct in (ChartType.GAUGE, ChartType.LIQUID) and not target:
                advisories.append(
                    f'{chart_type} 未提供 --target：achievement（达成率）已置 null。'
                    '自动推断的量程不是业务目标，若需达成率请传 --target <目标值>'
                )
            option = gen(ctx)
            option = self._apply_custom_names(option, x_name, y_names, series_names)
            data_points = self._estimate_data_points(df, chart_type, x_axis, y_axis)
            plot_stats = compute_plot_stats(df, chart_type, x_axis, y_axis,
                                            label_col=label_col, target=target,
                                            geo_names=geo_fields.get('geo_names'),
                                            geo_aliases=geo_fields.get('geo_aliases'))
            if dry_run:
                html_path = None
            else:
                html_path = self._save_html(ctx, option, width, height, chart_type, data_points, annotation)
                if getattr(self, '_title_truncated', False):
                    advisories.append('标题超过 30 字符，文件名已截断为 30 字符；完整标题见 title 字段')
            
            preview, data_rows = self._data_preview(df, x_axis, y_axis)
            
            
            entity_col = label_col if (label_col and label_col in df.columns) else x_axis
            chart_result = {
                'success': True,
                'dry_run': dry_run,
                'html_path': str(html_path) if html_path is not None else None,
                'chart_type': chart_type,
                'title': title,
                'source_rows': source_rows,
                'plotted_rows': data_rows,
                'unique_entities': int(df[entity_col].nunique()) if entity_col in df.columns else int(len(df)),
                'data_rows': data_rows,
                'data_preview': preview,
                'annotation_source': annotation_source,
            }
            if plot_stats is not None:
                chart_result['plot_stats'] = plot_stats
            if assumptions:
                chart_result['assumptions'] = assumptions
            if advisories:
                chart_result['advisories'] = advisories
            self._attach_advisories(chart_result, extra_advisories, annotation_source)
            return {'chart': chart_result}
        except SmartChartsError as e:
            return {
                'chart': {
                    'success': False,
                    'error': e.to_dict(),
                    'chart_type': chart_type,
                    'title': title or '',
                }
            }
        except Exception as e:
            return {
                'chart': {
                    'success': False,
                    'error': {'error': str(e), 'code': ErrorCode.CHART_GENERATION_ERROR.value, 'code_name': ErrorCode.CHART_GENERATION_ERROR.name},
                    'chart_type': chart_type,
                    'title': title or '',
                }
            }

    def _generate_spreadsheet(
        self, df: pd.DataFrame, title: str, x_axis: Optional[str], y_axis: Optional[List[str]],
        width: int, height: int, texts: Dict[str, str], lang: str,
        annotation: str, dry_run: bool, subtitle: Optional[str] = None,
        annotation_source: str = 'default', target: Optional[float] = None,
        extra_advisories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        
        
        if isinstance(y_axis, str):
            y_axis = [y_axis]
        shown = ([x_axis] if x_axis is not None else []) + [c for c in (y_axis or []) if c != x_axis]
        for col in shown:
            if col not in df.columns:
                raise ChartError(
                    f"列不存在: {col}",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'given': col,
                        'available': list(df.columns),
                        'suggestion': '从 available 列中选择一个已存在的列',
                    },
                )
        df_table = df[shown] if shown else df
        plot_stats = stats_spreadsheet(df_table)
        if dry_run:
            html_path = None
        else:
            ctx = RenderContext(df=df_table, x=None, y=[], title=title, texts=texts,
                                theme=self._theme, lang=lang, subtitle=subtitle)
            html_path = self._save_table_html(ctx, df_table, title, width, height, annotation)
        preview, data_rows = self._data_preview(df, None, None)
        chart_result = {
            'success': True,
            'dry_run': dry_run,
            'html_path': str(html_path) if html_path is not None else None,
            'chart_type': 'spreadsheet',
            'title': title,
            'source_rows': int(len(df)),
            'plotted_rows': data_rows,
            'unique_entities': int(df_table.drop_duplicates().shape[0]),
            'data_rows': data_rows,
            'data_preview': preview,
            'annotation_source': annotation_source,
        }
        if plot_stats is not None:
            chart_result['plot_stats'] = plot_stats
        if not dry_run and getattr(self, '_title_truncated', False):
            chart_result['advisories'] = ['标题超过 30 字符，文件名已截断为 30 字符；完整标题见 title 字段']
        self._attach_advisories(chart_result, extra_advisories, annotation_source)
        return {'chart': chart_result}

    @staticmethod
    def _apply_custom_names(option: Dict[str, Any], x_name: Optional[str],
                            y_names: Optional[List[str]],
                            series_names: Optional[List[str]]) -> Dict[str, Any]:










        if x_name or y_names:
            for g in option.get('graphic', []):
                gid = g.get('id', '')
                if gid == 'axisName-x' and x_name:
                    g.setdefault('style', {})['text'] = x_name
                elif gid.startswith('axisName-y') and y_names:
                    suffix = gid[len('axisName-y'):]
                    try:
                        idx = int(suffix)
                    except ValueError:
                        continue
                    if idx < len(y_names):
                        g.setdefault('style', {})['text'] = y_names[idx]
        if series_names:
            visible = 0
            for s in option.get('series', []):
                if s.get('silent') or str(s.get('name', '')).startswith('__'):
                    continue
                if visible < len(series_names):
                    s['name'] = series_names[visible]
                visible += 1
        return option

    @staticmethod
    def _attach_advisories(chart_result: Dict[str, Any], extra_advisories: Optional[List[str]],
                           annotation_source: str = 'user') -> None:





        merged = list(extra_advisories or [])
        if annotation_source == 'default':
            merged.append(
                'annotation 未由 --annotation 提供，已使用默认模板文案填充；'
                '按交付规范需由 agent 读 plot_stats 后撰写解读并重新生成'
            )
        if merged:
            existing = chart_result.get('advisories')
            chart_result['advisories'] = (existing or []) + merged

    def generate_multi_charts(
        self,
        df: pd.DataFrame,
        chart_configs: List[Dict[str, Any]],
        width: int = 900,
        height: int = 560,
        lang: Optional[str] = None,
        dry_run: bool = False,
        target: Optional[float] = None,
        geo: Optional[str] = None,
        geo_path: Optional[str] = None,
        extra_advisories: Optional[List[str]] = None,
    ) -> Dict[str, Any]:






        results = []
        for cfg in chart_configs:
            r = self.generate_chart(
                df=df,
                chart_type=cfg.get('type', 'bar'),
                title=cfg.get('title') or None,
                x_axis=cfg.get('x_axis'),
                y_axis=cfg.get('y_axis'),
                transform_code=cfg.get('transform_code'),
                width=cfg.get('width', width),
                height=cfg.get('height', height),
                lang=lang,
                label_col=cfg.get('label_col'),
                color_by=cfg.get('color_by'),
                annotation=cfg.get('annotation'),
                subtitle=cfg.get('subtitle'),
                sort=cfg.get('sort', 'none'),
                y_scale=bool(cfg.get('y_scale', False)),
                label=cfg.get('label', 'auto'),
                dry_run=dry_run,
                target=cfg.get('target', target),
                x_name=cfg.get('x_name'),
                y_names=cfg.get('y_name'),
                series_names=cfg.get('series_names') or (([cfg.get('series_name')] if cfg.get('series_name') else None)),
                geo=cfg.get('geo', geo),
                geo_path=cfg.get('geo_path', geo_path),
                extra_advisories=extra_advisories,
            )
            chart_result = r['chart']
            chart_result['config'] = cfg
            results.append(chart_result)
        return {'charts': results}

    

    def _prepare_axes(self, df, chart_type, x_axis, y_axis) -> Tuple[str, List[str]]:
        
        
        
        if (chart_type == 'histogram'
                and x_axis is not None and x_axis in df.columns
                and pd.api.types.is_numeric_dtype(df[x_axis])):
            y_axis = [x_axis]

        
        
        if chart_type in ('mindmap', 'orgchart'):
            if y_axis is None or x_axis is None:
                raise ChartError(
                    f"{chart_type} 需要 父节点列(x) + 子节点列(y) 两个分类列",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'available': list(df.columns),
                        'suggestion': '用 --x-axis <父列> --y-axis <子列> 显式指定层级关系',
                    },
                )

        
        
        if chart_type in ('graph', 'sankey', 'lines'):
            if x_axis is None or not y_axis:
                raise ChartError(
                    f"{chart_type} 需要 来源列(x) + 去向列(y) 两列（可选 值列）",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'available': list(df.columns),
                        'suggestion': '用 --x-axis <来源列> --y-axis <去向列> [<值列>] 显式指定',
                    },
                )

        if x_axis is None:
            date_cols = df.select_dtypes(include=['datetime', 'datetime64']).columns
            cat_cols = df.select_dtypes(include=['object', 'string', 'category']).columns
            x_axis = date_cols[0] if len(date_cols) > 0 else (cat_cols[0] if len(cat_cols) > 0 else df.columns[0])

        if y_axis is None:
            avail = [c for c in df.columns if c != x_axis]
            nums = df[avail].select_dtypes(include=[np.number]).columns.tolist()
            y_axis = nums[:5] if nums else avail[:3]
        elif isinstance(y_axis, str):
            y_axis = [y_axis]

        if x_axis not in df.columns:
            raise ChartError(
                f"X轴字段不存在: {x_axis}",
                ErrorCode.CHART_CONFIG_ERROR,
                details={
                    'given': x_axis,
                    'available': list(df.columns),
                    'suggestion': '从 available 列中选择一个已存在的列，或提供 transform_code 生成所需列',
                },
            )
        for y in y_axis:
            if y not in df.columns:
                raise ChartError(
                    f"Y轴字段不存在: {y}",
                    ErrorCode.CHART_CONFIG_ERROR,
                    details={
                        'given': y,
                        'available': list(df.columns),
                        'suggestion': '从 available 列中选择一个已存在的列，或提供 transform_code 生成所需列',
                    },
                )
        return x_axis, y_axis

    def _data_preview(self, df: pd.DataFrame, x_axis: Optional[str], y_axis: Optional[List[str]], limit: int = 10) -> Tuple[List[Dict[str, Any]], int]:







        cols = list(dict.fromkeys(
            ([x_axis] if x_axis is not None else []) + list(y_axis or []))) or list(df.columns)
        records: List[Dict[str, Any]] = []
        for _, row in df[cols].head(limit).iterrows():
            rec: Dict[str, Any] = {}
            for c in cols:
                v = row[c]
                try:
                    if v is None or pd.isna(v):
                        rec[c] = None
                        continue
                except (TypeError, ValueError):
                    pass
                if isinstance(v, str):
                    rec[c] = v
                elif isinstance(v, (bool, np.bool_)):
                    rec[c] = bool(v)
                else:
                    try:
                        f = float(v)
                        rec[c] = int(f) if f.is_integer() and abs(f) < 2 ** 53 else f
                    except (TypeError, ValueError):
                        rec[c] = str(v)
            records.append(rec)
        return records, len(df)

    def _estimate_data_points(self, df: pd.DataFrame, chart_type: str, x_axis: str, y_axis: List[str]) -> int:






        try:
            if chart_type in ('bar', 'line', 'area', 'stacked_bar', 'combo', 'pareto', 'pictorial_bar'):
                
                
                
                if x_axis is not None and x_axis in df.columns:
                    return int(df[x_axis].nunique())
                return len(df)
        except Exception:
            pass
        return 0
