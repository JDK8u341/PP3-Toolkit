# API 参考

本文按公开导出逐项说明参数、返回值、数据前置条件和检查边界。除明确标注为 Python 数值/文本的参数外，整数参数通常是运行时槽的**地址**，而不是该槽当前保存的值。公开导出列表以 pp3_toolkit.__all__ 为准。

## 约定

- 宏构造方法返回 PP3 DSL 字符串；调用它们只生成文本，不执行 PP3。
- 对槽地址参数，先通过同一个 Macros 实例的 slot(name) 取得地址。
- 普通数值槽保存自然数；零头引用须使用 Reference 或 reference=True 的记录接口。
- 布尔结果为 0/1。除文档明确说明外，不应假设宏会在运行时验证前置条件。
- 内部 scratch 是同一生成过程共享的静态槽。不要让业务数据使用保留 scratch 名称。
- ValueError 表示某些可在生成期发现的错误；未抛异常不等于别名或输入一定有效。

## 固定 scratch 槽名

不少数据结构/帧模板也通过固定名称取得槽。它们不是命名空间隔离的 Python 属性；同一 Macros 中同名必然指向同一 PP3 槽。

| API | 内部槽名 |
| --- | --- |
| NegativeArray(m, name) | name.指针、name.寻址计数 |
| RecordHeap | 记录堆.未使用地址 |
| RecordList(name) | name.表头、name.表尾 |
| Arena | 机器堆.未使用地址 |
| Chain(name) | name.表头、name.表尾 |
| InstructionMachine | 机器.节点、机器.括号栈、机器.PC、机器.当前指令、机器.操作码、机器.输入游标；客体代码/客体输入链的表头和表尾；机器堆.未使用地址 |
| frame_program | 帧长、长度负号、剩余字符、帧字符、帧错误 |
| dual_frame | 双帧.源码长度、双帧.数据长度、双帧.源码负号、双帧.数据负号、双帧.剩余、双帧.字符、双帧.错误 |
| validate_byte | 最大字节、字节小于、字节等于、字节大于 |

frame_program 和 dual_frame 的错误槽必须在模板入口为零；Toolkit 不会自动清除错误槽。新 Runtime 的默认内存满足此条件。复用模板或在执行前有其他代码时，调用方负责显式清零。若帧读取已经报错，后续复用前也必须清零。

不同 NegativeArray、RecordHeap 和 Arena 实例不会自动获得独立动态区。尤其 RecordHeap/Arena 从同一 array_base 开始；同一程序的多个链应共享一个堆实例，而不是各自分配重叠区域。

生成流程和路由证明见[实现机制](mechanism.md)、[宏与数值模型](macros.md)。

## 源码组合函数

### seq(*parts) -> str

按传入顺序用换行连接非空字符串；空字符串会跳过。适合组合宏片段。不会检查 token、缩进或括号。

### format_code(code: str) -> str

去除空行并 trim 每一行；只有整行内容恰为 [ 或 ] 时才增减缩进。返回值末尾总有 LF，包括空输入。

若括号提前关闭或结束仍未闭合，抛 ValueError。它不是 PP3 lexer/parser：行内括号、注释、token 参数合法性由调用方负责。

### compile_program(program: Callable[[Macros], str]) -> str

调用生成函数两次：第一次收集槽名，第二次用正式动态区边界生成代码；比较两次 slot 名称映射后格式化代码。

生成函数及其回调必须确定且无副作用。实现只检查槽映射，不检查两次返回源码是否相同。通过手写负地址产生的隐藏槽不会纳入规划。括号不配对或两遍槽映射不同会抛 ValueError。

返回带缩进和尾随 LF 的源码。关于两遍运行的详细示意见[实现机制](mechanism.md)。

## Macros

### Macros(bound=3)

创建一个槽位分配器。正常情况下使用 compile_program 自动设置 bound；手动使用时，必须确保动态区起点低于全部静态槽和保留地址。

### slot(name: str) -> int

返回具名静态槽地址。首次请求从 -3 开始分配；同一 name 返回同一地址，故同名就是别名。不要将 name 与宏实现使用的 scratch 名称重复。

### array_base -> int

动态数组/记录区的第一个负地址，值为 -bound。静态槽和动态区必须由同一生成过程规划。

