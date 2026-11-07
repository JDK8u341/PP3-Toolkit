# 示例

本目录的 Python 文件仅生成固定 PP3 源码，不读取题目输入。生成器函数也由测试导入并交给原版 Runtime 执行。

## 有符号加法

```powershell
python -m examples.signed_add > signed-add.pp3
```

PP3 程序读取两行任意有符号整数并输出一行和。示例演示将每个输入拆为幅值/符号、同号相加、异号比较幅值后相减，再规范化输出符号。

## 稳定归并排序

```powershell
python -m examples.stable_sort > stable-sort.pp3
```

PP3 程序先读数量，再读相应数量的非负整数，每行输出一个升序结果。实现用独立零头节点表示元素身份，载荷可以重复或超过字节范围。归并相等值优先取左链，因而稳定。

生成 `.pp3` 后，把它交给所选 PP3 安装的 `IRBuilder(op_map=std_register)`；题目运行时使用 `Runtime(can_direct_addressing=False)`。测试子模块提供固定参考版本，见仓库根目录测试。
