# HTTP请求网关

这是一个示例项目，提供日历生成API和HTTP请求追踪功能，并实现了网关-工作节点架构。

## 功能

- 日历生成API：根据年份和月份生成格式化的日历
- HTTP请求跟踪：通过Redis存储HTTP请求和响应数据
- 网关-工作节点架构：将请求转发到工作节点处理
- 计数器功能：演示网关-工作节点架构的简单计数器API

## 架构

```
客户端 -> 网关(app.py) -> Redis队列 -> 工作节点(worker.py) -> Redis存储 -> 网关响应客户端
```

## 项目结构

```
.
├── app.py                # 主应用文件（网关）
├── worker.py             # 工作节点应用
├── lib/                  # 库文件
│   ├── redis_client.py   # Redis客户端
│   ├── app_worker.py     # 工作节点核心逻辑
│   ├── counter.py        # 计数器功能
│   ├── model/            # 数据模型
│   │   ├── job.py        # 基础作业类
│   │   ├── http_job.py   # HTTP作业类
│   │   └── job_repository.py # 作业存储库
│   └── router/           # 路由
│       └── http_job_router.py # HTTP作业路由
├── tests/                # 测试文件
└── requirements.txt      # 依赖库
```

## 安装依赖

```bash
pip install -r requirements.txt
```

## 环境变量

在 `.env` 文件中配置：

```
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=
REDIS_USE_SSL=false
```

## 运行服务

1. 启动Redis服务器
2. 启动工作节点：

```bash
python worker.py
```

3. 启动网关服务：

```bash
python app.py
```

网关将在 http://localhost:9000 启动。

## API 端点

### 基础API

- `POST /`: 日历生成API，接收JSON格式数据 `{"year": "YYYY", "month": "MM"}`
- `GET /demo`: 示例端点，用于测试
- `GET /api/jobs/<request_id>`: 获取指定ID的作业信息
- `DELETE /api/jobs/<request_id>`: 删除指定ID的作业
- `GET /api/queue/size`: 获取当前队列大小

### 计数器API

- `POST /api/counter/increment`: 增加计数器，参数 `{"name": "计数器名", "amount": 数量}`
- `POST /api/counter/decrement`: 减少计数器，参数 `{"name": "计数器名", "amount": 数量}`
- `POST /api/counter/reset`: 重置计数器，参数 `{"name": "计数器名"}`
- `GET /api/counter/get?name=计数器名`: 获取计数器值

## 网关与工作节点

- 网关(app.py)接收HTTP请求，创建HttpJob并加入Redis队列
- 工作节点(worker.py)从队列获取作业并处理
- 网关通过轮询等待处理结果，并将结果返回给客户端

## 测试

```bash
# 运行所有测试
python -m unittest discover tests

# 测试网关-工作节点架构
python -m unittest tests/test_gateway_worker.py
```

## Redis存储

所有HTTP请求会被自动存储到Redis中，键格式为 `http_job:<request_id>`，使用响应头中的 `X-Request-ID` 可以查询对应的作业信息 