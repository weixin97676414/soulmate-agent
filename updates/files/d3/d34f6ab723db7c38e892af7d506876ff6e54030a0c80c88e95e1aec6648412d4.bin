---
name: test-writing
description: 跨语言编写与运行测试：Jest/Vitest、pytest、Go、Rust、Bash 的单元/集成测试、异步处理、Mock 依赖、覆盖率度量与失败调试。触发场景：搭测试套件、写单元/集成测试、Mock 依赖、度量覆盖率、调试 flaky 用例。
author: Soulmate Agent团队成员：岸
---

# 功能：跨语言测试编写

## 适用场景
为新项目搭建测试套件、编写单元/集成测试、度量覆盖率、Mock 外部依赖（API/数据库/文件系统）、调试不稳定或失败测试。覆盖 Node.js（Jest/Vitest）、Python（pytest）、Go、Rust、Bash。

## 边界
- 本技能只做「跨语言编写并运行测试」：单测/集成测试的架子、Mock、覆盖率度量与失败调试。
- 整体测试策略、覆盖率目标与发布门槛归 `test-planning`；逐条用例设计归 `test-case-generation`。
- TDD 的红-绿-重构纪律归 `tdd`，本技能只保证测试写得对、跑得起来。

## 步骤

1. **搭环境**：按语言安装框架（Node: `npm install -D jest` 或 `vitest`；Python: `pip install pytest pytest-cov`）。
2. **写单元测试**：一个行为一个测试，命名描述行为（`test_returns_empty_list_when_no_users_exist` 优于 `test_get_users_2`）。
3. **处理异步**：`async/await` + `rejects.toThrow`（JS）；`pytest-asyncio`/`AsyncMock`（Python）。
4. **Mock 依赖**：Mock 模块函数与网络（JS `jest.mock` / `global.fetch = jest.fn()`；Python `unittest.mock.patch`、`AsyncMock`、上下文管理器 mock）。**不要 mock 你不拥有的东西**——写薄包装再 mock 包装。
5. **度量覆盖率**：`npx jest --coverage` / `pytest --cov=mypackage --cov-report=term-missing --cov-fail-under=80` / `go test -coverprofile=coverage.out ./...`。
6. **集成测试**：启动真实服务/数据库（Bash 起服务+trap 清理；Python `:memory:` SQLite fixture）。
7. **调试失败测试**：见「注意事项」。

## 各语言要点

- **Node.js**：`describe/test/expect`；参数化用 `test.each`；覆盖率阈值在 `jest.config.js` 的 `coverageThreshold`。
- **Python**：`pytest.mark.parametrize`、fixture（`tmp_path`、yield 清理）、`pytest.approx`、`pytest.raises`。
- **Go**：表驱动测试 + `t.Run`；`go test -race` 检测竞态；`go test -bench=.` 做基准。
- **Rust**：`#[cfg(test)] mod tests`、`assert_eq!`、`#[should_panic]`；`cargo tarpaulin` 覆盖率。
- **Bash**：自建最小断言框架（`assert_eq` / `assert_exit_code` / `assert_contains`），统计 `PASS/FAIL`，`exit 1` 表示失败。

## 输入输出
- 输入：被测代码、语言/框架、测试类型。
- 输出：可运行的测试文件 + 覆盖率报告 + 失败清单。

## 注意事项
- 测行为不测实现，测试应能挺过重构。
- 一个概念一个断言；不要为覆盖率硬凑。
- 调试常见失败：
  - **单跑通过、成套失败** → 共享状态（全局变量、未清理数据库、mock 未还原，用 `afterEach`/teardown）。
  - **间歇性失败（flaky）** → 时序或顺序问题（缺 `await`、依赖执行顺序、时间相关逻辑、单测里有网络调用）。
  - **覆盖率显示未覆盖分支** → 缺边界用例（错误路径、空输入、边界值 0/-1/MAX_INT）。
- `tmp_path`（pytest）/`t.TempDir()`（Go）/`tempfile`（Node）用于文件类测试。
- 快照测试适合发现意外变更，不适合演化中的格式。

## 可复用示例
```python
@pytest.mark.parametrize("a,b,expected", [(2,3,5),(-1,1,0),(0,0,0),(100,-50,50)])
def test_add_cases(a, b, expected):
    assert add(a, b) == expected
```
```javascript
test('throws on division by zero', () => {
  expect(() => divide(10, 0)).toThrow('Division by zero');
});
```
```bash
# 快速反馈
npx jest --watch          # Node
ptw                       # pytest-watch
ls *.go | entr -c go test ./...   # Go
```
