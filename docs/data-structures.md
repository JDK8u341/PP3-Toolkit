# 数据结构

本文解释 Toolkit 的动态负地址区域如何映射到数组、记录、链表和排序。所有结构都是 DSL 模板；Python 对象只记住生成期的槽号和配置，不承载运行期节点或数组内容。

## 动态区规划

compile_program 收集全部静态槽后，动态数据区从负方向紧接静态槽区。若静态槽数为 N，则动态基址为 -N-3；槽地址从 -3 到 -N-2，-1/-2 保留给图标记。

数组元素或记录头占据动态负地址。没有显式释放 API；默认内存值为零，新建记录可利用此性质。程序不能假设两个独立分配器会自动获得不同区域。

特别注意：NegativeArray 实例各自有游标槽，但都从同一个 macros.array_base 开始；多个数组会互相覆盖。RecordHeap 和 Arena 也各自从该基址启动，不能与其他堆分配器混用。一个程序若需要多条链，应共享同一个 RecordHeap/Arena，通过不同链头管理同一堆内的节点。

## NegativeArray：连续自然数带

若动态基址为 B，数组元素地址定义为：

~~~text
element(i) = B - i,  i >= 0
~~~

数组对象只申请一个静态自然数游标 P：

- reset() 令 P=B。
- advance() 令 P=P-1。
- read() 读取 memory[P]。
- put(expr) 将自然数 expr 写入 memory[P]。
- seek(index) 从 B 开始前进运行时 index 次。

最小示例：

~~~python
from pp3_toolkit import Macros, NegativeArray, compile_program, seq


def make_array_demo(m: Macros) -> str:
    data = NegativeArray(m, "demo.array")
    value, count = m.slot("demo.value"), m.slot("demo.count")
    return seq(
        data.reset(),
        m.constant(value, 12), data.put(m.read(value)), data.advance(),
        m.constant(value, 0), data.put(m.read(value)), data.advance(),
        m.constant(value, 99), data.put(m.read(value)),
        data.reset(), m.constant(count, 3),
        m.loop(m.read(count), seq(
            data.read() + " @print",
            data.advance(),
            m.change(count, "@-"),
        )),
    )


source = compile_program(make_array_demo)
~~~

输出依次为 12、0、99。零是有效元素，数组不使用零作为结束符。必须显式保存数量，或使用另一个经证明会归零的条件。

put(expression) 会重路由当前目标，表达式不能读取当前元素旧值。要修改已有元素，请使用 change("@+")/change("@-")，或先读入独立工作槽再写回。游标、索引计数、表达式来源和业务状态应使用不同槽；seek 只检查 index 是否与其内部计数槽/游标相同。

## 引用与零头

设一个节点的头地址为 R：

~~~text
memory[R] = 0       永久零头
memory[R-1] = field 1
memory[R-2] = field 2
...
~~~

头字段恒为零，使记录地址本身可作为安全引用：沿一条边 R -> 0 到达零锚点。引用槽保存 0 或 R；数值载荷则是普通自然数。读字段时先从引用得到 R，再按字段编号递减地址。

引用写入深度为 3，自然数载荷写入深度为 4。二者数值在运行器里都只是 Python 整数，但路由不变量不同；不要交换两种写入 API。完整证明见[实现机制](mechanism.md)。

## RecordHeap：幅值、符号和 NEXT

RecordHeap 固定 stride=4：

| 节点相对地址 | 含义 | 类型 |
| --- | --- | --- |
| R | 零头 | 必须为 0 |
| R-1 | MAGNITUDE | 自然数 |
| R-2 | SIGN | 0/1 |
| R-3 | NEXT | 0 或记录头引用 |

负整数由 MAGNITUDE 与 SIGN 分开保存，数学值为 SIGN=1 时的负幅值。独立头地址表示节点身份，因此两个载荷都为 7 的记录仍然不同，零载荷也不是空节点。

RecordHeap.initialize() 将 bump 引用设为 B=array_base。allocate(node, magnitude, sign) 的顺序为：

1. 将当前 bump 复制为 node，即新节点头 R。
2. bump 向负方向移动 4 格，为下一节点准备地址。
3. 将幅值、符号和 NEXT=0 写入节点字段。

因此第 i 个分配节点位于 B-4i。分配不逐项清零未用内存；首次使用该地址是前置条件。不要对同一运行时重复执行 initialize 后还保留之前的节点引用。

