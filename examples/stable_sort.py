"""生成非负整数稳定链表归并排序器的 PP3 源码。"""

from pp3_toolkit import Macros, RecordHeap, RecordList, compile_program, merge_sort, seq


def stable_sort(m: Macros) -> str:
    """读取数量与自然数载荷，逐行输出升序序列。"""
    heap = RecordHeap(m)
    values = RecordList(heap, "数据")
    count, remaining, value, sign, node = (m.slot(name) for name in (
        "元素数", "剩余数", "载荷", "零符号", "节点",
    ))
    return seq(
        heap.initialize(), m.put(count, "@input"), m.copy(remaining, count),
        m.loop(m.read(remaining), seq(
            m.put(value, "@input"), m.constant(sign, 0),
            heap.allocate(node, value, sign), values.append(node),
            m.change(remaining, "@-"),
        )),
        merge_sort(m, values, count),
        m.loop(m.read(values.head), seq(
            values.pop(node), heap.read(node, RecordHeap.MAGNITUDE) + " @print",
        )),
    )


if __name__ == "__main__":
    print(compile_program(stable_sort), end="")