### flag() -> int

按调用顺序分配独立条件标志槽，内部名称为 条件标志N。一般直接使用 if_nonzero/if_zero，不必手工申请标志。

### read(slot: int) -> str

生成读取自然数/槽内容到 view 的表达式。典型结果形式为 &slot ~1。不会复制到另一个槽。

### select(slot: int) -> str

生成普通自然数写入模板的路由前缀；通常由 put/constant 使用。该方法只建立路径，不是完整赋值。

### put(slot: int, expression: str) -> str

将 expression 生成的非负数写入 slot。表达式不得依赖 slot 的旧值、破坏零锚点或覆盖目标路径。引用不能用此方法写入。

### constant(slot: int, value: int) -> str

将生成期非负立即数写入槽；value < 0 时抛 ValueError。运行时不会验证其他自然数不变量。

### copy(destination: int, source: int) -> str

将自然数源槽复制到目标，保留 source；destination==source 返回空代码。不能让参数与此程序中同时活跃的 scratch 别名。

### change(slot: int, operation: str) -> str

生成原位 @+ 或 @-。其他 operation 抛 ValueError。@- 要求旧值大于零，否则自然数槽约定可能被破坏。

### once(condition: str, body: str) -> str

若 condition 执行后的 view 非零，执行一次 body；分支结束时 view 置零。condition 和 body 均为 DSL 文本。

### if_nonzero(condition: str, nonzero: str, zero="") -> str

按 condition 的 view 是否非零选择一个分支。使用一个条件标志槽。内部槽按生成期位置分配，不应跨分支保存临时 view。

### if_zero(condition: str, body: str) -> str

condition 为零时执行 body；等价于反向使用 if_nonzero。

### loop(condition: str, body: str) -> str

反复执行 body 并重新计算 condition，直到其 view 为零。不会对循环终止性作检查。

### conjunction(left: int, right: int, result: int) -> str

两个自然数槽均非零时将 result 置 1，否则置 0。left/right 保持不变；result 不得与任一输入相同，冲突时抛 ValueError。

### write_marker(pointer: int, marker: int) -> str

在 pointer 指向的正地址标记写入 0、-1 或 -2。其他 marker 抛 ValueError。pointer 应是自然数地址值；此操作依赖 PP3 Toolkit 的正地址标记不变量。-2 仅应用作受控的临时判等标记。

### equal(left: int, right: int, result: int) -> str

自然数判等，输出规范化布尔值。输入保持不变；结果不得覆盖输入或内部槽。实现会拒绝若干确定的内部别名冲突并抛 ValueError。执行期间临时占用 -2 标记，不能与另一活动判等操作交错。

scratch：等值地址、等值原标记，以及条件标志。正地址在宏入口时应只含约定的零/集合标记。

### compare(left: int, right: int, lt: int, eq: int, gt: int) -> str

自然数三路比较，输入保持不变，lt/eq/gt 中恰好一个为 1。输出必须互异且不能覆盖输入或内部槽；检测到冲突时抛 ValueError。

scratch：比较副本A、比较副本B、比较继续，并使用 equal 的 scratch 和条件标志。非等路径逐次同步递减，成本与较小输入值相关。

### in_range(value: int, low: int, high: int, result: int) -> str

判断生成期常量闭区间 low <= value <= high，结果为 0/1。要求 0 <= low <= high；结果不能覆盖输入或区间内部槽。非法边界或可检测别名抛 ValueError。

scratch：区间下界、区间上界、区间小于、区间等于、区间大于，并使用 compare/equal 的全部 scratch。

### decode_integer(magnitude: int, sign: int) -> str

生成一条 @input 并将有符号结果拆成非负幅值与 0/1 符号位；负零规范成 sign=0。两个输出必须不同且避开解码内部槽，否则抛 ValueError。整数解析错误和 EOFError 由 PP3 Runtime 原样传播。

scratch：解码P、解码Q、解码步数、解码继续；内部还调用加减、条件模板。请为业务槽使用独立前缀，不要占用这些内部名字或加法计数/减法计数。

### add_into(destination: int, source: int) -> str

执行 destination += source。若两个槽不同，来源保持不变；destination==source 合法，此时结果为原值的两倍。参数与内部加法计数槽冲突时抛 ValueError。两个槽必须含自然数。

