# 实现机制导览

PP3 Toolkit 是一个 **PP3 源码生成库**，不是 PP3 解释器，也不是宿主语言里的算法库。Python 在生成期拼接模板；运行期的输入、比较、数组操作和链表操作都由生成出来的 PP3 程序完成。

阅读顺序建议：

1. 本文：了解运行边界、图寻址、自然数写入和两遍槽位规划。
2. [宏与数值模型](macros.md)：理解条件、判等、比较、整数表示和算术宏的契约。
3. [数据结构](data-structures.md)：理解负地址数组、零头记录、链表与归并排序布局。
4. [帧与指令机](io-machines.md)：理解字符帧、编译期回调和括号跳转。
5. [成本模型](cost-model.md)：区分 PP3 操作量、数值相关工作量和宿主 Runtime 成本。
6. [API 参考](api.md)：按名字查参数、结果、scratch 和异常。

## 执行边界

宏方法返回 PP3 DSL 文本。Toolkit 不读取题目输入、不把运行时整数拿回 Python、不自动调用 PP3 Runtime，也不替用户选择 op_map。最小工作流如下：

~~~python
from pp3_toolkit import Macros, compile_program, seq


def make_sum(m: Macros) -> str:
    left = m.slot("示例.左值")
    right = m.slot("示例.右值")
    return seq(
        m.put(left, "@input"),
        m.put(right, "@input"),
        m.add_into(left, right),
        m.read(left) + " @print",
    )


source = compile_program(make_sum)
print(source, end="")
~~~

source 是普通 PP3 源码。要运行它，仍需安装/检出 PP3，并按目标环境构造 IRBuilder(op_map=std_register) 和 Runtime(can_direct_addressing=False)。Toolkit 的测试子模块是固定版本，只用于本仓库测试，不是安装此包的运行依赖。

更复杂的完整示例见 [有符号加法](../examples/signed_add.py) 与 [稳定排序](../examples/stable_sort.py)。前者把有符号整数表示为幅值与符号位；后者以记录身份排序重复自然数。

## PP3 的函数图模型

把内存视为整数地址到整数内容的函数：

~~~
f(a) = memory[a]
~~~

每个地址是一个节点，内存内容是从该节点出发的一条有向边。对当前 view 执行深度为 d 的间接操作时，先计算位置：

~~~
place = f^(d-1)(view)
~~~

随后操作目标是 memory[place]：

| 操作 | 效果 |
| --- | --- |
| ~d | 读取 memory[place] 到 view |
| ^d | 将当前 view 写入 memory[place] |
| *d | 交换当前 view 与 memory[place] |

直接寻址会直接指定目标位置；Toolkit 的路由模板只依赖 PP3 的间接操作。&n 设置 view=n，但设置 view 不等于读写地址 n：后续间接操作还会沿 f 走若干边。

最简单的静态自然数槽读取是 &槽地址 ~1。因为 ~1 的目标位置就是当前 view，所以它读取 memory[槽地址]。若槽保存的是记录引用而不是自然数载荷，取到地址后还要按字段偏移继续路由；这也是 Toolkit 区分“数值槽”和“引用槽”的原因。

原始推导和有限图验证见 [PP3-Lab 图模型](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/01-graph-model.md)、[局部标记](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/02-address-marking.md)和[验证方法](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/06-validation.md)。下面把 Toolkit 实际依赖的不变量重新写出，链接不是本地解释的替代品。

## 为什么自然数赋值使用深度 4

Toolkit 的普通静态数据槽位于负地址 X <= -3，槽中只存自然数。两个保留位置 -1、-2 必须保持零：

~~~
memory[-1] = 0
memory[-2] = 0
~~~

自然数 v 可沿图在有限两步内到达零：

- v=0 时已经位于零。
- v>0 且 memory[v]=0 时，一步到零。
- 若正地址 v 当前被集合/判等标记，则 v -> -1 -> 0 或 v -> -2 -> 0。

因此自然数载荷的最大路由高度是 h=2。把新值写入槽 X 的模板是：

~~~text
&0 ^1
&X ^4
&X ^1
表达式 ^4
~~~

Macros.put(X, expression) 正是这四阶段模板，公式为 D=h+2=4：

1. &0 ^1 把 memory[0] 清为零，令零成为暂时的吸收点。
2. &X ^4 从 X 沿旧值路径到零，并把 X 写到 memory[0]。旧槽内容即使为零或被标记，路径仍在深度 4 时落到零。
3. &X ^1 建立 memory[X]=X，让目标槽在后续路由中自环。
4. expression ^4 计算新自然数，并将它写入 memory[X]。新值先到零，再经 memory[0]=X 到达目标；若提前到达 X，则由 X 的自环吸收多余深度。

表达式必须只产生新载荷。它不能依赖被覆盖的目标旧值，不能改写零锚点/目标路径，也不能在临时路由尚未结束时调用另一个会改写同一路径的写宏。完成后 memory[0] 可以仍指向 X；下一次普通写模板会重新建立自己的路由。持久不变量是 memory[-1] 和 memory[-2]，并非 memory[0] 永远为零。

