# API 参考

以下符号都可从 `pp3_toolkit` 顶层导入；细节和限制也记录在各函数的 Python docstring 中。

## 生成器

### `seq(*parts)`

按顺序拼接非空 PP3 源码片段。宏模板通常返回 `seq(...)`，因此可自然组合条件和循环。

### `format_code(code)`

清理空行并按独立 `[`、`]` 行缩进；循环不匹配时抛 `ValueError`。它是格式器，不是完整 PP3 parser；生成器应确保 token 与括号符合 PP3 语法。

### `compile_program(generator)`

接受 `generator(macros) -> str`，两遍确定槽位，返回有末尾换行的源代码。传入函数必须是确定性的；不要在其执行期间读取 stdin 或基于题目数据构造不同模板。

## `Macros`

| 方法 | 用途 | 主要约束 |
| --- | --- | --- |
| `slot(name)` | 取得稳定控制槽 | 同名共用槽，勿让独立值意外别名 |
| `read(slot)` | 读取自然数槽 | 返回表达式字符串 |
| `put(slot, expression)` | 写槽 | 常规槽仅存非负值；表达式不可破坏目标路由 |
| `constant(slot, value)` | 写立即数 | value>=0 |
| `copy(dst, src)` | 保留来源的复制 | 参数不可占用内部 scratch |
| `change(slot, "@+"/"@-")` | 自增/自减 | 仅支持这两个标准操作 |
| `once(cond, body)` | 非零单次分支 | body 后归零 |
| `if_nonzero(cond, yes, no)` / `if_zero(cond, body)` | 条件 | 两分支的临时工作槽不可互相覆盖 |
| `loop(cond, body)` | 非零循环 | body 必须最终改变条件至零 |
| `equal(a,b,out)` | 任意自然数判等 | 输出不能覆盖输入或内部 scratch |
| `compare(a,b,lt,eq,gt)` | 自然数三路比较 | 三个输出互异且不覆盖输入/scratch |
| `in_range(x,lo,hi,out)` | 自然数闭区间判断 | 常量边界满足 0<=lo<=hi |
| `decode_integer(mag,sign)` | `@input` 读取有符号整数 | mag/sign 互异且不占四个解码 scratch |
| `add_into(dst,src)` | 自然数加法并保留来源 | 工作量与 src 成正比 |
| `subtract_from(dst,src)` | 自然数减法并保留来源 | 必须 dst>=src |
| `divmod_unsigned(n,d,q,r)` | 自然数商余数 | d>0、q!=r；重复减法 |
| `print_unsigned_decimal(x)` | 字符输出十进制 | x>=0；不自动补 LF |

完整宏列表和内部路由细节见 [`macros.py`](../pp3_toolkit/macros.py)。比较、十进制与除法会复用具名 scratch 槽。不要在某个宏尚未结束时递归进入同一 scratch 使用者，除非已证明重入安全。

## 数组和记录

- `NegativeArray(macros, name="数据区")`：`reset()`、`advance()`、`read()`、`put(expr)`、`change(op)`、`seek(index)`。数组元素非负，动态区不自带长度或结束标记。
- `Reference.put/copy/next/bump`：在静态槽存取零头引用。引用不是普通自然数。
- `RecordHeap(macros)`：四格零头记录，字段 `MAGNITUDE=1`、`SIGN=2`、`NEXT=3`；须先生成/运行 `initialize()`。
- `RecordList(heap, name)`：`append(node)`、`pop(node)`、`concat(other)`。链之间要遵守节点所有权。
- `merge_sort(macros, source, length, name="归并")`：按 MAGNITUDE 稳定排序，结束后节点归还 source。
- `Arena(macros, width=8)`：通用零头记录堆；`put(..., reference=True)` 或 `link(...)` 专用于引用字段。
- `Chain(arena, name, next_field=8)`：指定后继字段的只追加引用链；不拥有/释放节点。

## 帧和指令

- `ERROR_OUTPUT`：用字节字符输出 `ERROR\n` 的静态 DSL。
- `validate_byte(macros, char, error)`：将超出 0..255 的码点标记为错误；调用前要求 char 非负。
- `frame_program(macros, prepare, consume, finish)`：单个非负长度帧的加载模板，回调仅在 Python 生成期展开。
- `literal(text)`：把固定字符串转换成字符输出 DSL，实际输出服从 `view % 256`。
- `InstructionMachine(macros)`：共用 Arena、指令链和 I/O 链；使用 `emit`、`code_end`、`jump_after_pair`、`run` 组合解释器。
- `dual_frame(macros, prepare, code_char, code_end, data_char, finish)`：读取两长度头及连续源码/数据帧，完整加载后运行。

这些机器模板只定义存储与控制流框架，不替使用者决定具体 opcode、客体 EOF 或无效源码的全部语义。
