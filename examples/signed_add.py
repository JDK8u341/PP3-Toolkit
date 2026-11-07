"""生成任意有符号整数加法器的 PP3 源码。"""

from pp3_toolkit import Macros, compile_program, seq


def signed_add(m: Macros) -> str:
    """读取两行有符号整数并输出其和；题目运算由 PP3 完成。"""
    a, sa, b, sb, total, sign = (m.slot(name) for name in (
        "A幅值", "A负号", "B幅值", "B负号", "结果幅值", "结果负号",
    ))
    same, lt, eq, gt = (m.slot(name) for name in ("同号", "小于", "相等", "大于"))

    same_sign_sum = seq(
        m.constant(total, 0), m.add_into(total, a), m.add_into(total, b), m.copy(sign, sa),
    )
    larger_a = seq(m.copy(total, a), m.subtract_from(total, b), m.copy(sign, sa))
    larger_b = seq(m.copy(total, b), m.subtract_from(total, a), m.copy(sign, sb))
    opposite_sign_sum = seq(
        m.compare(a, b, lt, eq, gt),
        m.if_nonzero(m.read(gt), larger_a,
                     m.if_nonzero(m.read(lt), larger_b,
                                  seq(m.constant(total, 0), m.constant(sign, 0)))),
    )
    return seq(
        m.decode_integer(a, sa), m.decode_integer(b, sb), m.equal(sa, sb, same),
        m.if_nonzero(m.read(same), same_sign_sum, opposite_sign_sum),
        m.once(m.read(total), m.once(m.read(sign), "&45 @print_as_char")),
        m.print_unsigned_decimal(total), "&10 @print_as_char",
    )


if __name__ == "__main__":
    print(compile_program(signed_add), end="")