### subtract_from(destination: int, source: int) -> str

执行 destination -= source，要求 destination >= source；source 在不同槽时保留。与内部减法计数槽冲突时抛 ValueError。宏不检查下溢条件。

### multiply_by_ten(value: int) -> str

原位乘十。value 必须是自然数槽；工作量与原值相关。实现没有完整别名校验，请勿把 value 与内部乘十计数槽合用。

### divmod_unsigned(numerator: int, denominator: int, quotient: int, remainder: int) -> str

自然数商余数，要求 denominator > 0。输入副本保留，结果槽被覆盖；quotient 与 remainder 必须不同。scratch 冲突或结果槽相同会抛 ValueError。

API 预期输入、输出分槽使用；当前实现不会检查每一种输入/输出别名组合。分母为零没有受支持的结果/错误协议。执行工作量按 numerator 的数值线性增长。

scratch：除法工作、除法分母、除法倒数。

### print_unsigned_decimal(value: int) -> str

以 @print_as_char 输出自然数的十进制表示，不添加 LF，输入槽保持不变。调用方负责输出分隔符。零会输出字符 0。宏使用固定输出 scratch 和除法/乘十 scratch；不要将业务槽命名为输出数值、输出位权、输出探测、常数十、输出商或输出余数。

## 数组

### NegativeArray(macros: Macros, name="数据区")

声明动态负地址数组游标，不分配或清零整片内存。base 为 macros.array_base，元素 i 位于 base-i。不同实例默认共享起点，不能把它们当作独立数组。

- reset() -> str：游标回到 base。
- advance() -> str：游标向更负方向移动一格。
- read() -> str：读取当前自然数元素，不移动游标。
- put(expression: str) -> str：把自然数表达式写入当前元素；表达式不能读当前元素旧值。
- change(operation: str) -> str：原位 @+/@-；其他操作抛 ValueError。
- seek(index: int) -> str：从 base 移动 index 格；index 是存放自然数的运行时槽地址。与游标或内部计数槽冲突时抛 ValueError。

零是合法元素，数组没有哨兵或内建长度；遍历必须另有计数。

## 引用与记录

### Reference

仅用于值为零或永久零头地址的引用。

- put(slot, expression)：引用赋值模板；expression 必须产生有效引用。
- copy(destination, source)：引用复制；同槽时为空操作。
- next(slot)：沿固定四格记录的 NEXT 前进，假定当前引用非零。
- bump(slot)：分配游标向负方向移动四格；只适合 RecordHeap 布局。

这些函数没有运行时有效性检查。数值载荷不能交给 Reference 写入。

### RecordHeap(macros: Macros)

固定四格布局：节点头地址 R 的 memory[R] 保持零；R-1 为幅值、R-2 为符号、R-3 为 NEXT 引用。

- initialize()：设置下一未用地址；首次 allocate 前必须执行。
- field_address(reference, field)：返回字段地址表达式；field 仅允许 1、2、3，非法值抛 ValueError。
- read(reference, field)：读取对应自然数载荷或 NEXT 引用。
- put(reference, field, expression)：字段 1/2 按自然数写，字段 3 按引用写；禁止字段 0。
- allocate(node, magnitude, sign)：申请并初始化节点，node/magnitude/sign/分配游标必须互异，否则抛 ValueError。幅值为自然数、符号为 0/1。

堆依赖新地址默认零，不逐字段清理；不要在同一个 Macros 动态起点同时使用另一种堆分配器。

### RecordList(heap: RecordHeap, name: str)

声明带 head/tail 的线性所有权链。

- append(node)：把一个已分配且未归属其他链的节点追加到尾部。
- pop(node)：从非空链移除首节点，把引用放到 node，并断开 NEXT。
- concat(other)：将另一条不相交的同堆链拼到尾部，并清空来源链。

node 不得覆盖控制槽；否则 append/pop 抛 ValueError。concat 会检查堆对象相同及控制槽不同。节点集合是否相交、节点是否已经属于其他链无法由宏检测，违反前置条件可造成环或共享所有权。

### merge_sort(macros, source: RecordList, length: int, name="归并") -> str

