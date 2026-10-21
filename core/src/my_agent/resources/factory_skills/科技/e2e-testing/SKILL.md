---
name: e2e-testing
description: 用 Playwright/Cypress 构建稳定快速的端到端测试：配置、Page Object Model、fixtures、智能等待、网络 Mock、选择器策略、视觉回归、可访问性、CI 集成与 flaky 排查。触发场景：实施 E2E、关键用户流程测试、消除 flaky、搭建浏览器测试流水线。
author: Soulmate Agent团队成员：岸
---

# 功能：端到端（E2E）测试

## 适用场景
为 Web 应用实施 E2E 自动化、调试间歇性失败（flaky）用例、搭建 CI/CD 浏览器测试流水线、测试关键用户流程（登录/结算/注册）、判断什么该用 E2E 而非单元/集成测试。

## 测试金字塔定位
```
        /\
       /E2E\      ← 少：只覆盖关键路径
      /─────\
     /Integr\    ← 较多：组件交互、API 契约
    /────────\
   /Unit Tests\ ← 多：快、隔离、覆盖边界
  /────────────\
```
判断：**业务上坏了会「灾难性」的才做 E2E；只是不便的用更快的单测/集成测**。

## 步骤

1. **配置**：`playwright.config.ts` 设 `testDir`、`timeout`、`expect.timeout`、`fullyParallel`、CI 下 `forbidOnly`/`retries`/`workers`、reporter（html+junit）、use.baseURL/trace/screenshot/video、多浏览器 projects。
2. **用 Page Object Model 封装页面逻辑**，让测试读起来像用户故事。
3. **用 fixtures 自动准备/清理测试数据**（setup 创建用户，teardown 删除）。
4. **智能等待**：禁用固定超时，改为等条件：
   ```typescript
   // ❌ await page.waitForTimeout(3000);
   await page.waitForLoadState("networkidle");
   await page.waitForURL("/dashboard");
   await expect(page.getByText("Welcome")).toBeVisible();
   const r = page.waitForResponse(x => x.url().includes("/api/users") && x.status() === 200);
   ```
5. **网络 Mock 隔离外部服务**：`page.route(...)`（Playwright）/ `cy.intercept(...)`（Cypress），模拟 500、慢网络等。
6. **选择器策略**（优先级从高到低）：

   | 优先级 | 选择器 | 例 |
   |---|---|---|
   | 1 | Role + name | `getByRole("button", { name: "Submit" })` |
   | 2 | Label | `getByLabel("Email address")` |
   | 3 | data-testid | `getByTestId("checkout-form")` |
   | 4 | 文本内容 | `getByText("Welcome back")` |
   | ❌ | CSS 类 / DOM 结构 | `.btn-primary` / `div > form > input:nth-child(2)` |

7. **视觉回归**：`toHaveScreenshot("homepage.png", { fullPage: true, maxDiffPixels: 100 })`。
8. **可访问性**：`@axe-core/playwright` 的 `AxeBuilder`，`expect(results.violations).toEqual([])`。
9. **CI 集成**：GitHub Actions 装依赖 → `npx playwright install --with-deps` → build → 起服务 → 跑测试 → 失败时上传 `playwright-report/`。

## 输入输出
- 输入：Web 应用 + 关键用户旅程 + CI 环境。
- 输出：可稳定运行的 E2E 测试套件 + 报告/trace + CI 流水线配置。

## 注意事项
- **永不做**：固定 `waitForTimeout`/`cy.wait(ms)`；用 CSS 类或 DOM 结构当选择器；测试间共享状态；测实现细节；跳过清理；用 E2E 测所有东西；忽略 flaky 用例（要么立即修，要么删除——flaky 比没有更糟）；把易变内容硬编码进选择器。
- **Flaky 排查表**：固定超时 → 换成等选择器/断言；页面加载竞态 → 等 networkidle 或具体元素；测试数据污染 → 各自创建/清理；动画时序 → 等动画完成或禁用；视口不一致 → 显式设 viewport；测试顺序依赖 → 必须独立；第三方服务抖动 → Mock。
- 调试：`npx playwright test --headed` / `--debug` / `npx playwright show-report`；用 `test.step` 分段让失败定位更准；`await page.pause()` 手动检查。

## 可复用示例
```typescript
test("shows error when API fails", async ({ page }) => {
  await page.route("**/api/users", route =>
    route.fulfill({ status: 500, body: JSON.stringify({ error: "Server Error" }) }));
  await page.goto("/users");
  await expect(page.getByText("Failed to load users")).toBeVisible();
});
```
