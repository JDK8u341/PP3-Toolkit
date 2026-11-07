"""构造 PP3 文本 DSL 的静态宏和自然数运算模板。

宏调用发生在 Python 生成期；返回的是 PP3 源码字符串。没有任何函数会
在 Python 中运行待解题目的输入或模拟其算术。
"""


def seq(*parts):
    """按顺序连接非空代码片段，避免生成空白占位行。"""
    return "\n".join(part for part in parts if part)


def format_code(code):
    """缩进由独立 ``[``/``]`` 行表示的循环，并检查其配对。"""
    depth = 0
    lines = []
    for line in code.splitlines():
        line = line.strip()
        if not line:
            continue
        if line == "]":
            depth -= 1
        if depth < 0:
            raise ValueError("生成的循环括号不匹配")
        lines.append("  " * depth + line)
        if line == "[":
            depth += 1
    if depth:
        raise ValueError("生成的循环括号未闭合")
    return "\n".join(lines) + "\n"


class Macros:
    """为一个生成过程分配静态槽并展开通用 PP3 代码片段。

    ``slot(name)`` 从 -3 开始向负方向分配控制槽；-1 和 -2 留作正地址
    标记。``bound`` 是动态数组/记录区的最小负地址幅值，普通用法应由
    ``compile_program`` 两遍构造自动计算，不建议手工指定。

    大多数标量槽约定存非负整数。负数需要由 ``decode_integer`` 拆成幅值
    和符号，不能直接交给这些槽操作。复用同一 ``Macros`` 实例可以共享
    静态槽；不要把不同生成过程的工作槽别名起来。

    比较、十进制编解码和算术模板会申请具名 scratch 槽。它们通常可在
    外层循环中重复调用，但不要把同一模板嵌套在它自己的活动 scratch
    运算内部，除非调用者另行证明重入安全。各方法的别名约束见包文档。
    """
    SET_MARK = -1
    EQUAL_MARK = -2

    def __init__(self, bound=3):
        """创建槽分配器；``bound`` 应大于所有静态槽的地址幅值。"""
        self.bound = bound
        self.slots = {}
        self.flag_count = 0

    def slot(self, name):
        """取得稳定具名槽；同名请求返回同一地址。"""
        if name not in self.slots:
            self.slots[name] = -len(self.slots) - 3
        return self.slots[name]

    @property
    def array_base(self):
        return -self.bound

    def flag(self):
        """分配一个独立分支标志槽。"""
        self.flag_count += 1
        return self.slot(f"条件标志{self.flag_count}")

    @staticmethod
    def read(slot):
        """从零锚点追踪标量槽并把值放入 view。"""
        return f"&{slot} ~1"

    @staticmethod
    def select(slot):
        """选择槽作为写入目标；后续表达式负责产生要写入的值。"""
        return f"&0 ^1 &{slot} ^4 &{slot} ^1"

    def put(self, slot, expression):
        """把 DSL ``expression`` 计算出的非负值存入槽。"""
        return f"{self.select(slot)} {expression} ^4"

    def constant(self, slot, value):
        """把非负立即数写入槽；负数应使用符号/幅值表示。"""
        if value < 0:
            raise ValueError("普通数据槽只接受非负常量")
        return self.put(slot, f"&{value}")

    def copy(self, destination, source):
        """复制标量槽内容，保留来源；同槽复制展开为空操作。"""
        return "" if destination == source else self.put(destination, self.read(source))

    @staticmethod
    def change(slot, operation):
        """对槽值执行 ``@+`` 或 ``@-``，保留其余路由关系。"""
        # 交换保留旧值；自环补齐经标记或零值返回目标的路径。
        if operation not in ("@+", "@-"):
            raise ValueError("更新宏只接受自增或自减")
        return f"&0 ^1 &{slot} ^4 &{slot} *1 {operation} ^4"

    @staticmethod
    def once(condition, body):
        """若 ``condition`` 非零，执行一次 body，退出时将 view 清零。"""
        return seq(condition, "[", body, "&0", "]")

    def if_nonzero(self, condition, nonzero, zero=""):
        """按条件展开互斥分支；两条分支都以 view=0 汇合。"""
        flag = self.flag()
        return seq(
            self.constant(flag, 1),
            self.once(condition, seq(self.constant(flag, 0), nonzero)),
            self.once(self.read(flag), zero),
        )

    def if_zero(self, condition, body):
        """仅在条件为零时执行 body。"""
        return self.if_nonzero(condition, "", body)

    @staticmethod
    def loop(condition, body):
        """按 PP3 非零循环执行 body；body 必须使条件最终归零。"""
        return seq(condition, "[", body, condition, "]")

    def conjunction(self, left, right, result):
        """计算自然数槽的逻辑与，输出规范化布尔值 0 或 1。"""
        if result in (left, right):
            raise ValueError("合取输出不得覆盖输入")
        return seq(self.constant(result, 0), self.once(self.read(left),
                   self.once(self.read(right), self.constant(result, 1))))

    def write_marker(self, pointer, marker):
        """沿自然数地址写入零锚点标记；只允许 0、SET_MARK、EQUAL_MARK。"""
        if marker not in (0, self.SET_MARK, self.EQUAL_MARK):
            raise ValueError("正地址只接受零锚点标记")
        return f"&0 ^1 {self.read(pointer)} ^3 {self.read(pointer)} ^1 &{marker} ^4 &0 ^1"

    def equal(self, left, right, result):
        """以局部地址标记判断两个任意自然数是否相等。

        输入必须是自然数；结果槽不得覆盖输入或内部 scratch 槽。算法在
        ``left+1`` 地址写临时标记，再探测 ``right+1``，最后恢复该地址原
        有的零/集合标记。判等不按数值大小逐次抵消，但仍有地址访问成本。
        """
        pointer, saved = self.slot("等值地址"), self.slot("等值原标记")
        if result in (left, right, pointer, saved) or {left, right} & {pointer, saved}:
            raise ValueError("等值参数不能覆盖输入或内部槽")
        return seq(
            self.put(pointer, self.read(left) + " @+"),
            self.constant(saved, 0), self.constant(result, 0),
            self.once(self.read(pointer) + " ~1", self.constant(saved, 1)),
            self.write_marker(pointer, self.EQUAL_MARK),
            self.if_zero(self.read(right) + " @+ ~1 @+ @+", self.constant(result, 1)),
            self.if_nonzero(self.read(saved), self.write_marker(pointer, self.SET_MARK),
                            self.write_marker(pointer, 0)),
        )

    def compare(self, left, right, lt, eq, gt):
        """比较两个自然数并写入 lt/eq/gt 三个互斥布尔结果。

        原输入保持不变；相等时先使用 ``equal`` 快速返回，否则复制输入并
        同步递减，直到一方归零。结果槽两两不同且不与输入重叠；不能占用
        本对象声明的比较 scratch 槽。非相等路径的 DSL 执行量与较小值相关。
        """
        if len({lt, eq, gt}) != 3 or {lt, eq, gt} & {left, right}:
            raise ValueError("比较输出必须互异且不能覆盖输入")
        a, b, run = (self.slot(name) for name in ("比较副本A", "比较副本B", "比较继续"))
        if {a, b, run} & {left, right, lt, eq, gt}:
            raise ValueError("比较参数不能使用内部槽")
        race = seq(
            self.copy(a, left), self.copy(b, right), self.conjunction(a, b, run),
            self.loop(self.read(run), seq(self.change(a, "@-"), self.change(b, "@-"),
                                         self.conjunction(a, b, run))),
            self.if_nonzero(self.read(a), self.constant(gt, 1), self.constant(lt, 1)),
        )
        return seq(self.constant(lt, 0), self.constant(gt, 0), self.equal(left, right, eq),
                   self.if_zero(self.read(eq), race))

    def in_range(self, value, low, high, result):
        """判断 ``low <= value <= high``，不按区间大小生成分支。

        ``low``、``high`` 是生成期非负常量；区间宏占用具名上下界/比较槽，
        ``result`` 不可覆盖输入或内部槽。输出是规范化布尔值。
        """
        lower, upper, lt, eq, gt = (self.slot(name) for name in (
            "区间下界", "区间上界", "区间小于", "区间等于", "区间大于"))
        if result == value or {value, result} & {lower, upper, lt, eq, gt}:
            raise ValueError("区间输入输出不得重叠或使用内部槽")
        if not 0 <= low <= high:
            raise ValueError("自然数区间要求 0<=下界<=上界")
        return seq(
            self.constant(lower, low), self.constant(upper, high), self.constant(result, 0),
            self.compare(value, lower, lt, eq, gt),
            self.if_zero(self.read(lt), seq(self.compare(value, upper, lt, eq, gt),
                         self.if_zero(self.read(gt), self.constant(result, 1)))),
        )

    def decode_integer(self, magnitude, sign):
        """用 ``@input`` 读取任意有符号整数，保存幅值和符号位。

        输入槽 ``magnitude`` 与 ``sign`` 必须互异且不得占用四个解码 scratch
        槽。结果满足 magnitude>=0、sign∈{0,1}，且零的符号规范化为 0。
        解码会对有限个内部原始槽地址作别名保护，不枚举整个保留地址区间。
        标准 ``@input`` 的解析异常和 EOF 不会被本宏捕获。
        """
        p, q, k, run = (self.slot(name) for name in ("解码P", "解码Q", "解码步数", "解码继续"))
        if len({magnitude, sign, p, q, k, run}) != 6:
            raise ValueError("解码结果不得覆盖内部槽或彼此覆盖")

        def select_raw(slot):
            return f"&0 ^1 &{slot} ^5 &{slot} ^1"

        def put_raw(slot, expression):
            return f"{select_raw(slot)} {expression} ^5"

        def finish(expression, negative):
            return seq(self.put(magnitude, expression), self.constant(sign, negative), self.constant(run, 0))

        def advance(slot, operation):
            probe = self.read(slot) + " " + operation
            guards = []
            for address in (p, q):
                # 命中原始值槽前已知原输入为负；用步数恢复其幅值。
                recover = seq(self.constant(magnitude, -address),
                              self.add_into(magnitude, k) if operation == "@+" else self.subtract_from(magnitude, k),
                              self.constant(sign, 1), self.constant(run, 0))
                guards.append(self.once(self.read(run), self.if_zero(
                    probe + " " + "@+ " * -address, recover)))
            return seq(*guards, self.once(self.read(run), seq(
                f"&0 ^1 &{slot} ^5 &{slot} *1 {operation} ^5",
                self.if_zero(self.read(slot), finish(self.read(k), int(operation == "@+"))),
            )))

        race = seq(
            put_raw(q, self.read(p)), self.constant(magnitude, 0), self.constant(sign, 0),
            self.constant(k, 0), self.constant(run, 1),
            self.if_zero(self.read(p), self.constant(run, 0)),
            self.loop(self.read(run), seq(self.change(k, "@+"), advance(p, "@-"),
                                         self.once(self.read(run), advance(q, "@+")))),
            put_raw(q, "&0"),
        )
        ordinary = seq(
            self.constant(magnitude, -q), self.read(p) + " " + "@+ " * -q,
            "[", race, "&0", "]",
            put_raw(p, "&0"), select_raw(p),
        )
        return seq(
            self.constant(magnitude, -p), self.constant(sign, 1),
            select_raw(p), "@input ^5", self.read(p) + " " + "@+ " * -p,
            "[", ordinary, "&0", "]",
            # 两条路径均以 memory[0]=P、memory[P]=P 汇合，再统一清空。
            "&0 ^2 &0 ^1",
        )

    def subtract_from(self, destination, source):
        """执行自然数 ``destination -= source``，保留来源。

        前置条件为 destination>=source；两槽不得与内部倒数槽别名。
        算法按 source 大小递减，适合小差值的一般场景。
        """
        counter = self.slot("减法计数")
        if counter in (destination, source):
            raise ValueError("减法参数不能使用内部计数槽")
        return seq(self.copy(counter, source), self.loop(self.read(counter), seq(
            self.change(destination, "@-"), self.change(counter, "@-"))))

    def add_into(self, destination, source):
        """执行自然数 ``destination += source``，保留来源。

        允许两参数同槽（此时按原值加到自身）；两参数不得占用内部 scratch
        槽。工作量与 source 的值成正比。
        """
        counter = self.slot("加法计数")
        if counter in (destination, source):
            raise ValueError("加法参数不能使用内部计数槽")
        return seq(
            self.copy(counter, source),
            self.loop(self.read(counter), seq(self.change(destination, "@+"), self.change(counter, "@-"))),
        )

    def multiply_by_ten(self, value):
        """原位乘以常数 10；使用具名计数槽，不使用宿主整数计算输入。"""
        counter = self.slot("乘十计数")
        return seq(
            self.copy(counter, value), self.constant(value, 0),
            self.loop(self.read(counter), seq(
                *(self.change(value, "@+") for _ in range(10)),
                self.change(counter, "@-"),
            )),
        )

    def divmod_unsigned(self, numerator, denominator, quotient, remainder):
        """计算自然数商和余数，要求分子>=0、分母>0。

        输入保留，结果槽必须不同，所有四个参数都不能覆盖内部工作槽。
        重复减法构造通用版本，因此工作量与 numerator 成正比；不适合把
        该宏误认为机器除法。
        """
        work, divisor, countdown = (self.slot(name) for name in ("除法工作", "除法分母", "除法倒数"))
        if {work, divisor, countdown} & {numerator, denominator, quotient, remainder}:
            raise ValueError("除法参数不能使用内部工作槽")
        if quotient == remainder:
            raise ValueError("商和余数必须使用不同槽位")
        step = seq(
            self.change(work, "@-"), self.change(remainder, "@+"), self.change(countdown, "@-"),
            self.if_zero(self.read(countdown), seq(
                self.constant(remainder, 0), self.change(quotient, "@+"), self.copy(countdown, divisor),
            )),
        )
        return seq(
            self.copy(work, numerator), self.copy(divisor, denominator), self.copy(countdown, divisor),
            self.constant(quotient, 0), self.constant(remainder, 0),
            self.loop(self.read(work), step),
        )

    def print_unsigned_decimal(self, value):
        """逐位用字符 I/O 输出自然数十进制表示，不调用整数 ``@print``。

        输入槽保留。宏占用具名输出工作槽，输出不附加换行；调用者自行
        输出所需分隔符。位权通过重复除以 10 构造，成本随数值幅值增长。
        """
        number, scale, probe, ten, q, r = (self.slot(name) for name in (
            "输出数值", "输出位权", "输出探测", "常数十", "输出商", "输出余数",
        ))
        scale_step = seq(
            self.divmod_unsigned(probe, ten, q, r), self.copy(probe, q),
            self.once(self.read(probe), self.multiply_by_ten(scale)),
        )
        digit_step = seq(
            self.divmod_unsigned(number, scale, q, r),
            self.read(q) + " " + "@+ " * 48 + "@print_as_char",
            self.copy(number, r),
            self.divmod_unsigned(scale, ten, q, r), self.copy(scale, q),
        )
        return seq(
            self.copy(number, value), self.copy(probe, value), self.constant(scale, 1), self.constant(ten, 10),
            self.loop(self.read(probe), scale_step), self.loop(self.read(scale), digit_step),
        )


def compile_program(program):
    """两遍展开程序，自动规划静态槽和动态数组起点。

    ``program`` 是接受一个 ``Macros`` 并返回 DSL 字符串的确定性生成函数。
    第一遍只发现具名静态槽；第二遍以 ``bound=槽数+3`` 重新展开，确保
    动态负地址数据区不会撞上静态槽和两个保留标记。两遍申请的槽必须完全
    相同，否则报错。返回值是已缩进、带末尾换行的 PP3 源码。
    """
    # 首遍统计全部静态槽；第二遍把动态数据区放在槽位和两个锚点之后。
    preview = Macros()
    program(preview)
    macros = Macros(bound=len(preview.slots) + 3)
    code = program(macros)
    if macros.slots != preview.slots:
        raise ValueError("两遍生成的槽位布局不同")
    return format_code(code)
