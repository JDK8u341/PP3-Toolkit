"""通用 DSL 宏和数据结构的原版 PP3 端到端测试。"""

from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests" / "vendor" / "PP3"))

from src.pp3 import HandlerType, IRBuilder, Runtime, std_register
from examples.signed_add import signed_add
from examples.stable_sort import stable_sort
from pp3_toolkit import (
    Arena,
    Chain,
    InstructionMachine,
    Macros,
    NegativeArray,
    RecordHeap,
    RecordList,
    compile_program,
    dual_frame,
    frame_program,
    merge_sort,
    seq,
)


def build(code):
    """使用固定注册表构建 IR，并确保生成代码没有直接寻址节点。"""
    ir = IRBuilder(op_map=std_register).build(code)

    def check(nodes):
        for node in nodes:
            if node.TYPE == HandlerType.Mem:
                raise AssertionError("Toolkit 生成了直接寻址操作")
            if node.TYPE == HandlerType.Loop:
                check(node.body)

    check(ir)
    return ir


def execute(ir, stdin=""):
    runtime, output = Runtime(can_direct_addressing=False), StringIO()
    with patch("sys.stdin", StringIO(stdin)), redirect_stdout(output):
        runtime.run(ir)
    return output.getvalue(), runtime


class FormattingTests(unittest.TestCase):
    def test_seq_and_loop_formatting(self):
        self.assertEqual(seq("&1", "", "[", "@-", "]"), "&1\n[\n@-\n]")
        self.assertEqual(compile_program(lambda m: seq("&1", "[", "@-", "]")),
                         "&1\n[\n  @-\n]\n")

    def test_unmatched_generated_loop_is_rejected(self):
        for source in (" ] ", "[", "[\n&0\n"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                compile_program(lambda m, source=source: source)

    def test_generator_must_allocate_same_slots_on_both_passes(self):
        calls = 0

        def unstable(m):
            nonlocal calls
            calls += 1
            m.slot(f"槽{calls}")
            return "&0"

        with self.assertRaises(ValueError):
            compile_program(unstable)


class ArithmeticMacroTests(unittest.TestCase):
    def test_division_comparison_equality_and_decimal_output(self):
        def program(m):
            number, divisor, quotient, remainder = (m.slot(name) for name in (
                "数", "除数", "商", "余数",
            ))
            lt, eq, gt = (m.slot(name) for name in ("小", "等", "大"))
            return seq(
                m.constant(number, 17), m.constant(divisor, 5),
                m.divmod_unsigned(number, divisor, quotient, remainder),
                m.print_unsigned_decimal(quotient), "&32 @print_as_char",
                m.print_unsigned_decimal(remainder), "&10 @print_as_char",
                m.compare(quotient, remainder, lt, eq, gt), m.read(gt) + " @print",
                m.equal(quotient, quotient, eq), m.read(eq) + " @print",
            )

        output, _ = execute(build(compile_program(program)))
        self.assertEqual(output, "3 2\n1\n1\n")

    def test_signed_integer_decoder_and_sign_normalization(self):
        def program(m):
            magnitude, sign = m.slot("幅值"), m.slot("符号")
            return seq(
                m.decode_integer(magnitude, sign),
                m.once(m.read(magnitude), m.once(m.read(sign), "&45 @print_as_char")),
                m.print_unsigned_decimal(magnitude), "&10 @print_as_char",
            )

        ir = build(compile_program(program))
        for text, expected in (("-00123\n", "-123\n"), ("+000\n", "0\n"), ("-0\n", "0\n")):
            with self.subTest(text=text):
                self.assertEqual(execute(ir, text)[0], expected)


class ArrayAndRecordTests(unittest.TestCase):
    def test_negative_array_keeps_zero_as_a_valid_element(self):
        def program(m):
            array = NegativeArray(m)
            value, remaining = m.slot("载荷"), m.slot("剩余")
            parts = [array.reset()]
            for item in (0, 8, 0, 42):
                parts.extend((m.constant(value, item), array.put(m.read(value)), array.advance()))
            parts.extend((array.reset(), m.constant(remaining, 4), m.loop(m.read(remaining), seq(
                array.read() + " @print", array.advance(), m.change(remaining, "@-")))))
            return seq(*parts)

        self.assertEqual(execute(build(compile_program(program)))[0], "0\n8\n0\n42\n")

    def test_stable_sort_handles_duplicates_and_large_natural_payloads(self):
        def program(m):
            heap = RecordHeap(m)
            values = RecordList(heap, "排序")
            count, left, value, ordinal, sign, node = (m.slot(name) for name in (
                "数量", "剩余", "值", "原序号", "符号", "节点",
            ))
            return seq(
                heap.initialize(), m.put(count, "@input"), m.copy(left, count),
                m.loop(m.read(left), seq(
                    m.put(value, "@input"), heap.allocate(node, value, ordinal), values.append(node),
                    m.change(ordinal, "@+"), m.change(left, "@-"),
                )),
                merge_sort(m, values, count),
                m.loop(m.read(values.head), seq(
                    values.pop(node), heap.read(node, RecordHeap.MAGNITUDE) + " @print",
                    heap.read(node, RecordHeap.SIGN) + " @print",
                )),
            )

        ir = build(compile_program(program))
        large = 10**40
        values = [7, large, 0, 7, 2, large]
        stdin = "\n".join(map(str, [len(values), *values])) + "\n"
        output, _ = execute(ir, stdin)
        ordered = sorted(enumerate(values), key=lambda pair: pair[1])
        self.assertEqual(output, "".join(f"{value}\n{index}\n" for index, value in ordered))

    def test_arena_and_chain_support_self_follow(self):
        layout = {}

        def program(m):
            arena = Arena(m, width=3)
            chain = Chain(arena, "链", next_field=3)
            a, b, cursor = (m.slot(name) for name in ("A", "B", "游标"))
            layout.update(head=chain.head, tail=chain.tail, a=a, b=b, cursor=cursor, bump=arena.bump)
            return seq(
                arena.initialize(), arena.allocate(a), arena.allocate(b),
                arena.put(a, 1, "&11"), arena.put(b, 1, "&22"),
                chain.append(a), chain.append(b), arena.link(b, 3, b),
                # 使用同槽游标沿 NEXT 前进一步，再沿节点自环验证原地跟随。
                m.copy(cursor, chain.head), chain.advance(cursor),
                chain.advance(cursor), arena.read(cursor, 1) + " @print",
            )

        output, runtime = execute(build(compile_program(program)))
        self.assertEqual(output, "22\n")
        self.assertEqual(runtime.memory[layout["head"]], runtime.memory[layout["a"]])
        self.assertNotEqual(runtime.memory[layout["tail"]], 0)
        self.assertEqual(runtime.memory[runtime.memory[layout["a"]]], 0)


class FrameAndMachineTests(unittest.TestCase):
    def test_single_frame_buffers_until_whole_frame_valid(self):
        def echo_frame(m):
            array = NegativeArray(m, "帧缓存")
            remaining, char = m.slot("回放剩余"), m.slot("帧字符")
            return frame_program(
                m,
                lambda m, length: array.reset(),
                lambda m, value: seq(array.put(m.read(value)), array.advance()),
                lambda m, length: seq(
                    array.reset(), m.copy(remaining, length), m.loop(m.read(remaining), seq(
                        array.read() + " @print_as_char", array.advance(), m.change(remaining, "@-"))),
                ),
            )

        ir = build(compile_program(echo_frame))
        self.assertEqual(execute(ir, "3\nA\x00B")[0], "A\x00B")
        self.assertEqual(execute(ir, "3\nA中B")[0], "ERROR\n")
        self.assertEqual(execute(ir, "-1\n")[0], "ERROR\n")

    def test_dual_frame_loads_consecutive_code_and_data_payloads(self):
        def program(m):
            array = NegativeArray(m, "双帧缓存")
            count, remaining = m.slot("累计数"), m.slot("回放数")

            def append(m, char, error):
                return seq(array.put(m.read(char)), array.advance(), m.change(count, "@+"))

            def finish(m, error):
                return seq(array.reset(), m.copy(remaining, count), m.loop(m.read(remaining), seq(
                    array.read() + " @print_as_char", array.advance(), m.change(remaining, "@-"))))

            return dual_frame(
                m, lambda m, error: seq(array.reset(), m.constant(count, 0)),
                append, lambda m, error: "", append, finish,
            )

        ir = build(compile_program(program))
        self.assertEqual(execute(ir, "2\n1\nABZ")[0], "ABZ")
        self.assertEqual(execute(ir, "-1\n0\n")[0], "ERROR\n")
        self.assertEqual(execute(ir, "2\n1\nA中Z")[0], "ERROR\n")

    def test_instruction_machine_pairs_and_executes_control_flow(self):
        def program(m):
            machine = InstructionMachine(m)
            heap = machine.heap
            counter, opcode, error = (m.slot(name) for name in ("计数", "操作码", "错误"))

            def emit(code):
                return seq(m.constant(opcode, code), machine.emit(opcode, error, 3, 4))

            # 指令 1 自增；2 将 0..2 按模 3 递减；3/4 是循环括号。
            decrement_mod_three = m.if_nonzero(m.read(counter), seq(
                m.change(counter, "@-"), m.if_zero(m.read(counter), m.constant(counter, 2))),
                m.constant(counter, 2))
            dispatch = seq(
                m.if_zero(m.read(opcode) + " @-", m.change(counter, "@+")),
                m.if_zero(m.read(opcode) + " @- @-", decrement_mod_three),
                m.if_zero(m.read(opcode) + " @- @- @-",
                          m.if_zero(m.read(counter), machine.jump_after_pair())),
                m.if_zero(m.read(opcode) + " @- @- @- @-",
                          m.once(m.read(counter), machine.jump_after_pair())),
            )
            # +[--] 会走两轮；第二个 [--] 在 view 为零时应直接跳过。
            return seq(
                heap.initialize(),
                *(emit(code) for code in (1, 3, 2, 2, 4, 3, 2, 2, 4)),
                machine.code_end(error), machine.run(error, "", dispatch),
                m.read(counter) + " @print",
            )

        output, _ = execute(build(compile_program(program)))
        self.assertEqual(output, "0\n")


class ExampleTests(unittest.TestCase):
    def test_signed_add_example(self):
        ir = build(compile_program(signed_add))
        for a, b in ((5, 8), (-5, -8), (-15, 6), (15, -20), (0, -0), (-9, 9)):
            with self.subTest(a=a, b=b):
                self.assertEqual(execute(ir, f"{a}\n{b}\n")[0], f"{a + b}\n")

    def test_stable_sort_example(self):
        ir = build(compile_program(stable_sort))
        values = [7, 0, 7, 1000, 2, 0]
        stdin = "\n".join(map(str, [len(values), *values])) + "\n"
        self.assertEqual(execute(ir, stdin)[0], "0\n0\n2\n7\n7\n1000\n")


if __name__ == "__main__":
    unittest.main()
