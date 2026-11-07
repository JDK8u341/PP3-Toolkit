"""可复用的动态记录堆、只追加链和双帧指令机器宏。"""

from .frames import ERROR_OUTPUT, validate_byte
from .macros import seq
from .records import Reference


class Arena:
    """具有永久零头和可配置字段数的动态记录堆。

    节点地址总是零或一个零头；``field`` 从 1 开始。数值载荷和引用都
    存在同一物理字段区，但必须分别调用 ``put(..., reference=False)`` 或
    ``link``，因为 PP3 需要不同的间接路由深度。``allocate`` 假定新区域
    从未使用，因此依赖默认内存零值，不主动逐字段清零。

    一个 ``Macros`` 实例只应有一个动态堆游标。若多个结构要共存，给它们
    分配不同字段或由同一 Arena 分配，不能各自创建指向相同 base 的堆。
    """

    def __init__(self, m, width=8):
        """声明宽度为 ``width`` 的记录布局；字段总数不含零头。"""
        self.m, self.width = m, width
        self.bump = m.slot("机器堆.未使用地址")

    def initialize(self):
        """生成分配游标初始化代码，首次 allocate 前执行一次。"""
        return Reference.put(self.bump, f"&{self.m.array_base}")

    def address(self, node, field):
        """生成字段地址表达式；field=0 是永久零头，禁止使用。"""
        if not 1 <= field <= self.width:
            raise ValueError("字段必须位于记录内部，不能覆盖零头")
        return self.m.read(node) + " " + "@- " * field

    def read(self, node, field):
        """读取记录字段，不改变 node 引用。"""
        return self.address(node, field) + "~1"

    def put(self, node, field, expression, *, reference=False):
        """写入字段；reference=True 表示值为零头引用而非自然数载荷。"""
        address = self.address(node, field)
        depth = 3 if reference else 4
        return f"&0 ^1 {address} ^{depth} {address} ^1 {expression} ^{depth}"

    def link(self, node, field, target):
        """把字段设为另一个节点引用。"""
        return self.put(node, field, self.m.read(target), reference=True)

    def allocate(self, node):
        """分配一个新零头记录并把其引用存入 node 工作槽。"""
        if node == self.bump:
            raise ValueError("分配结果不能覆盖分配游标")
        # 新区域从未写入，全部字段已隐式为零；分配只移动零头引用。
        bump = self.bump
        return seq(Reference.copy(node, bump),
                   f"&0 ^1 &{bump} ^3 &{bump} *1 " + "@- " * (self.width + 1) + "^3")

    def follow(self, destination, source, field):
        """令 destination 指向 source.field；支持 destination 与 source 同槽。"""
        if destination == source:
            # 先交换取出旧引用；普通赋值会先把该控制槽改成自环。
            self.address(source, field)
            return f"&0 ^1 &{source} ^3 &{source} *1 " + "@- " * field + "~1 ^3"
        return Reference.put(destination, self.read(source, field))


class Chain:
    """由 Arena 节点组成、可共享引用的只追加链。

    默认后继字段是 8；创建链时可指定其它引用字段。链不拥有或销毁节点，
    ``append`` 只改写前驱边和头尾。遍历通过 ``advance(pointer)`` 更新游标，
    不拆除节点间边，适用于字节缓冲、AST/指令流和索引链。
    """

    def __init__(self, arena, name, next_field=8):
        """声明独立头尾控制槽；next_field 必须是可存引用的记录字段。"""
        self.heap, self.m, self.next_field = arena, arena.m, next_field
        self.head, self.tail = (self.m.slot(f"{name}.{part}") for part in ("表头", "表尾"))

    def append(self, node):
        """把现有节点挂到尾部；调用方负责节点生命周期和链不成环约束。"""
        if node in (self.head, self.tail):
            raise ValueError("追加节点不能覆盖链表控制槽")
        return seq(self.m.if_nonzero(
            self.m.read(self.tail), self.heap.link(self.tail, self.next_field, node),
            Reference.copy(self.head, node)), Reference.copy(self.tail, node))

    def advance(self, pointer):
        """沿后继字段前进一步，安全支持游标与来源槽相同。"""
        return self.heap.follow(pointer, pointer, self.next_field)


