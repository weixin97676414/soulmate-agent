# 架构分析方法

阶段2 使用。目标：**让人在 10 分钟内建立正确的心智模型**。

## 四个必答问题

分析完必须能回答：

1. **入口在哪** —— 程序从哪开始执行
2. **分几层** —— 每层干什么，代表类是哪个
3. **数据/控制怎么流** —— 主调用链是什么
4. **怎么扩展** —— 我想加功能该动哪里

答不出任何一个，说明没分析透。

## 一、分层识别

| 层 | 典型目录名 | 职责 | 找什么 |
|----|-----------|------|--------|
| 接口层 | controller / api / handler / routes | 接收外部请求 | 路由表、参数校验 |
| 业务层 | service / domain / core / usecase | 核心逻辑 | 事务边界、领域对象 |
| 数据层 | dao / repository / mapper / model | 持久化 | ORM 映射、连接管理 |
| 基础设施 | config / common / util / infra | 通用能力 | 配置加载、工具类 |
| 扩展层 | spi / plugin / extension / hook | 插件机制 | 扩展点接口与注册方式 |

**每层要给出：职责一句话 + 2-3 个代表类（带 `路径:行号`）+ 该层文件数。**

## 二、模块依赖

1. 从构建文件读模块划分（Maven modules / Gradle subprojects / workspace）
2. 从 import 语句统计模块间依赖方向
3. **检查循环依赖** —— 发现了就是重点踩坑点

输出格式：

```markdown
| 模块 | 依赖谁 | 被谁依赖 | 职责 |
|------|--------|----------|------|
| core | — | api, service | 核心抽象 |
| api | core | — | 对外接口 |
```

## 三、主调用链

挑 3-5 条**用户最常走**的路径，不是最复杂的：

```markdown
### 调用链 1：<场景名，如"处理一个 HTTP 请求">
DispatcherServlet.doDispatch (framework:1034)
  → HandlerMapping.getHandler (framework:1187)
  → UserController.list (controller/UserController.java:42)
  → UserService.listUsers (service/UserService.java:28)
  → UserMapper.selectList (mapper/UserMapper.java:15)
```

选链标准：覆盖了核心能力的路径优先；每链 4-8 跳，太长拆分。

## 四、扩展机制

| 机制 | 识别方法 | 说明 |
|------|----------|------|
| SPI | `META-INF/services/`、`ServiceLoader` | Java 标准扩展 |
| 插件目录 | plugins/ 目录 + 扫描逻辑 | 运行时加载 |
| 钩子/回调 | 接口名含 Hook/Listener/Callback | 事件驱动 |
| 配置点 | `@ConfigurationProperties`、配置项常量类 | 不改代码调行为 |
| 覆盖 Bean | `@ConditionalOnMissingBean` | 框架留给用户的口子 |

**这一节直接决定"能不能改得动"，不能省。**

---

# Spring 依赖注入专项

Spring 生态项目必做。这是使用者最容易踩坑、也最能体现"是否真懂"的部分。

## 三种注入方式对比

| 方式 | 写法 | 优点 | 缺点 | 适用 |
|------|------|------|------|------|
| **构造器** | `public A(B b){this.b=b;}` | 依赖不可变、可测（无需容器）、**能暴露循环依赖** | 参数多时冗长 | **默认推荐** |
| **Setter** | `@Autowired void setB(B b)` | 可选依赖、可重新注入 | 对象可能处于不完整状态 | 可选依赖 |
| **字段** | `@Autowired private B b;` | 最省字 | **不可测、隐藏依赖、易循环依赖、无法 final** | 不推荐 |

判定依据从 `scan_project.py` 的 `spring.injection` 字段直接读：

```json
"injection": {"field": 12, "constructor": 0, "setter": 1}
```

**全是字段注入 → 必须写入踩坑点**（可测试性与循环依赖风险）。

## 多实现的选择机制

当一个接口有多个实现时，按优先级：

| 机制 | 作用范围 | 说明 |
|------|----------|------|
| `@Qualifier("name")` | 注入点 | 按 Bean 名精确指定 |
| `@Primary` | 实现类 | 设默认值，可被 `@Qualifier` 覆盖 |
| `@Profile("dev")` | 实现类 | 按环境切换 |
| `List<T>` 注入 | 注入点 | 拿到全部实现，常用于策略模式 |
| `@ConditionalOnMissingBean` | 自动配置 | 用户自定义优先，框架兜底 |

## Bean 作用域与生命周期

- `singleton`（默认）：容器启动时创建（除非 `@Lazy`）
- `prototype`：每次注入新建，**容器不负责销毁**
- `request` / `session`：Web 上下文专用
- 生命周期顺序：构造 → `@PostConstruct` → `InitializingBean.afterPropertiesSet` → 使用 → `@PreDestroy` → `DisposableBean.destroy`

## 循环依赖

| 类型 | Spring 能否解决 | 原因 |
|------|----------------|------|
| 字段/setter 循环依赖 | **能**（三级缓存提前暴露引用） | 对象已实例化，可先给引用后填属性 |
| 构造器循环依赖 | **不能**，启动报 `BeanCurrentlyInCreationException` | 构造都完不成，拿不到引用 |
| `prototype` 循环依赖 | 不能 | 不缓存 prototype 实例 |

**这是最有价值的踩坑点之一**——现象明确、原因清晰、可预防（统一用构造器注入，让问题在编译期/启动期暴露）。

## 自动配置

- 入口：`META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`（Boot 3）或 `spring.factories`（Boot 2）
- 条件装配：`@ConditionalOnClass`（类路径有某类）、`@ConditionalOnMissingBean`（用户没配才生效）、`@ConditionalOnProperty`（配置开关）
- 覆盖默认 Bean：自己定义同名/同类型 Bean，自动配置的因 `@ConditionalOnMissingBean` 而让位

## 分析输出要求

Spring 项目必须额外给出：

1. **注入方式统计**（来自扫描器）+ 风险提示
2. **Bean 清单**（stereotype 分布：@Component/@Service/@Repository/@Controller/@Bean 各多少）
3. **条件装配点**（哪些 Bean 是"用户可覆盖"的）
4. **循环依赖风险点**（构造器注入 + 相互引用的类）
