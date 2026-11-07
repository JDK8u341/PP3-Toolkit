"""基于负地址连续布局的动态数组宏。"""

from .macros import seq


class NegativeArray:
    """在零锚点下方分配可增长的自然数数组。

    数组元素从 ``-Macros.bound`` 开始，后续元素地址依次减一；控制指针
    保存在独立静态槽中。调用 ``compile_program`` 可自动保证数组起点低于
    全部静态槽。数组只保存非负值，空元素的零值不会被当作终止标记，遍历
    必须使用显式长度或外部条件。

    ``put(expression)`` 通过自环选择目标，表达式不能读取目标的旧值，也
    不能破坏地址 0。指针、元素值和调用方索引必须使用不同槽。数组实例
    共享同一 ``Macros`` 的默认动态起点；若多个实例并存，调用方必须自行
    管理数据区范围，或改用统一的记录堆。
    """

    def __init__(self, macros, name="数据区"):
        """建立数组的静态指针槽，不立即生成或执行任何 PP3 代码。"""
        self.m = macros
        self.name = name
        self.pointer = macros.slot(f"{name}.指针")

    @property
    def base(self):
        """返回本次生成布局中的第一个动态数组地址。"""
        return -self.m.bound

    def reset(self):
        """把数组游标重置到 ``base``。"""
        # 元素可能经过正地址标记，指针到零最多四步。
        p = self.pointer
        return f"&0 ^1 &{p} ^5 &{p} ^1 &{self.base} ^5"

    def advance(self):
        """将游标移至下一元素；动态地址向负方向增长。"""
        # 四次跳转以指针自环补齐经标记或零值返回目标的路径。
        p = self.pointer
        return f"&0 ^1 &{p} ^5 &{p} *1 @- ^5"

    def read(self):
        """读取游标指向的数组元素，不移动游标。"""
        return f"&{self.pointer} ~1 ~1"

    def put(self, expression):
        """把表达式写入当前元素；目标地址表达式建立自环。"""
        # 表达式不得读取目标旧值或破坏零槽。
        p = self.pointer
        return f"&0 ^1 &{p} ~1 ^4 &{p} ~1 ^1 {expression} ^4"

    def change(self, operation):
        """对当前元素原位执行 ``@+`` 或 ``@-``。"""
        if operation not in ("@+", "@-"):
            raise ValueError("数组更新只接受自增或自减")
        p = self.pointer
        return f"&0 ^1 &{p} ~1 ^4 &{p} ~1 *1 {operation} ^4"

    def seek(self, index):
        """从数组起点前进 ``index`` 步；索引必须是自然数静态槽。"""
        counter = self.m.slot(f"{self.name}.寻址计数")
        if index in (counter, self.pointer):
            raise ValueError("数组下标不能使用指针槽或内部计数槽")
        return seq(
            self.m.copy(counter, index), self.reset(),
            self.m.loop(self.m.read(counter), seq(self.advance(), self.m.change(counter, "@-"))),
        )