RecordHeap 的 allocate 会检查 node、magnitude、sign、bump 四个槽互异；它不会检查幅值确实非负或符号确实为 0/1。

## RecordList：带所有权的可变链

RecordList 用两个引用槽 head 和 tail 表示线性链：

~~~text
空链: head=0, tail=0
非空: head=首节点, tail=尾节点, tail.NEXT=0
~~~

### 追加

若链非空，写 tail.NEXT=node；若为空，head=node。两种情况下最后 tail=node。宏只改几个引用，不沿链扫描。

前置条件：node 是同堆中有效的非零节点、当前 NEXT 为零，且不属于另一条仍活动的链。append 不会检查这些条件。重复追加同一节点可能制造自环。

### 弹出

pop(work) 将 head 复制到 work，将 head 沿 NEXT 前移；若新 head 为零，则清 tail。最后把被弹出节点的 NEXT 清零，使其可转移到另一个链。

前置条件：链非空；work 不得覆盖 head/tail。宏不能保证空链弹出时有意义。

### 拼接

concat(other) 将 other 的 head 接到本链 tail；若本链为空则直接接管 other。随后接管 tail 并清空 other 的 head/tail。操作不逐节点搬移。

实现只检查两链来自同一 RecordHeap 且控制槽不冲突，不会遍历检查节点集合是否相交。调用方必须保证两链不共享节点，并在拼接后把 other 当成空链，不再依赖已转移的所有权。

## Arena 与 Chain

Arena(width=W) 使用 stride=W+1：

~~~text
node(i) = B - i * (W + 1)
field(node, j) = node - j,  1 <= j <= W
~~~

字段 0 是零头，不能写。allocate 复制 bump 作为节点，再把 bump 减 W+1。Arena.put 默认按自然数写字段；reference=True 或 link() 表示字段值是 0/节点地址，使用浅一层的引用路由。一个字段一旦按一种类型使用，就必须一直按该类型解释。

Chain(arena, name, next_field) 用 head/tail 槽记录引用链，append 只接已有节点，advance(pointer) 沿后继字段更新引用。Chain 本身不分配、不拥有、不释放节点；它也不检查成环或跨链共享。

通常用一套 Arena 管理多种链，给链分配不同名字和引用字段。不要创建多个 Arena 期望它们独占不同内存：当前实现的动态基址相同，bump 槽名也固定。

## 稳定链表归并排序

merge_sort(macros, source, length) 只接受由同一 Macros/RecordHeap 构造的 RecordList；按 MAGNITUDE 字段排序，不按 SIGN 排序。

算法为自底向上的链表归并：

1. 将有序段宽度设为 1。
2. 沿 source 拆出相邻的两个至多 width 长度的链到 left/right。
3. 比较两段头节点的幅值，将较小者从对应段 pop 到 output。
4. 相等时优先取 left，因此相等键保留原先相对次序。
5. 将未耗尽段拼到 output，再把 output 接回 source。
6. width 翻倍；当 width >= length 时结束。

循环不变量：每一趟开始时，source 由若干个至多 width 长度的有序段组成；每次合并把两个相邻段变成一个至多 2*width 长度的有序段；整趟结束后所有节点仍且仅属于 source。结束时临时链为空。

length 必须是运行时自然数槽，且等于实际链长。算法不会读取链长来替代该参数，也不会检测不匹配；传错长度可能导致跳过排序或错误控制宽度。空链 length=0 可直接结束。

对比按值域分桶：这里每个输入元素都是一个拥有独立身份的记录，比较任意自然数键，不需要建到最大键值的数组。排序的节点搬运为 O(n log n) 次链操作；比较宏的不等成本仍随幅值增长，整体成本见[成本模型](cost-model.md)。

## 指令表也是记录结构

InstructionMachine 在一个 Arena 中保存代码节点和输入节点。代码链与数据链共享堆，但由不同 head/tail 管理。每条指令用若干字段保存 opcode、可选参数、括号匹配和线性后继。

它采用“线性后继 + 括号配对”两类独立链接。正常执行沿 NEXT 前进；需要跳过循环体时先沿 PAIR 到配对括号，再沿 NEXT 移到其后。这样无需重写指令顺序，也无需按源码长度查找括号。

InstructionMachine 不替用户定义指令语义；dispatch 是由调用者生成的 PP3 代码。字段、括号栈和帧边界详见[帧与指令机](io-machines.md)。
