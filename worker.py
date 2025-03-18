#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import signal
import logging
import argparse
import uuid
from flask import Flask
from dotenv import load_dotenv
load_dotenv()

from lib.app_worker import worker, start_worker, stop_worker, register_handler
from lib.model.http_job import HttpJob
from lib.counter import counter

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker")

# 创建Flask应用（用于测试和开发，实际生产环境可不需要）
app = Flask(__name__)

# 捕获中断信号，优雅退出
def signal_handler(sig, frame):
    logger.info("接收到退出信号，正在停止工作节点...")
    stop_worker()
    logger.info("工作节点已停止")
    exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# 注册计数器处理器
@register_handler("/api/counter/increment", method="POST", timeout=10)
def increment_counter(job: HttpJob):
    """增加计数器
    
    Args:
        job: HTTP作业
        
    Returns:
        处理结果
    """
    # 获取计数器名称和增加量
    data = job.json_data or {}
    counter_name = data.get("name", "default")
    amount = int(data.get("amount", 1))
    
    # 增加计数器值
    logger.info(f"增加计数器 {counter_name}, 增加量: {amount}")
    new_value = counter.increment(counter_name, amount)
    
    # 返回结果
    return {
        "counter_name": counter_name,
        "value": new_value,
        "operation": "increment",
        "amount": amount
    }

@register_handler("/api/counter/decrement", method="POST", timeout=10)
def decrement_counter(job: HttpJob):
    """减少计数器
    
    Args:
        job: HTTP作业
        
    Returns:
        处理结果
    """
    # 获取计数器名称和减少量
    data = job.json_data or {}
    counter_name = data.get("name", "default")
    amount = int(data.get("amount", 1))
    
    # 减少计数器值
    logger.info(f"减少计数器 {counter_name}, 减少量: {amount}")
    new_value = counter.decrement(counter_name, amount)
    
    # 模拟延迟处理
    time.sleep(0.5)
    
    # 返回结果
    return {
        "counter_name": counter_name,
        "value": new_value,
        "operation": "decrement",
        "amount": amount
    }

@register_handler("/api/counter/reset", method="POST", timeout=10)
def reset_counter(job: HttpJob):
    """重置计数器
    
    Args:
        job: HTTP作业
        
    Returns:
        处理结果
    """
    # 获取计数器名称
    data = job.json_data or {}
    counter_name = data.get("name", "default")
    
    # 重置计数器
    logger.info(f"重置计数器 {counter_name}")
    success = counter.reset(counter_name)
    
    # 返回结果
    return {
        "counter_name": counter_name,
        "value": 0,
        "operation": "reset",
        "success": success
    }

@register_handler("/api/counter/get", method="GET", timeout=10)
def get_counter(job: HttpJob):
    """获取计数器值
    
    Args:
        job: HTTP作业
        
    Returns:
        处理结果
    """
    # 获取计数器名称
    query_params = job.query_params or {}
    counter_name = query_params.get("name", ["default"])[0]
    
    # 获取计数器值
    value = counter.get(counter_name)
    logger.info(f"获取计数器 {counter_name}: {value}")
    
    # 返回结果
    return {
        "counter_name": counter_name,
        "value": value
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="启动工作节点")
    parser.add_argument("--version", help="工作节点版本", default=None)
    parser.add_argument("--debug", help="是否启动Flask调试接口", action="store_true")
    args = parser.parse_args()
    
    # 如果没有指定版本，使用随机版本
    worker_version = args.version or f"worker-{uuid.uuid4().hex[:8]}"
    
    logger.info(f"启动工作节点，版本: {worker_version}")
    start_worker(worker_version)
    
    if args.debug:
        # 在开发模式下启动Flask接口
        app.run(host='0.0.0.0', port=9001, debug=True)
    else:
        # 简单地保持进程运行
        logger.info(f"工作节点 {worker_version} 已启动，按Ctrl+C停止")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("接收到中断，停止工作节点...")
            stop_worker()
            logger.info("工作节点已停止") 