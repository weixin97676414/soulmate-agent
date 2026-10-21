# Demo 生成规范

阶段4 使用。对应验收标准「输出的 demo 符合实际的需求」。

## 形态选择

| 项目类型 | 形态 | 交付物 |
|----------|------|--------|
| 框架类（Spring/Django/Express…） | **完整工程** | 构建文件 + 目录结构 + 配置 + 源码 + README |
| 工具类库 | **单文件示例** | 一个示例文件（头部注释含依赖与运行命令） |
| 用户明确"要能直接跑" | 完整工程 | 同上 |

## 完整工程的结构

```
demo-<能力名>/
├── pom.xml / build.gradle / package.json   ← 依赖版本写死
├── src/main/java/.../DemoApplication.java  ← 入口
├── src/main/java/.../<按能力分包>/
├── src/main/resources/application.yml      ← 配置（带注释）
├── src/test/java/.../                      ← 至少一个可运行的验证测试
└── README.md                                ← 怎么跑 + 跑完看到什么 + 怎么改
```

**缺 README 或测试，不算完整工程。**

## 注释标准

注释回答「为什么」，不是复述「是什么」：

```java
// ❌ 复述代码
@Autowired  // 自动注入

// ✅ 解释原因
// 用构造器注入而非字段注入：依赖声明为 final 保证不可变，
// 且单元测试时可直接 new OrderService(mockPay)，无需启动 Spring 容器。
// 若改成字段注入，循环依赖会被三级缓存掩盖，直到运行时才暴露问题。
public OrderService(PayClient payClient) {
    this.payClient = payClient;
}
```

必注释处：
- 每个关键 API 调用（为什么用这个而不是另一个）
- 每个配置项（取值含义、不配会怎样）
- 每个容易踩坑的写法（这里为什么这么绕）
- 依赖版本（为什么锁定这个版本）

注释率门槛 15%（`check_demo.py` 会查）。

## 版本锁定

**禁止** `latest`、`RELEASE`、`+`、`*`。写明具体版本：

```xml
<!-- Spring Boot 3.2.5：3.2.x 中 DI 行为一致；若降到 2.7，
     @ConstructorBinding 的用法需要调整 -->
<version>3.2.5</version>
```

并在注释里说明版本选择的理由与兼容边界。

## 验证步骤

每个 Demo 必须能回答"跑完我看到什么就说明对了"：

```markdown
## 验证

1. `mvn spring-boot:run`
2. 控制台出现 `Started DemoApplication in 1.8 seconds` → 启动成功
3. 访问 `http://localhost:8080/di/constructor`
   预期返回：`{"injectionType":"constructor","payClient":"mock"}` 
4. 若返回 500 且日志含 `BeanCurrentlyInCreationException` → 命中循环依赖，见踩坑点 N
```

**预期输出要具体到字符串，不写"应该能正常工作"。**

## 生成后自检

```bash
python scripts/check_demo.py <demo目录> --min-comment 0.15
```

有 ERROR 必须修完再交付。常见 ERROR：
- 缺构建文件
- 浮动版本号
- TODO/占位符未清理
- 注释率不足

## 优质判据

- [ ] 有构建文件且依赖版本写死
- [ ] 有入口，能直接运行
- [ ] 注释覆盖关键 API 与配置，解释「为什么」
- [ ] README 写清：怎么跑、跑完看到什么、想改哪里改哪个文件
- [ ] 至少一个可运行测试
- [ ] `check_demo.py` 无 ERROR

## 常见错误

- ❌ 只给代码片段，没有构建文件（跑不起来）
- ❌ 依赖写 `latest`（下次构建就可能挂）
- ❌ 注释复述代码（"这行是注入"）—— 没有信息量
- ❌ 只说"运行即可"，不说预期输出（用户不知道成功长什么样）
- ❌ Demo 用了项目里不存在的 API（凭记忆写的，必须核对版本）
