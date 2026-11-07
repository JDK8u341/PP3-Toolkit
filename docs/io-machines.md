# 帧与指令机

本文解释 Toolkit 的字符帧协议和 InstructionMachine。它们提供的是加载、存储和控制流框架；题目的字节语义、客体 EOF、指令效果仍由使用者决定。

## PP3 字符 I/O 语义

字符操作由 PP3 的标准注册表提供：

- @input_as_char 将一个字符码点放入当前 view。
- @print_as_char 输出 view % 256 对应的字符，不改变 view，也不自动添加换行。
- 输入扩展以 Runtime 为实例边界维护字符缓冲。缓冲为空时一次读取一整行，再把 LF 补回缓冲；随后逐个字符交付。空行因此交付一个 LF。
- 输入耗尽时由底层 input() 抛 EOFError。Toolkit 的帧读取器不吞掉这个异常。

这里“字符”指 Python 字符串中的码点，而非 UTF-8 字节。Toolkit 的帧校验只接受 0..255；超范围码点不静默截断。输出字符操作则明确按 256 取模。

## 单帧协议

frame_program 生成的输入顺序如下：

~~~text
一行整数长度 n
随后由 input_as_char 缓冲交付的 n 个码点
~~~

长度通过 PP3 @input 读取。n<0 时输出 ERROR 加 LF，不读取帧。n>=0 时每次字符读取都校验 0<=codepoint<=255：

1. prepare(m, length) 的 DSL 在帧读取之前执行，用于清空/初始化缓存等结构。
2. 对剩余长度循环读取字符。
3. 若字符合法且此前没有错误，执行 consume(m, char) 展开的 DSL。
4. 超范围字符会置 error，但仍继续消费该帧余下字符；已有错误时后续字符不再传给 consume。
5. 完整读取后，若 error 非零则输出 ERROR 加 LF；否则执行 finish(m, length) 的 DSL。

提前 EOF 会在读取位置抛 EOFError，之前已执行的 prepare/consume 副作用不会回滚；finish 不执行。整数解析失败同样由 Runtime 原样传播。frame_program 不设置最大 n，因此过大的长度可能消耗大量时间或内存。

回调不是运行时 Python 回调。prepare、consume、finish 在构造 frame_program 时各调用一次以取得 DSL 字符串；包裹在 compile_program 中时，生成器会整体运行两遍，因此这些 Python 回调也会被调用两遍。它们必须确定且无外部副作用。运行 PP3 时只执行拼出的 DSL。

## 单帧回显示例

下面把一帧先存进动态数组，完整校验成功后再输出。若第三个字符非法，不会输出前两个字符，因为实际输出在 finish 阶段：

~~~python
from pp3_toolkit import (
    Macros, NegativeArray, compile_program, frame_program, seq,
)


def make_echo(m: Macros) -> str:
    data = NegativeArray(m, "echo.frame")
    remaining = m.slot("echo.remaining")

    def prepare(m, length):
        return data.reset()

    def consume(m, char):
        return seq(data.put(m.read(char)), data.advance())

    def finish(m, length):
        return seq(
            data.reset(),
            m.copy(remaining, length),
            m.loop(m.read(remaining), seq(
                data.read() + " @print_as_char",
                data.advance(),
                m.change(remaining, "@-"),
            )),
        )

    return frame_program(m, prepare, consume, finish)


source = compile_program(make_echo)
~~~

若长度是 3，字符帧是 A、B、C，则输出 ABC。帧中 LF 是普通字符，也计入 3；例如输入行里的 LF 可能是该帧字符之一。帧结束由长度确定，不靠换行分隔。

## 双帧协议

dual_frame 的输入顺序：

~~~text
源码长度 c 的整数行
数据长度 d 的整数行
接着连续的 c 个源码字符
紧接着连续的 d 个数据字符
~~~

两帧之间没有自动插入的空格、换行或 NUL。字符缓冲补回的 LF 与其他字符一样计入对应帧。两个长度头先全部读取并解码；若任一为负，输出 ERROR 加 LF，跳过初始化和 payload 消费。

对于非负长度，运行时顺序是：

1. 执行 prepare，准备源码/数据结构。
2. 读取源码帧并对每个合法码点执行 code_char。
3. 仅当此前没有错误时执行 code_end，例如检查括号栈是否清空。
4. 读取数据帧。即使源码处理已经报错，也消费数据帧剩余字符，但不会继续调用 data_char。
5. 两帧都读完后，有错误就输出 ERROR 加 LF；无错误才执行 finish 返回的执行代码。