原位自增/自减不能先覆盖旧值；Macros.change 用 *1 交换旧槽值到 view，再在建立的自环下执行 @+ 或 @-，最后经深度 4 写回。自减只有在旧值大于零时才保持自然数不变量，宏不会动态检查这个条件。

这个证明依赖受限内存分区，不能外推为“任意 PP3 图上都能安全赋值”。Lab 中的正自环反例和图高边界见[局部标记文档](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/02-address-marking.md)。

## 为什么引用写入使用深度 3

引用槽存放 0 或永久零头记录地址 R。记录头满足 memory[R]=0，所以引用最多一步到零，不需要自然数载荷所需的两步路径。

~~~text
&0 ^1
&P ^3
&P ^1
表达式 ^3
~~~

对引用槽 P，深度 3 可先把 P 锚定到零，再建立 P 自环，然后把零或记录头地址写入 P。Reference.put、Arena.link 和记录的 NEXT 写入使用这一路由。

不要把引用交给 Macros.put：它按任意自然数载荷的高度使用深度 4。也不要把普通自然数载荷交给 Reference.put：它假设新值是零或零头，路径高度不满足前置条件。Python 类型系统不会阻止这种误用；数值与引用是程序层面的两种表示约定。

## 静态槽与动态地址区

Macros.slot(name) 为同一名字返回稳定地址；新名字依次获得 -3, -4, -5, ...。-1、-2 保留给图标记。槽名是布局身份，不是运行时变量名；同名请求必然别名。

数组和记录需要在静态控制槽以外使用负地址。compile_program(generator) 为此生成两遍：

1. 创建预览 Macros，调用生成器并收集所有通过 slot() 声明的名字。
2. 若共收集到 N 个名字，创建 bound=N+3 的正式 Macros。静态槽最大地址幅值为 N+2，动态区从 -N-3 开始，和静态区相邻但不重叠。
3. 再调用生成器，核对两遍的 name -> address 字典完全相同。
4. 用 format_code() 缩进独立括号行并检查括号配对，返回带末尾换行的源码。

例如 N=6 时，静态槽是 -3..-8，动态区起点为 -9。NegativeArray 的后续元素和 Arena 记录从更负地址增长。

两遍构造是生成期行为。生成函数和回调会被调用两次，必须确定、无 I/O、无依赖调用次数的外部副作用。实现只比较槽名映射，不比较两次完整源码；因此随机生成内容、根据外部状态生成不同代码、或者依赖调用次数的副作用仍然是调用方错误。宏若手写 &-100 之类地址，也不会自动登记，必须自行保证不与静态槽或动态区冲突。

不要在生成器执行时读取待解题目的输入。输入只应出现在返回的 DSL 中，例如 m.put(slot, "@input")。

## 标量、引用、记录字段的三类路由

| 数据类别 | 典型内容 | 路由深度 | 对应 API |
| --- | --- | ---: | --- |
| 自然数标量 | 数量、索引、幅值、字符码点 | 4 写入 | Macros.put/constant/change |
| 零头引用 | 0 或记录头地址 | 3 写入 | Reference.put/copy/next |
| 记录内字段 | 由记录头和固定偏移计算出的地址 | 数值字段 4、引用字段 3 | RecordHeap.put、Arena.put/link |

读取数值字段和读取引用字段在物理上都从 memory[address] 得到整数；差异在后续如何路由、如何改写。一个错误深度可能静默覆盖错误的图节点，因此每个数据结构 API 都要求调用者遵守字段类型约定。

## 实现承诺与不承诺

- 不改变 PP3 语义：生成文本由所选 PP3 IRBuilder 和 Runtime 解析、执行。
- 不使用直接寻址：模板通过 view 和间接深度路由；测试检查 IR 中没有直接内存寻址节点。
- 不做隐式静态类型检查：Python 的整数槽地址无法区分数值、引用或逻辑布尔值。
- 不自动证明别名安全：部分显然冲突会抛 ValueError，但所有宏的 scratch 与数据结构所有权不能完全静态验证。
- 不保证任意错误前置条件产生友好错误：例如除数为零、自然数自减下溢、错误链表所有权可能让生成程序进入不正确状态或不终止。
- 不声称运行时间与宿主机器整数运算相当。请读[成本模型](cost-model.md)。

## 实验依据

本仓库的端到端测试用固定 PP3 子模块运行生成源码，配置为 IRBuilder(op_map=std_register)、Runtime(can_direct_addressing=False)。测试适合发现实现回归，不构成对无限内存、无限执行时间或所有可能图状态的形式验证。

需要继续追踪数学推导时，可从 [PP3-Lab 的比较文档](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/03-comparison.md)、[验证与成本模型](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/06-validation.md)和[链表/记录实验](https://github.com/JDK8u341/PP3-Lab/blob/main/docs/07-linked-records.md)开始。
