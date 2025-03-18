# CallMe Gate 

编写这个组件的初衷，是因为我希望有一个公网的服务，同时可以使用本地的进行对这个服务的请求进行响应。

网络上有一些 SaaS 平台，都支持进行 回调（事件）这个特性，假如我们有一个稳定的服务器，接受这些回调，会让我们的 Service 多很多的扩展。

同时，要部署一个稳定的服务器，需要在线上一直部署一个 ECS，但对个人来说，这个非常浪费。那基于现在越来越便宜的云平台，我们可以使用一些便宜的服务方案，加上一些个人设备的运算能力，可以做一个非常简单的低负载联网网关，提供一个非常便宜及简洁的 Service 服务器。因此我花了一点时间，编写了这个框架。

技术调研上，我们可以将 gate 打包成一个**函数计算**程序包，可以发布到 aliyun 函数计算产品中，再使用一个 redis 实例保存请求，再通过本地进程消费 redis 中保存的请求。也就是说：gate 节点保存在线上， worker 节点可以保存在任意的进程中，甚至是你的移动设备。

## 核心功能

- **HTTP请求路由**: 将客户端请求路由到合适的工作节点处理
- **请求跟踪**: 通过Redis存储跟踪所有HTTP请求和响应数据
- **动态路由注册**: 工作节点可以动态注册API路由
- **服务发现**: 支持工作节点的自动注册和发现
- **计数器API示例**: 包含完整的计数器API实现示例
- **高可用设计**: 支持多工作节点横向扩展

## TODO
[ ] 注册时通过分布式锁，避免路由状态错误
[ ] 测试请求实际网络延迟
[ ] 实现一个简单的鉴权处理
[ ] worker 的心跳机制, 避免强杀进程导致路由状态错误。

## 系统架构

```
客户端 -> 网关(gate.py) -> Redis队列 -> 工作节点(worker.py) -> Redis存储 -> 网关响应客户端
```

## 项目结构

```
.
├── gate.py              # 网关应用入口
├── worker.py            # 工作节点应用入口
├── run.sh               # 运行脚本
├── build.sh             # 构建脚本
├── lib/                 # 核心库文件
│   ├── app_worker.py    # 工作节点核心逻辑
│   ├── redis_client.py  # Redis客户端
│   ├── counter.py       # 计数器功能示例
│   ├── model/           # 数据模型
│   │   ├── job.py       # 基础作业类
│   │   ├── http_job.py  # HTTP作业类
│   │   └── job_repository.py # 作业存储库
│   ├── router/          # 路由系统
│   │   ├── http_job_router.py # HTTP作业路由器
│   │   ├── job_dispatcher.py  # 作业分发器
│   │   ├── node.py           # 节点管理
│   │   ├── route.py          # 路由定义
│   │   ├── route_registry.py # 路由注册表
│   │   └── route_strategy.py # 路由策略
│   ├── lock/            # 分布式锁
│   └── auth/            # 认证相关
├── tests/               # 测试文件
├── logs/                # 日志文件
├── .pid/                # 进程ID文件
└── requirements.txt     # 依赖库
```

## 核心模块说明

### 网关 (gate.py)

网关是系统的入口点，负责接收所有客户端请求，并将请求转发给适当的工作节点处理。网关通过装饰器 `@process_via_gateway` 将API请求转换为HttpJob对象并推送到Redis队列。

### 工作节点 (worker.py)

工作节点从Redis队列中获取作业并处理。工作节点通过 `@register_handler` 装饰器将处理函数注册到特定路由路径和HTTP方法。

### 应用工作节点 (lib/app_worker.py)

实现了工作节点的核心逻辑，包括任务队列处理、路由处理器注册、以及处理结果的返回。

### HTTP作业 (lib/model/http_job.py)

表示一个HTTP请求作业，包含请求和响应的所有相关信息，支持序列化和反序列化。

### 路由系统 (lib/router/)

- **http_job_router.py**: HTTP路由处理
- **route_registry.py**: 路由注册管理
- **job_dispatcher.py**: 任务分发和结果处理
- **route_strategy.py**: 路由策略实现（如轮询、随机等）

### 计数器示例 (lib/counter.py)

提供了一个完整的计数器API实现，演示如何使用网关-工作节点架构构建功能。

## 环境要求

- Python 3.7+
- Redis服务器
- 可选依赖库：Flask, redis, tabulate, python-dotenv

## 环境变量

在 `.env` 文件中配置：

```
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_USE_SSL=false
```

## 快速开始

1. 安装依赖

```bash
pip install -r requirements.txt
```

2. 启动Redis服务器

3. 运行工作节点

```bash
python worker.py
```

4. 运行网关服务

```bash
python gate.py
```

网关默认在 http://localhost:9000 启动。

## API端点

### 系统API

- `GET /health`: 健康检查
- `GET /routes`: 获取所有已注册路由信息

### 计数器API示例

- `POST /api/counter/increment`: 增加计数器，参数 `{"name": "计数器名", "amount": 数量}`
- `POST /api/counter/decrement`: 减少计数器，参数 `{"name": "计数器名", "amount": 数量}`
- `POST /api/counter/reset`: 重置计数器，参数 `{"name": "计数器名"}`
- `GET /api/counter/get?name=计数器名`: 获取计数器值

## 工作节点扩展

系统支持多工作节点并行处理请求。可以通过启动多个工作节点实例来扩展系统处理能力：

```bash
python worker.py --version worker-1
python worker.py --version worker-2
...
```

## 使用示例

### 增加计数器

```bash
curl -X POST http://localhost:9000/api/counter/increment \
     -H "Content-Type: application/json" \
     -d '{"name": "visitors", "amount": 1}'
```

### 获取计数器值

```bash
curl http://localhost:9000/api/counter/get?name=visitors
```

## 单元测试
* 本地启动一个 redis 服务
```
./run.sh test
```