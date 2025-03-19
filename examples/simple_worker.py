#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
简单的工作节点示例
演示如何使用 worker SDK 创建一个简单的工作节点
"""

import logging
import argparse
from dotenv import load_dotenv
load_dotenv()

# 导入所需的模块
from callme import register_handler, worker_sdk, HttpJob

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("example-worker")

# 注册一个简单的回显处理器
@register_handler("/api/echo", method="POST", timeout=10)
def echo_handler(job: HttpJob):
    """简单的回显处理器，返回接收到的数据"""
    request_data = job.body.get("data", {})
    
    # 记录接收到的请求
    logger.info(f"收到回显请求: {request_data}")
    
    # 简单地返回接收到的数据
    return {
        "success": True,
        "echo": request_data,
        "message": "这是一个回显响应"
    }

# 注册一个健康检查处理器
@register_handler("/api/health", method="GET", timeout=5)
def health_check(job: HttpJob):
    """健康检查处理器"""
    return {
        "status": "ok",
        "service": "example-worker",
        "message": "服务运行正常"
    }

def main(version=None):
    """工作节点主函数"""
    # 使用 worker SDK 启动工作节点
    worker_sdk.on_call(version=version)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动示例工作节点")
    parser.add_argument("--version", help="工作节点版本", default="example-worker-v1")
    args = parser.parse_args()
    
    main(version=args.version) 