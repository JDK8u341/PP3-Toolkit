# 示例

本目录的 Python 文件仅生成固定 PP3 源码，不读取题目输入。生成器由测试导入并交给原版 PP3 Runtime 执行。生成出的源码可以保存为 .pp3 文件，再由你选用的 PP3 前端构建和运行。

## 有符号整数加法

在仓库根目录运行：

~~~powershell
python -m examples.signed_add > signed-add.pp3
~~~

生成的 PP3 程序读取两行有符号整数并输出一行和。每个输入先用 decode_integer 拆成幅值与符号：

- 同号时相加，结果沿用共同符号。
- 异号时比较幅值，只做较大幅值减较小幅值。
- 幅值相等时输出规范化的正零。
- 结果幅值为零时不输出负号。

此例展示的是 Toolkit 的 signed-magnitude 表示和有符号加法组合，不代表比较宏的运行成本与整数位数线性，也不绕过 PP3 的标准输入解析限制。

示例输入：

~~~text
-15
6
~~~

输出：

~~~text
-9
~~~

## 稳定链表归并排序

~~~powershell
python -m examples.stable_sort > stable-sort.pp3
~~~

生成的 PP3 程序先读自然数数量 n，再读 n 个非负整数，每行输出一个升序结果。每个元素分配一个独立零头记录，因此重复值和零值仍有不同节点身份。归并相等值时优先取左链，保持相同键的原始相对次序。

示例输入：

~~~text
6
7
0
7
1000
2
0
~~~

输出：

~~~text
0
0
2
7
7
1000
~~~

当前输出只打印键，不显示节点身份；稳定性由归并分支保证，若要直接观察稳定性，应为记录额外保存原始序号并在测试中核对。

## 生成、构建与执行

Python 模块输出的是 DSL 文本：

~~~powershell
python -m examples.signed_add > signed-add.pp3
~~~

Toolkit 不包含 PP3 Runtime。使用 PP3 仓库时，运行器配置应使用 IRBuilder(op_map=std_register) 和 Runtime(can_direct_addressing=False)。仓库测试会把每个示例构建成 IR，检查无直接寻址节点，并执行边界样例。

更完整的机制和前置条件见[图路由](../docs/mechanism.md)、[宏契约](../docs/macros.md)、[记录和排序](../docs/data-structures.md)及[成本模型](../docs/cost-model.md)。
