"""基于标准字符 I/O 的可复用 PP3 帧读取器。

这些宏只输出 DSL；Python 回调在编译期展开，不能在运行时取得帧内容。
"""

from .macros import seq


ERROR_OUTPUT = " ".join(f"&{ord(char)} @print_as_char" for char in "ERROR\n")


def validate_byte(m, char, error):
    """验证已知非负的码点不大于 255，并在 DSL 错误槽中置位。"""
    maximum, lt, eq, gt = (m.slot(name) for name in ("最大字节", "字节小于", "字节等于", "字节大于"))
    return seq(
        m.constant(maximum, 255),
        m.compare(char, maximum, lt, eq, gt),
        m.once(m.read(gt), m.constant(error, 1)),
    )


def frame_program(m, prepare, consume, finish):
    """生成“整数长度 + 定长字节字符帧”读取器。

    ``prepare(m, length)`` 在读取字符前生成初始化代码；
    ``consume(m, char)`` 为每个有效字符生成处理代码；
    ``finish(m, length)`` 生成完整帧验证成功后的输出代码。

    帧长度由 ``@input`` 读取，允许标准 ``int()`` 接受的整数拼写；负数
    输出 ``ERROR\\n`` 且不读字符。字符输入按 ``@input_as_char`` 的行缓冲
    语义工作，补回 LF 计入帧长。只有整帧校验后才调用 ``finish``；帧内
    非字节码点会继续消费余下帧但不会执行 ``consume``。提前 EOF 不捕获，
    保留 Runtime 的 ``EOFError``。

    回调只接收静态宏对象与槽地址，不会接收运行时的输入数值。
    ``prepare``/``consume``/``finish`` 在构造期调用，因此应保持确定性。
    """
    length, sign, remaining, char, error = (m.slot(name) for name in (
        "帧长", "长度负号", "剩余字符", "帧字符", "帧错误",
    ))
    # 预先展开所有回调，以便两遍槽位分配能看到完整工作区。
    initialize = prepare(m, length)
    process = consume(m, char)
    output = finish(m, length)
    step = seq(
        m.put(char, "@input_as_char"),
        m.if_zero(m.read(error), seq(
            validate_byte(m, char, error),
            m.if_zero(m.read(error), process),
        )),
        m.change(remaining, "@-"),
    )
    valid_length = seq(
        initialize,
        m.copy(remaining, length),
        m.loop(m.read(remaining), step),
        m.if_nonzero(m.read(error), ERROR_OUTPUT, output),
    )
    return seq(
        m.decode_integer(length, sign),
        m.if_nonzero(m.read(sign), ERROR_OUTPUT, valid_length),
    )
