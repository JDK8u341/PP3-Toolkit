"""零头记录、链表所有权与稳定归并排序的静态 DSL 宏。"""

from .macros import seq


class Reference:
    """零或永久零头地址的路由操作。

    这些方法处理的是**引用**，而不是自然数载荷。引用被存进静态控制槽，
    必须使用较浅路由深度；误用 ``Macros.put`` 会把负地址继续当作普通值
    路由，可能覆盖锚点或写错节点。
    """

    @staticmethod
    def put(slot, expression):
        """把一个零/零头引用写入静态槽。表达式必须产生有效引用。"""
        return f"&0 ^1 &{slot} ^3 &{slot} ^1 {expression} ^3"

    @staticmethod
    def copy(destination, source):
        """复制引用；同槽复制是空操作。"""
        return "" if destination == source else Reference.put(destination, f"&{source} ~1")

    @staticmethod
    def next(slot):
        """读取常见三字段记录的 NEXT 字段并更新引用槽。"""
        return f"&0 ^1 &{slot} ^3 &{slot} *1 @- @- @- ~1 ^3"

    @staticmethod
    def bump(slot):
        """将记录分配游标向低地址推进四个单元。"""
        return f"&0 ^1 &{slot} ^3 &{slot} *1 @- @- @- @- ^3"


class RecordHeap:
    """四单元步长的零头记录堆。

    每个节点布局为 ``[head=0, magnitude, sign, next]``；载荷字段是自然数，
    ``next`` 是零/节点引用。``initialize`` 将游标设到 ``Macros.array_base``，
    每次分配向更低地址移动四格。永久零头永不写载荷。

    这是固定三字段布局的便捷抽象；需要更多字段或其它类型约定时用
    ``Arena(width=...)``。同一生成过程中的列表和记录应共享一个 heap。
    """
    MAGNITUDE = 1
    SIGN = 2
    NEXT = 3

    def __init__(self, macros):
        """绑定该记录堆使用的宏上下文，并声明分配游标槽。"""
        self.m = macros
        self.bump = macros.slot("记录堆.未使用地址")

    def initialize(self):
        """生成游标初始化代码，必须在首次分配前执行。"""
        return Reference.put(self.bump, f"&{self.m.array_base}")

    def field_address(self, reference, field):
        """生成记录字段地址；不能选择永久零头字段 0。"""
        if field not in (self.MAGNITUDE, self.SIGN, self.NEXT):
            raise ValueError("永久零头不可写")
        return self.m.read(reference) + " " + "@- " * field

    def read(self, reference, field):
        """读取数值载荷或引用字段。"""
        return self.field_address(reference, field) + "~1"

    def put(self, reference, field, expression):
        """写入字段；NEXT 用引用写入路由，其余字段按自然数载荷处理。"""
        address = self.field_address(reference, field)
        depth = 3 if field == self.NEXT else 4
        return f"&0 ^1 {address} ^{depth} {address} ^1 {expression} ^{depth}"

    def allocate(self, node, magnitude, sign):
        """分配并初始化节点；载荷与分配/节点控制槽必须互异。"""
        if len({node, magnitude, sign, self.bump}) != 4:
            raise ValueError("分配器、节点引用和载荷必须使用不同槽")
        return seq(
            Reference.copy(node, self.bump), Reference.bump(self.bump),
            self.put(node, self.MAGNITUDE, self.m.read(magnitude)),
            self.put(node, self.SIGN, self.m.read(sign)), self.put(node, self.NEXT, "&0"),
        )


