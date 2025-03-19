#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import argparse
import uuid
import sys
import os
from flask import Flask
from dotenv import load_dotenv
load_dotenv()

# 导入所需的模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from callme import register_handler, worker_sdk, HttpJob
from examples.counter import counter

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("counter_worker")

# 注册计数器递增处理器
@register_handler("/api/counter/increment", method="POST", timeout=10)
def increment_counter(job: HttpJob):
    """
    递增计数器处理程序
    """
    # 从请求中获取要递增的值
    request_data = job.body.get("data", {})
    increment_by = request_data.get("value", 1)
    counter_id = request_data.get("counter_id", "default")
    
    # 调用计数器服务递增计数
    new_value = counter.increment(counter_id, increment_by)
    
    # 返回响应
    return {
        "success": True,
        "counter_id": counter_id,
        "value": new_value
    }

# 注册计数器递减处理器
@register_handler("/api/counter/decrement", method="POST", timeout=10)
def decrement_counter(job: HttpJob):
    """
    递减计数器处理程序
    """
    # 从请求中获取要递减的值
    request_data = job.body.get("data", {})
    decrement_by = request_data.get("value", 1)
    counter_id = request_data.get("counter_id", "default")
    
    # 调用计数器服务递减计数
    try:
        new_value = counter.decrement(counter_id, decrement_by)
        # 返回响应
        return {
            "success": True,
            "counter_id": counter_id,
            "value": new_value
        }
    except ValueError as e:
        # 处理计数器为负的情况
        return {
            "success": False,
            "counter_id": counter_id,
            "error": str(e),
            "value": counter.get(counter_id)
        }

# 注册计数器重置处理器
@register_handler("/api/counter/reset", method="POST", timeout=10)
def reset_counter(job: HttpJob):
    """
    重置计数器处理程序
    """
    # 从请求中获取要重置的计数器ID和值
    request_data = job.body.get("data", {})
    counter_id = request_data.get("counter_id", "default")
    initial_value = request_data.get("value", 0)
    
    # 调用计数器服务重置计数
    new_value = counter.reset(counter_id, initial_value)
    
    # 返回响应
    return {
        "success": True,
        "counter_id": counter_id,
        "value": new_value
    }

# 注册获取计数器值处理器
@register_handler("/api/counter/get", method="GET", timeout=10)
def get_counter(job: HttpJob):
    """
    获取计数器值处理程序
    """
    # 从URL参数获取计数器ID
    counter_id = job.params.get("counter_id", "default")
    
    # 获取计数器当前值
    current_value = counter.get(counter_id)
    
    # 返回响应
    return {
        "success": True,
        "counter_id": counter_id,
        "value": current_value
    }

def main(version=None):
    """工作节点主函数入口点"""
    # 如果没有指定版本，使用随机版本
    worker_version = version or f"worker-{uuid.uuid4().hex[:8]}"
    logger.info(f"启动工作节点，版本: {worker_version}")
    worker_sdk.on_call(version=worker_version)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动工作节点")
    parser.add_argument("--version", help="工作节点版本", default=None)
    args = parser.parse_args()
    
    main(version=args.version) 