因此，负长度不会消费 payload；已声明长度内的非法码点会导致错误并消费余下帧；提前 EOF 立即传播 EOFError，不保证输出 ERROR。错误分支只抑制后续回调/执行，不撤销此前回调产生的结构写入或输出。

源码和数据长度是运行时整数，帧内容是逐字符输入。不要在长度头和字符帧之间额外插入协议分隔符；行分隔仅用于整数头，字符缓冲随后按调用次序提供内容。

## InstructionMachine 的内存布局

InstructionMachine 使用一个 Arena(width=8)。每个记录包含零头和 8 个字段：

| 字段 | 内容 | 用法 |
| ---: | --- | --- |
| 1 | opcode | 每条指令必需 |
| 2 | magnitude 参数 | 可选自然数 |
| 3 | sign 参数 | 可选 0/1 |
| 4 | PAIR 引用 | 开括号指向配对闭括号，闭括号指向开括号 |
| 5 | 暂存括号栈前驱 | 仅装载开括号时使用 |
| 8 | NEXT 引用 | 线性代码/数据链后继 |

代码链和客体输入链共享 Arena 分配的记录，但各自用不同 head/tail 引用。节点身份与字段载荷分离；重复 opcode 或重复数据字节不会造成节点混淆。

### 括号配对构造

emit(opcode, error, opening, closing, ...) 每次在生成出的 PP3 程序运行时分配一条记录，并追加到代码链：

- 若 opcode 等于 opening，记录字段 5 保存当前括号栈顶，括号栈更新为新节点。
- 若 opcode 等于 closing 且栈非空，当前闭括号的字段 4 指向栈顶开括号；开括号字段 4 反向指向当前节点；括号栈沿开括号字段 5 弹出。
- 若 opcode 等于 closing 但栈为空，error 置非零。
- code_end 在加载结束后检查括号栈；非空表示存在未闭合开括号，也会置 error。

不属于 opening/closing 的普通 opcode 不改括号栈。opening/closing 是 Python 生成期整数；opcode 是运行时槽地址。emit 并不负责过滤未知 opcode，也不会检查代码长度。

## 取指与跳转

run 初始化 PC=code.head、输入游标=data.head，然后执行：

1. active 保存当前 PC。
2. opcode 从 active.field1 载入。
3. PC 先沿线性 NEXT 前进一步。
4. 执行调用者提供的 dispatch DSL。
5. 若 error 非零，将 PC 清零以退出循环。
6. 循环退出后若 error 非零，输出 ERROR 加 LF。

jump_after_pair 依次取 active.field4，然后沿代码 NEXT 再前进一步。因此：

- 当前 active 是开括号时，跳到匹配闭括号之后，适合实现入口条件为假的情况。
- 当前 active 是闭括号时，跳到匹配开括号之后，适合继续执行循环体。

PC 在 dispatch 之前已经预增，所以跳转代码必须基于 active 的配对字段，而不是假设 PC 仍指向当前节点。该 helper 只完成地址跳转；循环是否回边、何时退出完全由调用者的 dispatch 决定。

run 遇到错误时停止后续指令并输出 ERROR，但不回滚已经发生的客体输出。错误前的部分结果可能已经可见。

## 设计一个小解释器时的职责边界

使用者通常还需要自己生成以下状态和语义：

- 客体数据带/栈及其单元范围、回绕规则。
- 每个 opcode 的 dispatch 分支。
- 客体字符输入耗尽行为和输出编码。
- 指令参数的合法范围和错误协议。
- 运行步数或资源上限。
- 执行产生部分输出后遇到错误时的处理。

InstructionMachine 提供平坦指令节点、括号匹配和 PC/输入链框架；它不隐式提供上面的语言规则。若构造 BF/PP3 子集解释器，请把实际支持的 opcode 子集和 EOF 约定写在题目自身的规范中。

## 固定文本输出

literal(text) 将每个 Python 字符展开为 &ord(character) @print_as_char。输出按码点模 256 映射，不是 Unicode 或 UTF-8 编码。ERROR_OUTPUT 使用相同路径输出 ASCII 文本 ERROR 加 LF。
