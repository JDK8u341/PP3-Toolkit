# 宏与数值模型

本文描述 PP3 Toolkit 的通用宏语义和输入/输出表示。所有方法都在 Python 生成期返回 DSL 文本；宏名字中的“加法”“比较”指的是生成出的 PP3 程序所做的事，不是 Python 在构建期间先算出答案。

## 数据表示约定

Toolkit 不提供静态类型系统，但宏依赖三个互不等价的表示：

| 表示 | 允许值 | 用途 |
| --- | --- | --- |
| 自然数标量 | 整数 n >= 0 | 计数、幅值、索引、布尔值 |
| 引用 | 0 或零头地址 R | 节点身份、NEXT、游标 |
| 符号/幅值对 | magnitude >= 0，sign 为 0 或 1 | 任意有符号整数；数学值为 sign=1 时的 -magnitude，否则为 magnitude |

所有布尔值输出都规范为 0 或 1。普通数值槽不得直接存负载荷；负整数由幅值和符号分开保存，负零被规范为正零。引用则必须通过引用专用写入宏处理，不能当自然数写入。

## 最小可组合模板

~~~python
from pp3_toolkit import Macros, compile_program, seq


def program(m: Macros) -> str:
    x = m.slot("demo.x")
    y = m.slot("demo.y")
    less, equal, greater = (m.slot(name) for name in (
        "demo.lt", "demo.eq", "demo.gt",
    ))
    flag = m.slot("demo.flag")
    return seq(
        m.put(x, "@input"),
        m.constant(y, 10),
        m.compare(x, y, less, equal, greater),
        m.copy(flag, less),
        m.read(flag) + " @print",
    )


print(compile_program(program), end="")
~~~

输入/输出操作会出现在 PP3 源码中。生成器不接收输入值。关于生成器会运行两次以及槽布局的完整说明见[实现机制](mechanism.md)。

## 控制流

### once(condition, body)

展开为一次非零分支：先执行 condition 产生测试值；若 view 非零，执行 body，再把 view 清零。它不是循环。body 对内存的副作用会保留，结束时被重置的是 view。

### if_nonzero(condition, nonzero, zero)

根据 condition 的 view 是否为零，执行且只执行一个分支。内部使用一个具名临时标志槽；两条路径都在分支交接处清理 view。宏不会复制或保护调用者表达式中任意其他槽。

### if_zero(condition, body)

等价于 if_nonzero(condition, 空代码, body)。condition 仍须是一段执行后把测试值放入 view 的 DSL。

### loop(condition, body)

先评估 condition，非零时进入循环；每次 body 后重新评估 condition。宏不会检查终止性。body 必须最终让条件变零；若条件永不清零，生成程序就会一直循环。

这些模板的括号通过独立的 [ 和 ] 行构造，compile_program 最后仅检查括号配对，不会解析完整 PP3 语法。

## 局部标记判等

Macros.equal(a, b, result) 不通过从 a、b 同步减到零来判等，而是把自然数键 k 表示为正地址 k+1，并临时标记该地址。其前置条件是正地址图只含约定的零值或集合标记 -1，且 -2 没有其他未结束的临时用途。

核心步骤如下：

1. 计算 a+1，记作指针 P；读取 P 当前是否为 -1，保存成 0/1。
2. 把 memory[a+1] 临时改为 -2。
3. 读取 memory[b+1] 并加 2。若结果为零，只有 b=a 时才成立：原值 -2 表示判等临时标记；空标记 0 和集合标记 -1 加 2 后分别为 2、1。
4. 根据保存的状态，把 memory[a+1] 恢复成原来的 0 或 -1。

输入 a、b 保持不变；result 得到 0/1。对逻辑集合状态做了恢复，不代表宿主 defaultdict 一定删除了新建的零值字典项。输入/输出不能与内部 scratch 槽别名，且同一运行时不能有另一个尚未恢复的 -2 判等标记。

这让判等的 PP3 控制流不随 a、b 的差值增加，也不枚举数值范围；但地址仍是宿主任意精度整数，字典访问/哈希的实际成本仍会受整数大小影响。准确成本边界见[成本模型](cost-model.md)。

## 自然数顺序比较

Macros.compare(a, b, lt, eq, gt) 先调用上述判等。相等时只写 eq=1；不等时：

1. 将 a、b 复制到工作槽 A、B。
2. 只要 A、B 都非零，同步执行 A--、B--。
3. 若 A 仍非零，则 a>b，写 gt=1；否则写 lt=1。

三个结果恰有一个为 1，原输入保持不变。lt、eq、gt 必须彼此不同，也不能覆盖输入或内部 scratch。这个算法适用于任意自然数，但不等路径要执行与 min(a,b) 相关的递减轮次；若需要按二进制位数增长的比较，请勿把它描述为本宏已有保证。

in_range(x, low, high, out) 先比较 x 与生成期常量 low，再在未小于 low 时比较 x 与 high。区间为闭区间，要求 0 <= low <= high；out 是 0/1，x 保持不变。

## 有符号整数输入

decode_integer(magnitude, sign) 生成一条标准 @input 指令，并把读到的带符号整数拆为：

