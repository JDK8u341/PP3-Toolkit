# PP3 Toolkit

PP3 Toolkit 是一组**编译期静态代码生成工具**，用于把可复用的条件、自然数运算、数组、记录、链表、帧读取和指令机器宏展开为 PP3 DSL。生成出的程序仍由 PP3 自己执行；本包不实现 Runtime、不改写语言语义、不调用 cup，也不把题目输入交给 Python。

当前版本 0.1.0，支持 Python 3.10 及以上。运行时依赖为零；包不要求安装 PP3。PP3 仅作为测试子模块用于端到端验证。

## 安装

从 GitHub 仓库直接安装（pip 会从源码构建 wheel）：

~~~powershell
python -m pip install "pp3-toolkit @ git+https://github.com/JDK8u341/PP3-Toolkit.git@main"
~~~

开发时也可以从克隆目录 editable 安装：

~~~powershell
python -m pip install -e .
~~~

从本地克隆目录构建 wheel 并安装：

~~~powershell
python -m pip wheel . --no-deps --wheel-dir dist
python -m pip install dist/pp3_toolkit-0.1.0-py3-none-any.whl
~~~

GitHub Actions 的测试工作流也会构建 wheel，并将其作为短期 Actions artifact 保存；本项目目前不发布到 PyPI。

## 快速开始

生成一个读取两个非负整数并输出和的 PP3 程序：

~~~python
from pp3_toolkit import Macros, compile_program, seq


def make_sum(m: Macros) -> str:
    left, right = m.slot("sum.left"), m.slot("sum.right")
    return seq(
        m.put(left, "@input"),
        m.put(right, "@input"),
        m.add_into(left, right),
        m.read(left) + " @print",
    )


source = compile_program(make_sum)
print(source, end="")
~~~

Python 只展开固定宏模板。source 是 PP3 源码。要运行它，仍需 PP3 项目本身：

~~~python
from src.pp3 import IRBuilder, Runtime, std_register

ir = IRBuilder(op_map=std_register).build(source)
Runtime(can_direct_addressing=False).run(ir)
~~~

若使用 PP3 源码仓库本身，可从其项目根目录运行上面的导入代码。Toolkit 测试固定了 PP3 子模块版本，且会检查 IR 不包含直接寻址节点。

## 文档导航

建议首次阅读按以下顺序：

| 文档 | 内容 |
| --- | --- |
| [实现机制](docs/mechanism.md) | PP3 图模型、自然数/引用写入深度、槽位与动态区规划、生成期边界 |
| [宏与数值模型](docs/macros.md) | 条件控制流、局部标记判等、顺序比较、有符号表示、算术前置条件与 scratch |
| [数据结构](docs/data-structures.md) | NegativeArray、零头记录、引用路由、Arena/Chain 所有权和稳定归并 |
| [帧与指令机](docs/io-machines.md) | 字符缓冲协议、单帧/双帧、括号匹配、InstructionMachine 的 PC 跳转 |
| [成本模型](docs/cost-model.md) | 按数值、元素数、帧长度增长的工作量；PP3 操作与 Python Runtime 耗时的区别 |
| [API 参考](docs/api.md) | 所有公开导出的签名、参数含义、返回值、异常和别名限制 |
| [示例](examples/README.md) | 生成任意有符号整数加法器和稳定链表排序器 |

宏方法主要接收槽地址而不是运行时数值。第一次使用前建议先读实现机制和宏与数值模型，再按任务查 API；若要复用数组/记录或编写解释器，再读相应专题页。

## 包含内容

- Macros：槽位分配、局部分支/循环、判等、比较、区间判断、有符号整数读取、自然数算术、除法和十进制字符输出。
- NegativeArray：从自动规划的负地址区域增长的自然数数组。
- Reference、RecordHeap、RecordList、merge_sort：引用路由、零头记录、所有权链表及稳定归并。
- Arena、Chain、InstructionMachine：可配置记录堆、可共享后继链、带括号配对边的指令链模板。
- frame_program、dual_frame：基于标准字符 I/O 的单帧及源码/数据双帧加载模板。

Challenge 专属的 ROT13、生命游戏、BF/PP3 解释器和题目生成器不在本包内；它们留在 [PP3-Challenges](https://github.com/JDK8u341/PP3-Challenges)，并使用本包提供的通用结构。

## 验证

~~~powershell
git clone --recurse-submodules https://github.com/JDK8u341/PP3-Toolkit.git
cd PP3-Toolkit
python -B -m unittest discover -v
python -m pip wheel . --no-deps --wheel-dir dist
~~~

测试矩阵覆盖 Python 3.10、3.12、3.14，并用固定 PP3 提交执行生成代码。子模块只用于测试，不进入发布 wheel。只运行本机测试无需安装 Toolkit wheel；测试直接导入仓库源码。

测试不证明无限输入资源或任意违反前置条件时的行为，性能边界另见[成本模型](docs/cost-model.md)。

## 授权

GPL-3.0-only，详见 [LICENSE](LICENSE)。PP3 测试子模块保留其上游仓库与许可。