稳定地按 RecordHeap.MAGNITUDE 字段做自底向上链表归并排序。length 是运行时自然数槽，必须等于链长；结束时节点集合仍归 source 所有，临时链为空。相等键优先取左链。此函数不按 sign 排序，也不检查 length 与实际节点数一致。

## Arena、Chain 与指令机

### Arena(macros, width=8)

可配置记录，每个节点占 width+1 个负地址：头地址 R 永远保存零，字段位于 R-1 至 R-width。width 应至少为 1；当前构造函数不验证该值。

- initialize()：在首次 allocate 前执行。
- address(node, field)：字段范围必须为 1..width，否则抛 ValueError。
- read(node, field)：读取字段。
- put(node, field, expression, reference=False)：写数值字段；reference=True 时按引用路由。
- link(node, field, target)：将字段写成 target 引用。
- allocate(node)：分配零初始化记录；结果槽不能等于 bump 槽，否则抛 ValueError。
- follow(destination, source, field)：读取 source.field 并写到 destination；允许两者同槽。

字段类型由调用者保证。一个 Macros 只应使用一个动态堆游标/布局；多个 Arena 或 RecordHeap 并用会重叠动态地址区。

### Chain(arena, name, next_field=8)

声明 Arena 字段组成的非拥有型只追加链。append(node) 要求节点有效、未造成环；调用方负责生命周期和唯一所有权。advance(pointer) 沿 next_field 更新引用游标，可以原位更新。next_field 范围由 Arena 在实际字段访问时验证。

### InstructionMachine(macros)

共享一个 Arena，字段约定为：1 opcode、2/3 可选自然数参数、4 配对括号、5 暂存括号栈前驱、8 线性后继。创建后先运行 heap.initialize()。

- emit(opcode, error, opening, closing, magnitude=None, sign=None)：生成期构造一条指令；opcode/magnitude/sign 是存放自然数的运行时槽地址，opening/closing 是生成期立即数操作码。无匹配左括号的右括号会把 error 置非零。
- code_end(error)：源码结束时仍有未闭合左括号则置 error。
- data_char(char)：把字符码点装入数据链；char 是运行时槽地址。
- jump_after_pair()：把 PC 移到活动指令配对节点之后的线性后继。
- run(error, initialize, dispatch)：生成取指循环。initialize 和 dispatch 是 DSL 文本；dispatch 自行定义每种 opcode 的语义。error 非零时停止并输出 ERROR 加 LF。

run 不提供客体 tape、I/O、循环语义或错误恢复。它是指令记录与控制流的生成模板，不是完整解释器。

## 字符帧和工具

### ERROR_OUTPUT

生成输出字节串 ERROR 加 LF 的 PP3 字符输出 DSL。

### validate_byte(macros, char, error)

将非负 char 与 255 比较，超出范围时把 error 置为 1。调用方必须保证 char >= 0，并让参数避开比较宏内部 scratch。

### frame_program(macros, prepare, consume, finish) -> str

读取一行整数长度，再读取恰好该数量的字符码点。回调分别在 Python 生成期调用：prepare(m, length)、consume(m, char)、finish(m, length)。它们返回 DSL 文本，不接收运行时字符值。

负长度输出 ERROR 且不读取帧；非字节码点设置错误，但余下帧仍消费；只有完整有效帧才执行 finish。提前 EOF 和 @input 解析错误传播。帧长度统计字符缓冲实际交付的码点，缓冲补回的 LF 也计入长度。

### literal(text: str)

将固定文本生成为一串 &ord(character) @print_as_char。运行时字符输出按 256 取模；此 API 不是 UTF-8 编码器。非 ASCII 字符会按码点低 8 位输出。

### dual_frame(macros, prepare, code_char, code_end, data_char, finish) -> str

读取两个非负长度头，再连续读取源码帧和数据帧，不在两帧间插入分隔字符。回调在生成期被调用，分别负责初始化、处理每个源码码点、检查代码结束、处理数据码点和生成成功后的执行代码。

负长度输出 ERROR，且不读 payload；有效长度下即使源码/码点已标错，仍消费声明的剩余帧以保持缓冲边界；成功时才运行 finish 返回的 DSL。宿主帧提前 EOF、整数解析错误不捕获。精确顺序与错误路径见[帧与指令机](io-machines.md)。
