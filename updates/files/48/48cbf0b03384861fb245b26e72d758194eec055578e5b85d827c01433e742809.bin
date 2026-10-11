---
name: api-testing
description: REST/GraphQL 接口测试自动化：覆盖功能测试、性能测试（并发/响应时间/吞吐）、OpenAPI/Swagger 契约校验、Mock 服务与 Allure 报告生成。触发场景：接口测试、API 自动化测试、压测接口、契约测试、Mock 后端接口、GraphQL 测试。
author: Soulmate Agent团队成员：岸
---

# 功能：API 接口测试自动化

随技能附带工具源码：`scripts/api-test-automation/`（`src/` 客户端与工具、`examples/run_tests.py` 示例、`tests/test_api_suite.py` 自测、`requirements.txt`）。

## 适用场景
对 REST / GraphQL 接口做功能测试、性能测试（并发/响应时间/吞吐）、契约测试（OpenAPI/Swagger 校验）、Mock 服务与测试报告生成。

## 步骤

1. **装依赖**（Python ≥3.8）：
   ```bash
   pip install -r scripts/api-test-automation/requirements.txt
   ```
   关键依赖：requests ≥2.28、httpx ≥0.24、pytest ≥7.0、pytest-asyncio ≥0.21、schemathesis ≥3.19、hypothesis ≥6.82、aiohttp ≥3.8、uvicorn ≥0.23、starlette ≥0.27、jsonschema ≥4.19、pyyaml ≥6.0、allure-pytest ≥2.13。
2. **调用工具模块**：把 `scripts/api-test-automation/src` 加入 `PYTHONPATH`（或安装为包后 `from api_test_automation import ...`）。核心模块：
   - `rest_client.py` — REST 客户端；
   - `graphql_client.py` — GraphQL 客户端；
   - `performance.py` — 性能测试工具；
   - `contract_tester.py` — 契约测试；
   - `mock_server.py` — Mock 服务；
   - `reporter.py` — 报告生成；
   - `assertions.py` — 断言辅助。
3. **REST 测试**：
   ```python
   from api_test_automation import RestClient
   client = RestClient(base_url="https://api.example.com")
   response = client.get("/users")
   assert response.status_code == 200
   ```
4. **GraphQL 测试**：
   ```python
   from api_test_automation import GraphQLClient
   graphql = GraphQLClient(endpoint="https://api.example.com/graphql")
   result = graphql.query("{ users { id name } }")
   ```
5. **性能测试**：用 `PerformanceTester` 做并发/响应时间/吞吐量度量。
6. **契约测试**：用 `schemathesis` + `contract_tester` 依据 OpenAPI/Swagger 校验。
7. **Mock 服务**：用 `mock_server`（基于 starlette/uvicorn）起本地 Mock。
8. **跑示例/自测**：`python scripts/api-test-automation/examples/run_tests.py`；`pytest scripts/api-test-automation/tests/`。

## 输入输出
- 输入：被测接口地址、OpenAPI/GraphQL schema、并发与阈值参数。
- 输出：功能测试结果、性能指标、契约校验结论、Mock 服务、测试报告（Allure）。

## 注意事项
- 示例采用 `from api_test_automation import ...`（需先让包可导入）；若直接跑源码目录，用相对/路径导入。
- 实际模块接口以复制到 `scripts/api-test-automation/src/` 的源码为准；本处未逐一列出全部方法签名，**具体 API 以源码为准（未逐一验证）**。
- 性能测试要有明确指标与阈值，不得无基线声称「显著提升」。
- 契约测试依赖有效的 OpenAPI/Swagger 定义；定义过时会导致误报。

## 可复用示例
> 对一个订单服务：先用 `RestClient` 跑功能用例（下单/查询/取消），再用 `PerformanceTester` 压测下单接口拿 P95，最后用 `schemathesis` 依 OpenAPI 定义跑契约测试，并用 `mock_server` 在联调期替代未就绪的支付服务。
