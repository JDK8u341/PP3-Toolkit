"""PP3 静态 DSL 生成工具箱。

本包只在 Python 编译期生成 PP3 源码，不实现或替换 PP3 运行器。
生成结果仍交给使用者选择的标准 PP3 IRBuilder/Runtime 执行。
"""

from .arrays import NegativeArray
from .frames import ERROR_OUTPUT, frame_program, validate_byte
from .machines import Arena, Chain, InstructionMachine, dual_frame, literal
from .macros import Macros, compile_program, format_code, seq
from .records import RecordHeap, RecordList, Reference, merge_sort

__version__ = "0.1.0"

__all__ = [
    "Arena",
    "Chain",
    "ERROR_OUTPUT",
    "InstructionMachine",
    "Macros",
    "NegativeArray",
    "RecordHeap",
    "RecordList",
    "Reference",
    "compile_program",
    "dual_frame",
    "format_code",
    "frame_program",
    "literal",
    "merge_sort",
    "seq",
    "validate_byte",
]
