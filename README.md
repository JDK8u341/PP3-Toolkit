# PP3 Toolkit

PP3 Toolkit 是一组**编译期静态代码生成工具**，用于把可复用的条件、自然数运算、数组、记录、链表、帧读取和指令机器宏展开为 PP3 DSL。生成出的程序仍由 PP3 自己执行；本包不实现 Runtime、不改写语言语义、不调用 cup，也不把题目输入交给 Python 运算。

当前版本 `0.1.0`，支持 Python 3.10 及以上。运行时依赖为零；包不要求安装 PP3。PP3 仅作为测试子模块用于端到端验证。

## 安装

从 GitHub 仓库直接安装（pip 会从源码构建 wheel）：

```powershell
python -m pip install "pp3-toolkit @ git+https://github.com/JDK8u341/PP3-Toolkit.git@main"
```

从本地克隆目录构建 wheel 并安装：

```powershell
python -m pip wheel . --no-deps --wheel-dir dist
python -m pip install dist/pp3_toolkit-0.1.0-py3-none-any.whl
```

GitHub Actions 的测试工作流也会构建 wheel，并将其作为短期 Actions artifact 保存；本项目目前不发布到 PyPI。

## 快速开始

生成一个读取两个非负整数并输出和的 PP3 程序：

```python
from pp3_toolkit import Macros, compile_program, seq


def make_sum(m: Macros) -> str:
    left, right = m.slot("left"), m.slot("right")
    return seq(
        m.put(left, "@input"),
        m.put(right, "@input"),
        m.add_into(left, right),
        m.read(left) + " @print",
    )


source = compile_program(make_sum)
print(source, end="")
```

Python 只展开固定的宏模板。`source` 是 PP3 源码，可以传给：

```python
from src.pp3 import IRBuilder, Runtime, std_register

ir = IRBuilder(op_map=std_register).build(source)
Runtime(can_direct_addressing=False).run(ir)
```

更完整的可运行示例见 [`examples/`](examples/)。宏契约、寻址机制、内存布局和成本边界见[实现机制](docs/mechanism.md)与[API 参考](docs/api.md)。

## 包含内容

- `Macros`：槽位分配、局部分支/循环、判等、比较、区间判断、有符号整数读取、自然数算术、除法和十进制字符输出。
- `NegativeArray`：从自动规划的负地址区域增长的自然数数组。
- `Reference`、`RecordHeap`、`RecordList`、`merge_sort`：引用路由、零头记录、所有权链表及稳定归并。
- `Arena`、`Chain`、`InstructionMachine`：可配置记录堆、可共享后继链、带括号配对边的指令链模板。
- `frame_program`、`dual_frame`：基于标准字符 I/O 的单帧及源码/数据双帧加载模板。

Challenge 专属的 ROT13、生命游戏、BF/PP3 解释器和题目生成器**不在本包内**；它们留在 [PP3-Challenges](https://github.com/JDK8u341/PP3-Challenges)，并使用本包提供的通用结构。

## 验证

```powershell
git clone --recurse-submodules https://github.com/JDK8u341/PP3-Toolkit.git
cd PP3-Toolkit
python -B -m unittest discover -v
python -m pip wheel . --no-deps --wheel-dir dist
```

测试矩阵覆盖 Python 3.10、3.12、3.14，并用固定 PP3 提交执行生成代码。子模块只用于测试，不进入发布 wheel。

## 授权

GPL-3.0-only，详见 [LICENSE](LICENSE)。PP3 测试子模块保留其上游仓库与许可。
