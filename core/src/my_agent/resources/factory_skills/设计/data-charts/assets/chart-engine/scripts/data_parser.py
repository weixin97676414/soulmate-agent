




















import sys
import json
import re
import pandas as pd
import numpy as np
from functools import partial
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union

if __name__ == '__main__' and __package__ is None:
    import _bootstrap  
    from scripts.exceptions import FileError, DataError, SmartChartsError, ErrorCode, JSONArgumentParser
    from scripts.profile import build_profile
else:
    from .exceptions import FileError, DataError, SmartChartsError, ErrorCode, JSONArgumentParser
    from .profile import build_profile



ENCODING_FALLBACKS: Tuple[str, ...] = ('utf-8', 'utf-8-sig', 'gbk', 'gb2312', 'utf-16', 'latin1')




_LEADING_ZERO_RE = re.compile(r'^0\d+$')




_LONG_INT_RE = re.compile(r'^\d{16,}$')


_CN_MAGNITUDE = (('亿', 1e8), ('万', 1e4), ('千', 1e3))


_NUMERIC_SUCCESS_THRESHOLD = 0.5


class DataParser:

    MAX_FILE_SIZE_MB = 100  

    def __init__(self):
        
        
        
        self.advisories: List[str] = []
        self._parsers = {
            '.csv': partial(DataParser._parse_delimited, sep=','),
            '.tsv': partial(DataParser._parse_delimited, sep='\t'),
            '.xlsx': DataParser._parse_excel,
            '.xls': DataParser._parse_excel,
            '.json': DataParser._parse_json,
            '.txt': DataParser._parse_text,
        }

    def parse_file(
        self,
        file_path: str,
        skiprows: Optional[int] = None,
        header_row: Optional[int] = None,
        sheet_name: Union[int, str] = 0,
        drop_rows: Optional[List[int]] = None,
        **kwargs,
    ) -> pd.DataFrame:











        path = Path(file_path)
        self.advisories = []
        if not path.exists():
            raise FileError(
                f"文件不存在: {file_path}",
                ErrorCode.FILE_NOT_FOUND,
                details={'path': file_path, 'suggestion': '检查路径是否正确，或使用绝对路径'},
            )
        if not path.is_file():
            raise FileError(
                f"不是文件: {file_path}",
                ErrorCode.FILE_NOT_REGULAR,
                details={'path': file_path, 'suggestion': '路径指向的不是常规文件（可能是目录）'},
            )
        size_mb = path.stat().st_size / 1024 / 1024
        if size_mb > self.MAX_FILE_SIZE_MB:
            raise FileError(
                f"文件超过{self.MAX_FILE_SIZE_MB}MB限制",
                ErrorCode.FILE_SIZE_EXCEEDED,
                details={
                    'path': file_path,
                    'size_mb': round(size_mb, 2),
                    'limit_mb': self.MAX_FILE_SIZE_MB,
                    'suggestion': f'拆分文件或筛选行/列后重试，单文件上限 {self.MAX_FILE_SIZE_MB}MB',
                },
            )

        ext = path.suffix.lower()
        if ext not in self._parsers:
            
            
            if not ext:
                ext = self._detect_type(path)
        if ext not in self._parsers:
            supported = list(self._parsers.keys())
            raise FileError(
                f"不支持的格式: {ext}，支持: {supported}",
                ErrorCode.FILE_FORMAT_INVALID,
                details={
                    'path': file_path,
                    'given_ext': ext,
                    'supported': supported,
                    'suggestion': '将文件转为支持的格式（CSV/Excel/JSON）后重试',
                },
            )

        
        if skiprows is not None:
            kwargs['skiprows'] = skiprows
        if header_row is not None:
            kwargs['header_row'] = header_row
        
        kwargs.setdefault('sheet_name', 0 if sheet_name is None else sheet_name)

        df = self._parsers[ext](self, path, **kwargs)
        if df.empty:
            raise DataError(
                "文件内容为空",
                ErrorCode.DATA_EMPTY,
                details={'path': file_path, 'suggestion': '检查文件是否只有表头无数据行，或用 --sheet 指定其他工作表'},
            )

        df = self._clean(df)
        if drop_rows:
            df = self._drop_rows(df, drop_rows)
        self._validate(df)
        return df

    def parse_files(self, file_paths: List[str], merge: bool = False) -> Dict[str, Any]:





        results = []
        for fp in file_paths:
            df = self.parse_file(fp)
            results.append({'file': Path(fp).name, 'data': df})

        if not merge:
            return {'merged': False, 'data': results, 'merge_type': None}

        merged_df, merge_type = self._merge(results)
        return {'merged': True, 'data': merged_df, 'merge_type': merge_type}

    def get_data_summary(self, df: pd.DataFrame) -> Dict[str, Any]:
        
        
        summary: Dict[str, Any] = {
            'shape': list(df.shape),
            'columns': list(df.columns),
            'dtypes': {col: str(dtype) for col, dtype in df.dtypes.items()},
            'missing': {k: int(v) for k, v in df.isnull().sum().to_dict().items()},
            'sample': df.head(5).to_dict('records'),
            'tail': df.tail(5).to_dict('records'),
        }
        
        
        numeric_cols = df.select_dtypes(include=[np.number]).columns
        if len(numeric_cols) > 0:
            summary['stats'] = df[numeric_cols].describe().to_dict()
        warnings = list(self.advisories)
        if warnings:
            summary['warnings'] = warnings
        return summary

    @staticmethod
    def _dedupe_columns(cols: List[Any]) -> List[str]:





        used = set()
        out: List[str] = []
        for c in cols:
            name = str(c)
            if name not in used:
                used.add(name)
                out.append(name)
                continue
            n = 2
            while f'{name}_{n}' in used:
                n += 1
            new = f'{name}_{n}'
            used.add(new)
            out.append(new)
        return out

    def _merge(self, results: List[Dict]) -> Tuple[pd.DataFrame, str]:

        dfs = [r['data'] for r in results]
        col_sets = [set(df.columns) for df in dfs]

        
        if all(len(cs) > 0 for cs in col_sets) and all(cs == col_sets[0] for cs in col_sets):
            merged = pd.concat(dfs, ignore_index=True)
            merged['source_file'] = [r['file'] for r in results for _ in range(len(r['data']))]
            cols = list(merged.columns)
            cols.remove('source_file')
            merged = merged[cols + ['source_file']]
            return merged, '纵向拼接'

        
        if len(dfs) >= 2 and all(len(cs) > 0 for cs in col_sets):
            intersection = col_sets[0]
            for cs in col_sets[1:]:
                intersection = intersection & cs
            avg_col_count = sum(len(cs) for cs in col_sets) / len(col_sets)
            if len(intersection) >= avg_col_count * 0.5:
                
                
                original_cols = set()
                for df in dfs:
                    original_cols.update(str(c) for c in df.columns)
                merged = dfs[0]
                for df in dfs[1:]:
                    merged = pd.merge(merged, df, on=list(intersection), how='outer', suffixes=('', '_dup'))
                merged = self._collapse_merge_suffixes(merged, original_cols)
                return merged, '横向关联'

        
        summary_parts = []
        for r in results:
            summary_parts.append(f"{r['file']}: {r['data'].shape[0]}行 {r['data'].shape[1]}列, 列={list(r['data'].columns)}")
        raise DataError(
            f"文件结构差异大，无法自动合并。各文件信息：\n" + "\n".join(summary_parts) +
            "\n请指定关联方式，或分别分析。",
            ErrorCode.DATA_MERGE_ERROR,
            details={
                'files': [{'file': r['file'], 'shape': list(r['data'].shape), 'columns': list(r['data'].columns)} for r in results],
                'suggestion': '请指定关联方式（如 merge_files 时提供 on 列），或对每个文件分别分析',
            },
        )

    @staticmethod
    def _collapse_merge_suffixes(merged: pd.DataFrame, original_cols: set) -> pd.DataFrame:










        dup_cols = [
            c for c in merged.columns
            if c.endswith('_dup') and c not in original_cols and c[:-4] in merged.columns
        ]
        for dc in dup_cols:
            base = dc[:-4]
            merged[base] = merged[base].combine_first(merged[dc])
        merged = merged.drop(columns=dup_cols)
        duplicated = merged.columns[merged.columns.duplicated()].tolist()
        if duplicated:
            raise DataError(
                f"横向合并后出现重名列，无法自动处理: {duplicated}",
                ErrorCode.DATA_MERGE_ERROR,
                details={
                    'duplicated_columns': duplicated,
                    'suggestion': '先重命名撞名列（如 xxx_dup）后再合并，或显式指定关联列',
                },
            )
        return merged

    

    def _parse_delimited(self, path: Path, sep: str, **kw) -> pd.DataFrame:

        label = 'CSV' if sep == ',' else 'TSV'
        read_kwargs = self._build_header_kwargs(kw)
        for _enc in ENCODING_FALLBACKS:
            try:
                return pd.read_csv(path, sep=sep, encoding=_enc, dtype=str, **read_kwargs)
            except pd.errors.EmptyDataError:
                raise DataError(
                    "文件内容为空",
                    ErrorCode.DATA_EMPTY,
                    details={'path': str(path), 'suggestion': '检查文件是否只有表头无数据行'},
                )
            except pd.errors.ParserError as e:
                raise DataError(
                    f"{label} 解析失败: {e}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={
                        'path': str(path),
                        'error': str(e),
                        'suggestion': '文件可能含前导说明行或列数不一致，先不加参数运行查看原始布局，再用 --skiprows N 或 --header-row N 跳过冗余行',
                    },
                )
            except UnicodeDecodeError:
                continue
        raise DataError(
            "无法解码文件",
            ErrorCode.DATA_PARSE_ERROR,
            details={'path': str(path), 'tried_encodings': list(ENCODING_FALLBACKS),
                     'suggestion': '用文本编辑器另存为 UTF-8 后重试'},
        )

    def _parse_excel(self, path: Path, **kw) -> pd.DataFrame:
        sheet = kw.get('sheet_name', 0)
        
        ext = path.suffix.lower()
        engine = 'xlrd' if ext == '.xls' else 'openpyxl'
        read_kwargs = self._build_header_kwargs(kw)
        
        
        
        read_kwargs['dtype'] = str
        try:
            xl = pd.ExcelFile(path, engine=engine)
        except Exception as e:
            raise DataError(
                f"Excel读取失败: {e}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'engine': engine, 'error': str(e),
                         'suggestion': '检查文件是否损坏、是否为真正的 Excel 文件（非改扩展名的 CSV）'},
            )
        sheets = list(xl.sheet_names)
        
        if isinstance(sheet, str) and sheet not in sheets:
            raise DataError(
                f"工作表不存在: {sheet}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'given_sheet': sheet, 'available_sheets': sheets,
                         'suggestion': f'从 available_sheets 中选择，或用 --sheet <索引> 指定（共 {len(sheets)} 个）'},
            )
        if isinstance(sheet, int) and not (-len(sheets) <= sheet < len(sheets)):
            raise DataError(
                f"工作表索引越界: {sheet}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'given_index': sheet, 'available_sheets': sheets,
                         'suggestion': f'索引范围 0~{len(sheets) - 1}，或直接用 --sheet <名称>'},
            )
        try:
            df = pd.read_excel(path, sheet_name=sheet, engine=engine, **read_kwargs)
            
            
            if df.empty and sheet == 0:
                for s in sheets[1:]:
                    df2 = pd.read_excel(path, sheet_name=s, engine=engine, **read_kwargs)
                    if not df2.empty:
                        return df2
            return df
        except DataError:
            raise
        except Exception as e:
            raise DataError(
                f"Excel读取失败: {e}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'engine': engine, 'error': str(e),
                         'available_sheets': sheets,
                         'suggestion': '检查文件是否损坏、是否为真正的 Excel 文件（非改扩展名的 CSV）'},
            )

    @staticmethod
    def _build_header_kwargs(kw: Dict[str, Any]) -> Dict[str, Any]:






        out: Dict[str, Any] = {}
        skiprows = kw.get('skiprows')
        header_row = kw.get('header_row')
        if header_row is not None:
            
            out['header'] = int(header_row)
        elif skiprows is not None:
            out['skiprows'] = int(skiprows)
        return out

    def _parse_json(self, path: Path, **kw) -> pd.DataFrame:

        data = None
        last_error = None
        for enc in ENCODING_FALLBACKS:
            try:
                with open(path, 'r', encoding=enc) as f:
                    data = json.load(f)
                break
            except UnicodeDecodeError:
                continue
            except json.JSONDecodeError as e:
                last_error = e
                continue
        if data is None:
            if last_error:
                raise DataError(
                    f"JSON 解析失败: {last_error}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path), 'error': str(last_error), 'suggestion': '用 JSON 校验工具检查格式（如 jsonlint.com）'},
                )
            raise DataError(
                "无法解码 JSON 文件",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'tried_encodings': list(ENCODING_FALLBACKS), 'suggestion': '用文本编辑器另存为 UTF-8 后重试'},
            )

        
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            list_value = next((v for v in data.values() if isinstance(v, list)), None)
            records = list_value if list_value is not None else [data]
        else:
            raise DataError(
                "不支持的JSON结构",
                ErrorCode.DATA_PARSE_ERROR,
                details={'path': str(path), 'top_level_type': type(data).__name__,
                         'suggestion': 'JSON 顶层必须是数组、或含数组值的对象'},
            )

        
        
        for r in records:
            if not isinstance(r, dict):
                continue
            for k, v in r.items():
                if isinstance(v, list):
                    raise DataError(
                        f"JSON 字段 '{k}' 的值为数组，暂不支持",
                        ErrorCode.DATA_PARSE_ERROR,
                        details={'path': str(path), 'field': k,
                                 'suggestion': '请将数组字段转为标量（如取首元素、求和），或用工具先转为 CSV 再生成图表'},
                    )
                if isinstance(v, dict):
                    if any(isinstance(x, (dict, list)) for x in v.values()):
                        raise DataError(
                            "JSON 嵌套超过 1 层，暂不支持",
                            ErrorCode.DATA_PARSE_ERROR,
                            details={'path': str(path), 'field': k,
                                     'suggestion': '每条记录最多嵌套 1 层对象（展开为 "父.子" 列），更深的结构请先展平或转为 CSV'},
                        )
                    
                    
                    clash = [f'{k}.{sk}' for sk in v if f'{k}.{sk}' in r]
                    if clash:
                        raise DataError(
                            f"JSON 嵌套字段展开后与已有列重名: {clash}",
                            ErrorCode.DATA_PARSE_ERROR,
                            details={'path': str(path), 'duplicated_columns': clash,
                                     'suggestion': '展开产生的 "父.子" 列名与现有字段撞名，请重命名字段后再试'},
                        )

        
        has_nested = any(
            isinstance(v, dict)
            for r in records if isinstance(r, dict) for v in r.values()
        )
        if has_nested:
            if not all(isinstance(r, dict) for r in records):
                raise DataError(
                    "JSON 记录结构不一致（对象与标量混排），暂不支持",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path),
                             'suggestion': '数组元素须全部为对象，请清理数据或先转为 CSV'},
                )
            df = pd.json_normalize(records, max_level=1)
            dup = df.columns[df.columns.duplicated()].tolist()
            if dup:
                raise DataError(
                    f"JSON 嵌套字段展开后与已有列重名: {dup}",
                    ErrorCode.DATA_PARSE_ERROR,
                    details={'path': str(path), 'duplicated_columns': dup,
                             'suggestion': '展开产生的 "父.子" 列名与现有字段撞名，请重命名字段后再试'},
                )
            return df
        if isinstance(data, list):
            return pd.DataFrame(data)
        if list_value is not None:
            return pd.DataFrame(list_value)
        return pd.json_normalize(data)

    def _parse_text(self, path: Path, **kw) -> pd.DataFrame:

        lines = None
        detected_enc = ENCODING_FALLBACKS[0]
        for enc in ENCODING_FALLBACKS:
            try:
                with open(path, 'r', encoding=enc) as f:
                    lines = [l.strip() for l in f if l.strip()]
                detected_enc = enc
                break
            except UnicodeDecodeError:
                continue
        if not lines:
            raise DataError(
                "文件为空",
                ErrorCode.DATA_EMPTY,
                details={'path': str(path), 'suggestion': '检查文件是否有内容'},
            )
        read_kwargs = self._build_header_kwargs(kw)
        for delim in (',', '\t', ';', '|'):
            if delim in lines[0] and len(lines[0].split(delim)) > 1:
                return pd.read_csv(path, sep=delim, encoding=detected_enc, dtype=str, **read_kwargs)
        return pd.DataFrame({'content': lines})

    def _detect_type(self, path: Path) -> str:
        try:
            header = path.read_bytes()[:1024]
            text = header.decode('utf-8', errors='ignore')
            if text.strip().startswith(('{', '[')):
                return '.json'
            if header.startswith(b'\x50\x4B\x03\x04'):
                return '.xlsx'
            for delim in (',', '\t', ';'):
                if delim in text:
                    return '.csv'
        except Exception:
            pass
        return path.suffix.lower()

    def _clean(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.dropna(axis=1, how='all').dropna(axis=0, how='all').reset_index(drop=True)
        
        df.columns = self._dedupe_columns([self._normalize_col(c) for c in df.columns])
        for col in df.columns:
            if df[col].dtype == 'object' or pd.api.types.is_string_dtype(df[col]):
                
                
                if not self._is_id_like(col, df[col]):
                    converted, note = self._to_numeric_if_possible(df[col])
                    if note is not None:
                        self.advisories.append(note)
                    df[col] = converted
        
        
        return df

    @staticmethod
    def _is_id_like(col: str, series: pd.Series) -> bool:






        try:
            s = series.dropna().astype(str).str.strip()
            return bool(s.str.match(_LEADING_ZERO_RE).any() or s.str.match(_LONG_INT_RE).any())
        except Exception:
            return False

    @staticmethod
    def _to_numeric_if_possible(series: pd.Series) -> Tuple[pd.Series, Optional[str]]:













        
        
        s = series.fillna('').astype(str).str.strip()
        non_empty = s != ''
        n_non_empty = int(non_empty.sum())
        if n_non_empty == 0:
            return series, None
        cleaned = s.str.replace(r'[¥$€£￥]', '', regex=True).str.replace(',', '', regex=False)
        has_pct = cleaned.str.endswith('%')
        cleaned = cleaned.str.rstrip('%')
        
        mult = pd.Series(1.0, index=cleaned.index)
        for unit, factor in _CN_MAGNITUDE:
            is_u = cleaned.str.endswith(unit)
            if is_u.any():
                mult = mult.where(~is_u, factor)
                cleaned = cleaned.where(~is_u, cleaned.str.rstrip(unit))
        converted = pd.to_numeric(cleaned.mask(~non_empty), errors='coerce') * mult
        if has_pct.any():
            converted = converted.where(~has_pct, converted / 100.0)
        n_ok = int(converted.notna().sum())
        if n_ok == 0:
            return series, None
        if n_ok < n_non_empty:
            if n_ok / n_non_empty < _NUMERIC_SUCCESS_THRESHOLD:
                return series, None
            return converted, (
                f'列 "{series.name}" 有 {n_non_empty - n_ok}/{n_non_empty} 个单元格不是合法数值，'
                f'已置为缺失后转数值列（原值如 "-"、"N/A" 会被丢弃）；'
                f'如需保留为分类，请用 --transform-code 显式处理'
            )
        return converted, None

    @staticmethod
    def _normalize_col(name: Any) -> str:
        if pd.isna(name):
            return 'unnamed'
        s = re.sub(r'[^\w\s]', '_', str(name).strip())
        s = re.sub(r'[\s_]+', '_', s).strip('_').lower()
        return s or 'unnamed'

    def _drop_rows(self, df: pd.DataFrame, positions: List[int]) -> pd.DataFrame:






        n = int(len(df))
        positions = sorted(set(positions))
        bad = [p for p in positions if p < 0 or p >= n]
        if bad:
            raise DataError(
                f"--drop-rows 位置越界: {bad}（清洗后数据只有 {n} 行，位置须在 0~{n - 1}）",
                ErrorCode.DATA_PARSE_ERROR,
                details={
                    'positions': positions,
                    'rows': n,
                    'suggestion': '位置是清洗后 DataFrame 的行索引（0-based），'
                                  '先用 --profile 看 row_quality 与 rows 确认行数，'
                                  '或 --transform-code result = df.drop(index=[...])',
                },
            )
        if positions:
            df = df.drop(index=positions).reset_index(drop=True)
            self.advisories.append(
                f'已按 --drop-rows 丢弃 {len(positions)} 行（位置 {positions}，0-based），'
                f'剩余 {int(len(df))} 行'
            )
        return df

    @staticmethod
    def _validate(df: pd.DataFrame):
        if df.empty:
            raise DataError(
                "数据为空",
                ErrorCode.DATA_EMPTY,
                details={'suggestion': '清洗后数据为空，检查原始数据是否全为空行/空列'},
            )


def _build_arg_parser() -> JSONArgumentParser:
    p = JSONArgumentParser(
        prog='data_parser.py',
        description='智能图表 数据解析器：数据文件 → DataFrame（预览/JSON 摘要）',
    )
    p.add_argument('files', nargs='+', help='数据文件路径（单个或多个）')
    p.add_argument('--summary', action='store_true', help='输出 JSON 数据摘要（shape/列/类型/缺失/样本/统计）')
    p.add_argument('--profile', action='store_true',
                   help='输出 JSON 数据画像（列角色/基数/分布/粒度/候选洞察信号/图型建议）——出图前的第 0 步，不依赖图表类型')
    p.add_argument('--merge', action='store_true', help='多文件自动合并（列相同纵向拼接，公共列>=50%横向关联）')
    p.add_argument('--skiprows', type=int, default=None, metavar='N', help='跳过前 N 行再读取（单文件模式）')
    p.add_argument('--header-row', dest='header_row', type=int, default=None, metavar='N',
                   help='第 N 行（0-based）作为列名，其上方行丢弃（单文件模式）')
    p.add_argument('--drop-rows', dest='drop_rows', default=None, metavar='0,1',
                   help='丢弃清洗后 DataFrame 中指定行位置（0-based，逗号分隔；单文件模式）')
    p.add_argument('--sheet', default=None, metavar='NAME|INDEX',
                   help='Excel 工作表名称或索引（单文件模式，默认第 0 个）')
    return p


def _run_cli() -> int:
    try:
        ns = _build_arg_parser().parse_args()
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1

    sheet_name = 0
    if ns.sheet is not None:
        v = ns.sheet
        sheet_name = int(v) if v.lstrip('-').isdigit() else v

    drop_rows: List[int] = []
    if ns.drop_rows is not None:
        try:
            drop_rows = sorted({int(x) for x in str(ns.drop_rows).split(',') if x.strip()})
        except ValueError:
            err = SmartChartsError(
                f"--drop-rows 需要逗号分隔的整数: {ns.drop_rows}",
                ErrorCode.DATA_PARSE_ERROR,
                details={'given': ns.drop_rows, 'suggestion': '形如 --drop-rows 0,1（0-based 行位置，逗号分隔）'},
            )
            print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)
            return 1

    
    single = len(ns.files) == 1 and not ns.merge
    parser = DataParser()
    try:
        if single:
            df = parser.parse_file(
                ns.files[0], skiprows=ns.skiprows, header_row=ns.header_row, sheet_name=sheet_name,
                drop_rows=drop_rows,
            )
            if ns.profile:
                print(json.dumps(build_profile(df), ensure_ascii=False, indent=2, default=str))
            elif ns.summary:
                print(json.dumps(parser.get_data_summary(df), ensure_ascii=False, indent=2, default=str))
            else:
                print(f"解析成功: {df.shape[0]} 行, {df.shape[1]} 列")
                print(f"列名: {list(df.columns)}")
                print(df.head(5).to_string())
        else:
            result = parser.parse_files(ns.files, merge=ns.merge)
            if result['merged']:
                merged_df, merge_type = result['data'], result['merge_type']
                if ns.profile:
                    prof = build_profile(merged_df)
                    prof['merge_type'] = merge_type
                    print(json.dumps(prof, ensure_ascii=False, indent=2, default=str))
                elif ns.summary:
                    
                    summary = parser.get_data_summary(merged_df)
                    summary['merge_type'] = merge_type
                    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
                else:
                    print(f"合并方式: {merge_type}")
                    print(f"合并后: {merged_df.shape[0]} 行, {merged_df.shape[1]} 列")
                    print(f"列名: {list(merged_df.columns)}")
                    print(merged_df.head(5).to_string())
            else:
                items = result['data']
                if ns.profile:
                    profiles = [{'file': it['file'], **build_profile(it['data'])} for it in items]
                    print(json.dumps(profiles, ensure_ascii=False, indent=2, default=str))
                elif ns.summary:
                    summaries = [{'file': it['file'], **parser.get_data_summary(it['data'])} for it in items]
                    print(json.dumps(summaries, ensure_ascii=False, indent=2, default=str))
                else:
                    for it in items:
                        df = it['data']
                        print(f"\n--- {it['file']}: {df.shape[0]} 行, {df.shape[1]} 列 ---")
                        print(f"列名: {list(df.columns)}")
                        print(df.head(3).to_string())
        return 0
    except SmartChartsError as e:
        print(json.dumps(e.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as e:
        
        
        
        err = SmartChartsError(
            f"未知错误: {e}", ErrorCode.UNKNOWN_ERROR,
            details={'error': str(e), 'type': type(e).__name__,
                     'suggestion': '先不带任何 flags 运行一次查看原始布局；'
                                   '若列名规范化后撞名（如 Sales Amount 与 sales-amount），'
                                   '请重命名源文件的列后重试'},
        )
        print(json.dumps(err.to_dict(), ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(_run_cli())