class InstructionMachine:
    """基于 Arena/Chain 的平坦指令表与括号配对宏。

    字段约定：1=操作码、2/3=可选自然数参数、4=括号配对、5=暂存括号栈
    前驱、8=代码后继。括号配对字段和运行后继彼此独立，因此运行器可以
    直接跳转，同时保留线性代码遍历。

    这是构造器而非宿主解释器：``emit`` 和 ``run`` 只返回 DSL。指令语义
    由调用者提供 ``dispatch`` 代码；栈错误写入 error 槽，由外层选择输出。
    """

    def __init__(self, m):
        """创建共享指令记录堆、代码链、数据链和运行控制槽。"""
        self.m, self.heap = m, Arena(m)
        self.code, self.data = Chain(self.heap, "客体代码"), Chain(self.heap, "客体输入")
        (self.node, self.stack, self.pc, self.active, self.opcode, self.input) = (
            m.slot(f"机器.{part}") for part in ("节点", "括号栈", "PC", "当前指令", "操作码", "输入游标"))

    def emit(self, opcode, error, opening, closing, magnitude=None, sign=None):
        """在编译期生成一条记录并执行对应的括号栈配对逻辑。

        opening/closing 是立即数操作码。可选参数引用的是存放自然数的槽，
        不是 Python 值；此函数只在编译期静态展开。
        """
        m, heap, node = self.m, self.heap, self.node
        pair = seq(heap.link(node, 4, self.stack), heap.link(self.stack, 4, node),
                   heap.follow(self.stack, self.stack, 5))
        return seq(
            heap.allocate(node), heap.put(node, 1, m.read(opcode)),
            heap.put(node, 2, m.read(magnitude)) if magnitude is not None else "",
            heap.put(node, 3, m.read(sign)) if sign is not None else "",
            self.code.append(node),
            m.if_zero(m.read(opcode) + " " + "@- " * opening, seq(
                heap.link(node, 5, self.stack), Reference.copy(self.stack, node))),
            m.if_zero(m.read(opcode) + " " + "@- " * closing,
                      m.if_nonzero(m.read(self.stack), pair, m.constant(error, 1))),
        )

    def code_end(self, error):
        """在源码加载结束时，将未闭合左括号报告到 error 槽。"""
        return self.m.once(self.m.read(self.stack), self.m.constant(error, 1))

    def data_char(self, char):
        """生成一个输入字节记录并追加至机器数据链。"""
        return seq(self.heap.allocate(self.node), self.heap.put(self.node, 1, self.m.read(char)),
                   self.data.append(self.node))

    def jump_after_pair(self):
        """将 PC 移到当前括号配对节点的后继。"""
        return seq(self.heap.follow(self.pc, self.active, 4), self.code.advance(self.pc))

    def run(self, error, initialize, dispatch):
        """生成顺序取指循环，逐条调用静态 ``dispatch`` 片段。

        initialize 在 PC/输入游标设好后执行一次。dispatch 必须读取当前
        opcode 槽，并按应用自定语义修改机器状态；error 变为非零时循环
        停止，之后输出固定 ``ERROR\\n``。空代码链自然不执行循环体。
        """
        m = self.m
        return seq(
            Reference.copy(self.pc, self.code.head), Reference.copy(self.input, self.data.head), initialize,
            m.loop(m.read(self.pc), seq(
                Reference.copy(self.active, self.pc),
                m.put(self.opcode, self.heap.read(self.active, 1)), self.code.advance(self.pc), dispatch,
                m.once(m.read(error), Reference.put(self.pc, "&0")),
            )), m.once(m.read(error), ERROR_OUTPUT),
        )


def literal(text):
    """将生成期固定文本展开为逐字节 ``&n @print_as_char`` 指令。"""
    return " ".join(f"&{ord(char)} @print_as_char" for char in text)


def dual_frame(m, prepare, code_char, code_end, data_char, finish):
    """读取源码/数据双帧并在完整验证后执行调用者生成的 DSL。

    先用两次 ``@input`` 读取非负源码长度 c、数据长度 d，再连续读取 c+d
    个字符码点；源码和数据之间不插入分隔符，补回 LF 计入相应帧长。
    所有码点须为 0..255。两个长度为负或完整帧出现超范围码点时输出
    ``ERROR\\n``；帧提前 EOF 与整数解析错误原样传播。

    ``prepare(m, error)`` 建立所需结构，``code_char(m, char, error)`` 处理
    每个源码字节，``code_end(m, error)`` 检查源码结束条件，
    ``data_char(m, char, error)`` 加载输入字节，``finish(m, error)`` 返回
    成功加载后的执行程序。错误源码/帧仍会消费剩余两个帧，以维持协议边界。
    """
    code_length, data_length, code_sign, data_sign, left, char, error = (
        m.slot(f"双帧.{part}") for part in (
            "源码长度", "数据长度", "源码负号", "数据负号", "剩余", "字符", "错误"))
    initialization = prepare(m, error)
    code_step, end, data_step, execution = (
        code_char(m, char, error), code_end(m, error),
        data_char(m, char, error), finish(m, error))

    def load(length, body):
        return seq(m.copy(left, length), m.loop(m.read(left), seq(
            m.put(char, "@input_as_char"),
            m.if_zero(m.read(error), seq(validate_byte(m, char, error),
                                        m.if_zero(m.read(error), body))),
            m.change(left, "@-"))))

    return seq(
        m.decode_integer(code_length, code_sign), m.decode_integer(data_length, data_sign),
        m.if_nonzero(m.read(code_sign), m.constant(error, 1)),
        m.if_nonzero(m.read(data_sign), m.constant(error, 1)),
        m.if_nonzero(m.read(error), ERROR_OUTPUT, seq(
            initialization, load(code_length, code_step),
            m.if_zero(m.read(error), end), load(data_length, data_step),
            m.if_nonzero(m.read(error), ERROR_OUTPUT, execution))),
    )
