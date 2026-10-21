







import ast
import contextlib
import re
import signal
import sys
import pandas as pd
import numpy as np
from typing import Any, Dict, List, Optional, Set, Tuple

from .exceptions import TransformError, ErrorCode




KEYWORD_BLACKLIST: List[str] = [
    
    'exec(', 'eval(', 'compile(',
    
    '__import__', 'importlib', 'import ',
    
    'open(', 'read(', 'write(', 'remove(', 'os.rename(',
    'os.path', 'shutil', 'pathlib.Path',
    
    'socket', 'requests', 'urllib', 'http.', 'subprocess',
    
    'os.system', 'os.popen', 'os.exec', 'os.spawn',
    'sys.exit', 'sys.argv',
    
    '__class__', '__bases__', '__subclasses__', '__globals__',
    '__code__', '__closure__', '__dict__', '__mro__',
    
    
    
    '__builtins__', '__getattribute__', '__getattr__', '__loader__',
    '__spec__', '__self__', '__func__', '__reduce__',
    'getattr(', 'setattr(', 'delattr(',
    
    'breakpoint(', 'exit(', 'quit(',
    
    '@property', '@classmethod', '@staticmethod',
]






DANGEROUS_ATTRIBUTES: Set[str] = {
    
    'read_csv', 'read_excel', 'read_json', 'read_pickle', 'read_hdf', 'read_html',
    
    
    'get_handle', 'open_memmap', 'urlopen', 'urlretrieve',
    'read_sql', 'read_sql_query', 'read_sql_table', 'read_table', 'read_fwf',
    'read_clipboard', 'read_feather', 'read_parquet', 'read_orc', 'read_sas',
    'read_spss', 'read_stata', 'read_gbq',
    
    'to_csv', 'to_excel', 'to_json', 'to_pickle', 'to_hdf', 'to_sql',
    'to_feather', 'to_parquet', 'to_stata', 'to_gbq',
    
    'hdfstore', 'excelwriter', 'excelfile',
    
    'load', 'save', 'savez', 'savez_compressed', 'loadtxt', 'savetxt',
    'fromfile', 'tofile', 'genfromtxt', 'fromregex', 'frombuffer', 'fromstring',
    'memmap',
}





DANGEROUS_MODULE_PREFIXES: Tuple[str, ...] = ('pd.io', 'np.lib')


def _dotted_name(node) -> str:

    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return '.'.join(reversed(parts))


class _DangerousAttributeVisitor(ast.NodeVisitor):





    def __init__(self):
        self.violations: List[str] = []

    def visit_Attribute(self, node):
        if node.attr.lower() in DANGEROUS_ATTRIBUTES:
            self.violations.append(f"不允许的属性访问: .{node.attr}")
        else:
            path = _dotted_name(node).lower()
            for prefix in DANGEROUS_MODULE_PREFIXES:
                if path == prefix or path.startswith(prefix + '.'):
                    self.violations.append(f"不允许的模块路径访问: {_dotted_name(node)}")
                    break
        self.generic_visit(node)





AST_WHITELIST: Set[type] = {
    
    ast.Module, ast.Expr, ast.Assign, ast.AugAssign,
    
    ast.Name, ast.Constant, ast.Num, ast.Str,
    
    ast.UnaryOp, ast.BinOp, ast.BoolOp, ast.Compare,
    ast.UAdd, ast.USub, ast.Not, ast.Invert,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    
    ast.BitAnd, ast.BitOr, ast.BitXor,
    ast.And, ast.Or,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Is, ast.IsNot, ast.In, ast.NotIn,
    
    ast.List, ast.Tuple, ast.Dict, ast.Set,
    
    ast.Subscript, ast.Index, ast.Slice,
    
    ast.Attribute, ast.Call, ast.keyword,
    
    ast.If, ast.IfExp,
    
    ast.For, ast.While,
    
    ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp,
    ast.comprehension,
    
    
    
    ast.JoinedStr, ast.FormattedValue,
    
    ast.Lambda, ast.FunctionDef, ast.Return,
    ast.arguments, ast.arg,
    
    ast.Starred,
}



for _t in (getattr(ast, 'Num', None), getattr(ast, 'Str', None),
           getattr(ast, 'Index', None), getattr(ast, 'NameConstant', None)):
    if _t is not None:
        AST_WHITELIST.add(_t)


class CodeValidationError(TransformError):

    pass


def _strip_comments_and_strings(code: str) -> str:





    
    lines = []
    in_string = False
    string_char = None
    for line in code.split('\n'):
        result_chars = []
        i = 0
        while i < len(line):
            c = line[i]
            if in_string:
                result_chars.append(c)
                if c == string_char and (i == 0 or line[i-1] != '\\'):
                    in_string = False
                    string_char = None
            elif c in ('"', "'"):
                in_string = True
                string_char = c
                result_chars.append(c)
            elif c == '#':
                
                break
            else:
                result_chars.append(c)
            i += 1
        lines.append(''.join(result_chars))
    return '\n'.join(lines)


def validate_code_blacklist(code: str) -> List[str]:





    violations = []
    
    code_clean = _strip_comments_and_strings(code)
    code_lower = code_clean.lower()
    for keyword in KEYWORD_BLACKLIST:
        kw_lower = keyword.lower()
        if kw_lower in code_lower:
            violations.append(keyword)
    return violations