~~~text
magnitude = abs(input)
sign = 1  当 input < 0
sign = 0  当 input >= 0
~~~

因此 -0 的规范结果为 magnitude=0、sign=0。该方法依赖 PP3 原版 @input 的整数解析：解析异常和 EOFError 不由 Toolkit 捕获。允许处理的实际位数还受宿主 Python/PP3 实现资源与整数解析限制影响，不能把数学上的“任意整数”解释为无资源上限。

实现过程可概括为一对相反方向的图内探针：

1. 将原始输入暂存在内部槽 P，并复制到 Q；步数 k 从 0 开始。
2. 每轮先让 P 中的暂存值减一；若未到零，再让 Q 中的暂存值加一。k 同步计数。
3. P 先到零表示输入非负，结果幅值为 k、符号为 0；Q 先到零表示输入为负，幅值为 k、符号为 1。输入为零时会在正式竞速前结束为 0/正号。
4. 原始整数也可能恰好等于负地址 P 或 Q。若探针候选值将碰到这两个内部地址，宏会用已走步数和碰撞地址直接恢复幅值并停止，而不是把 scratch 地址当成普通图边继续走。
5. 清除暂存探针后，把规范化的幅值和符号写入调用者结果槽。

这是对两个方向的整数距离进行计数，不是为每个可能输入值生成分支，也不是扫描整个负地址保留区。调用者不要把结果槽或其他业务槽命名为该宏的内部槽名；API 参考列出 scratch 名称。

最小输出模式可写为：

~~~python
mag, sign = m.slot("signed.mag"), m.slot("signed.sign")
code = seq(
    m.decode_integer(mag, sign),
    m.once(m.read(mag), m.once(m.read(sign), "&45 @print_as_char")),
    m.print_unsigned_decimal(mag),
    "&10 @print_as_char",
)
~~~

示例中的减号是字节 45；十进制宏只输出数字，不自动附加换行。

## 算术宏的前置条件

### 加法与减法

- add_into(dst, src) 执行 dst += src；槽不同则 src 保持不变，dst 和 src 相同时合法地将原值加到自身。
- subtract_from(dst, src) 执行 dst -= src，要求初始 dst >= src。src 与 dst 不同时保留 src；dst==src 时结果为零，原值当然不再保留。
- 两个宏都用一个计数槽逐次增减，因此执行量与 src 的数值成正比，不是位宽复杂度。

### 常数乘十

multiply_by_ten(x) 原位令 x 变成 10x。每轮把原 x 加十次，使用 scratch 计数。执行量与输入 x 成正比；名字中的“常数”指乘数为 10，不代表宏只执行固定条数的 PP3 操作。

### 无符号除法

divmod_unsigned(n, d, q, r) 要求 n >= 0、d > 0，输出 q=floor(n/d)、r=n mod d。输入 n、d 保持不变；q、r 被覆盖且必须不同。实现从工作副本 n 逐个减一，用倒数计数维护除数批次，因此工作量与 n 的数值成正比。d=0 没有有效结果，也不会产生受支持的错误输出。

为保留输入，请让 n、d、q、r 使用互不别名的槽。当前实现硬检查 q != r 和 scratch 冲突；它不检查所有输入/输出别名组合。

### 十进制输出

print_unsigned_decimal(x) 保留 x，以 PP3 字符输出格式化的非负十进制数，不添加 LF。零输出为 0。调用者需要自行输出空格或换行。它反复构造十进制位权并使用上述重复减法除法，运行工作量与数值大小相关，而不是单纯与十进制位数相关。

## Scratch 与别名规则

同一 Macros 对象把所有 slot(name) 放进一个全局名字表。下表中出现的名称是实现实际申请的槽名，不是建议命名；业务槽不得主动使用这些名字。

| 模板 | 固定 scratch 名称 |
| --- | --- |
| 条件宏 | 条件标志1、条件标志2、……，按生成期调用顺序分配 |
| equal | 等值地址、等值原标记 |
| compare | 比较副本A、比较副本B、比较继续；并使用 equal 的 scratch |
| in_range | 区间下界、区间上界、区间小于、区间等于、区间大于；并使用 compare/equal 的 scratch |
| decode_integer | 解码P、解码Q、解码步数、解码继续；需要加法计数、减法计数及条件标志 |
| add_into / subtract_from | 加法计数 / 减法计数 |
| multiply_by_ten | 乘十计数 |
| divmod_unsigned | 除法工作、除法分母、除法倒数 |
| print_unsigned_decimal | 输出数值、输出位权、输出探测、常数十、输出商、输出余数；并使用除法/乘十 scratch |

实现对部分宏冲突会直接抛 ValueError，但并未对每个复合宏的所有别名组合做完整静态证明。推荐为业务槽统一使用前缀，例如 题目.计数，并避免本表名称。

复合宏的 scratch 在整个生成程序中静态复用。顺序重复调用通常可行；若一个宏执行过程中再进入另一个会覆盖同一 scratch 的宏，或者让 scratch 槽同时承担业务数据，必须单独证明安全。

更完整的逐 API 签名、错误行为和 alias 注意事项见 [API 参考](api.md)。