class RecordList:
    """由独立头尾引用管理的线性链。

    ``append`` 将节点所有权转入链；节点必须已分配且不在其它链中。
    ``pop`` 返回首节点并切断它的 NEXT，之后才可追加到另一条链。
    ``concat`` 常数次改写引用，把另一链的全部节点所有权转给本链并清空
    来源头尾。不能对共享节点或不同 heap 的链拼接。
    """

    def __init__(self, heap, name):
        self.heap = heap
        self.m = heap.m
        self.head = self.m.slot(f"{name}.表头")
        self.tail = self.m.slot(f"{name}.表尾")

    def _check_node(self, node):
        if node in (self.head, self.tail):
            raise ValueError("节点工作引用不能覆盖头尾")

    def append(self, node):
        """追加现有节点并更新尾引用。"""
        self._check_node(node)
        return seq(self.m.if_nonzero(
            self.m.read(self.tail), self.heap.put(self.tail, RecordHeap.NEXT, self.m.read(node)),
            Reference.copy(self.head, node)), Reference.copy(self.tail, node))

    def pop(self, node):
        """弹出首节点到工作引用，并断开其后继。"""
        self._check_node(node)
        return seq(
            Reference.copy(node, self.head), Reference.next(self.head),
            self.m.if_zero(self.m.read(self.head), Reference.put(self.tail, "&0")),
            self.heap.put(node, RecordHeap.NEXT, "&0"),
        )

    def concat(self, other):
        """拼接同堆的另一条不相交链，并转移其所有权。"""
        if self.heap is not other.heap or {self.head, self.tail} & {other.head, other.tail}:
            raise ValueError("拼接要求同堆、不同控制槽和互不重叠的节点所有权")
        join = seq(self.m.if_nonzero(
            self.m.read(self.tail), self.heap.put(self.tail, RecordHeap.NEXT, self.m.read(other.head)),
            Reference.copy(self.head, other.head)), Reference.copy(self.tail, other.tail))
        return seq(self.m.once(self.m.read(other.head), join),
                   Reference.put(other.head, "&0"), Reference.put(other.tail, "&0"))


def merge_sort(m, source, length, name="归并"):
    """稳定地按记录 MAGNITUDE 字段对链表做自底向上归并排序。

    ``source`` 必须使用同一 ``Macros`` 对象拥有的 ``RecordHeap``。节点
    载荷为任意自然数，不按字节值域分桶；相同键优先取左段，保持稳定性。
    调用结束时排序结果回到 source，所有临时链头尾清空，节点集合保持不变。
    比较使用通用 ``Macros.compare``：空间为常数级，但比较的 DSL 执行成本
    仍可能随载荷数值幅值增长。
    """
    heap = source.heap
    output, left, right = (RecordList(heap, f"{name}.{part}") for part in ("输出", "左段", "右段"))
    width, count, node, run, a, b, lt, eq, gt = (m.slot(f"{name}.{part}") for part in (
        "段长", "截取剩余", "转移节点", "继续", "左值", "右值", "小于", "等于", "大于"))

    def split(target):
        return seq(m.copy(count, width), m.conjunction(count, source.head, run),
                   m.loop(m.read(run), seq(source.pop(node), target.append(node),
                          m.change(count, "@-"), m.conjunction(count, source.head, run))))

    def take(target):
        return seq(target.pop(node), output.append(node))

    merge = seq(
        m.conjunction(left.head, right.head, run),
        m.loop(m.read(run), seq(
            m.put(a, heap.read(left.head, RecordHeap.MAGNITUDE)),
            m.put(b, heap.read(right.head, RecordHeap.MAGNITUDE)), m.compare(a, b, lt, eq, gt),
            # 相等时取左段，保持相同载荷节点的原始先后次序。
            m.if_nonzero(m.read(gt), take(right), take(left)),
            m.conjunction(left.head, right.head, run),
        )), output.concat(left), output.concat(right),
    )
    one_pass = seq(
        m.loop(m.read(source.head), seq(split(left), split(right), merge)),
        source.concat(output), m.add_into(width, width), m.compare(width, length, lt, eq, gt),
    )
    return seq(m.constant(width, 1), m.compare(width, length, lt, eq, gt),
               m.loop(m.read(lt), one_pass))