def validate_code_ast(code: str) -> List[str]:





    violations = []
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return [f"语法错误: {e}"]

    for node in ast.walk(tree):
        
        if isinstance(node, (ast.Load, ast.Store, ast.Del)):
            continue
        if type(node) not in AST_WHITELIST:
            violations.append(f"不允许的语法节点: {type(node).__name__}")

    
    visitor = _DangerousAttributeVisitor()
    visitor.visit(tree)
    violations.extend(visitor.violations)

    return violations


class DataTransformer:








    
    SANDBOX_TIMEOUT_SECONDS = 10
    
    SANDBOX_MAX_RECURSION = 500

    def __init__(self, timeout: int = None):




        self.timeout = timeout or self.SANDBOX_TIMEOUT_SECONDS

    def transform(self, df: pd.DataFrame, code: str) -> pd.DataFrame:











        if not code or not code.strip():
            return df

        
        blacklist_violations = validate_code_blacklist(code)
        if blacklist_violations:
            raise CodeValidationError(
                f"代码包含危险关键字，已阻止执行: {', '.join(blacklist_violations)}",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={
                    'code': code,
                    'violations': blacklist_violations,
                    'reason': '这些关键字可能用于文件操作、网络访问、动态执行或系统命令，'
                              '在数据转换场景中不需要。如确需使用，请检查数据是否需要预处理。',
                    'suggestion': '移除这些危险关键字；如确需文件/网络操作，请改用其他工具预处理数据后再导入',
                },
            )

        
        ast_violations = validate_code_ast(code)
        if ast_violations:
            raise CodeValidationError(
                f"代码包含不允许的语法结构，已阻止执行: {', '.join(ast_violations)}",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={
                    'code': code,
                    'violations': ast_violations,
                    'reason': '数据转换代码仅允许使用赋值、运算、方法调用、条件判断、'
                              '循环和推导式等基本语法。不允许导入模块、定义类、'
                              '异常处理等复杂结构。',
                    'suggestion': '仅使用赋值、运算、方法调用、条件判断、循环和推导式等基本语法；去掉 import、类定义、异常处理等结构',
                },
            )

        
        return self._execute_in_sandbox(df, code)

    def _execute_in_sandbox(self, df: pd.DataFrame, code: str) -> pd.DataFrame:







        
        
        
        
        
        ns: Dict[str, Any] = {'df': df.copy(), 'pd': pd, 'np': np}
        
        safe_builtins = {
            'len': len, 'range': range, 'list': list, 'dict': dict,
            'str': str, 'int': int, 'float': float, 'bool': bool,
            'sorted': sorted, 'enumerate': enumerate, 'zip': zip,
            'map': map, 'filter': filter, 'sum': sum, 'min': min, 'max': max,
            'abs': abs, 'round': round, 'set': set, 'tuple': tuple,
            'isinstance': isinstance, 'hasattr': hasattr, 'print': print,
            'True': True, 'False': False, 'None': None,
        }
        ns['__builtins__'] = safe_builtins

        
        original_recursion_limit = sys.getrecursionlimit()
        sys.setrecursionlimit(self.SANDBOX_MAX_RECURSION)

        
        timed_out = [False]

        def _timeout_handler(signum, frame):
            timed_out[0] = True
            raise TimeoutError("转换代码执行超时")

        
        use_signal = False
        old_handler = None
        try:
            if hasattr(signal, 'SIGALRM'):
                use_signal = True
                old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                signal.alarm(self.timeout)
        except (ImportError, ValueError, OSError):
            pass

        try:
            
            
            with contextlib.redirect_stdout(sys.stderr):
                exec(code, ns)
        except TimeoutError:
            raise TransformError(
                f"转换代码执行超时（超过 {self.timeout} 秒），可能存在无限循环",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={'code': code, 'timeout': self.timeout,
                         'suggestion': '检查代码是否含死循环或过重计算；如需更复杂处理，请在本地用 pandas 完成后再导入'},
            )
        except Exception as e:
            raise TransformError(
                f"转换代码执行失败: {e}",
                ErrorCode.TRANSFORM_EXEC_ERROR,
                details={'code': code, 'error': str(e),
                         'suggestion': '根据报错信息修正转换代码；可先用 print(df.columns) 或 print(df.head()) 检查列名与数据类型'},
            )
        finally:
            
            sys.setrecursionlimit(original_recursion_limit)
            
            if use_signal:
                signal.alarm(0)
                if old_handler is not None:
                    signal.signal(signal.SIGALRM, old_handler)

        if 'result' not in ns:
            raise TransformError(
                "转换代码必须产出 result 变量",
                ErrorCode.TRANSFORM_NO_RESULT,
                details={'code': code},
            )

        result = ns['result']
        if not isinstance(result, pd.DataFrame):
            raise TransformError(
                f"result 必须是 DataFrame，实际类型: {type(result).__name__}",
                ErrorCode.TRANSFORM_INVALID_RESULT,
                details={'code': code, 'result_type': type(result).__name__},
            )

        if result.empty:
            raise TransformError(
                "转换后数据为空，请检查转换逻辑",
                ErrorCode.TRANSFORM_EMPTY_RESULT,
                details={'code': code},
            )

        return result
