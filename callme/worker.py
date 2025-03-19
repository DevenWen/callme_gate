#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import logging
import uuid
import signal
from typing import Callable, Dict, Any, Optional, List, Union

from .app_worker import worker, start_worker, stop_worker, register_handler
from .app_worker import register_handler as app_worker_register_handler
from .model.http_job import HttpJob, JobStatus

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("worker_sdk")

class Worker:
    """Worker SDK 封装类
    
    封装了 app_worker 的功能，提供更简单的 API
    """
    
    def __init__(self, debug=False):
        """初始化 Worker SDK
        
        Args:
            debug: 是否启用调试模式
        """
        self.debug = debug
        self.version = None
        self.running = False
        self._handlers_registered = False
        
    def register_handler(self, path, method="GET", timeout=10):
        """注册路由处理函数的装饰器
        
        Args:
            path: API路径
            method: HTTP方法，默认为GET
            timeout: 处理超时时间(秒)
            
        Returns:
            装饰器函数
        """
        # 直接调用 app_worker 中的 register_handler
        return app_worker_register_handler(path, method, timeout)
        
    def on_call(self, version=None):
        """启动工作节点
        
        Args:
            version: 工作节点版本，如不提供则使用随机版本
            debug: 是否启用调试模式，如不提供则使用初始化时的设置
        """
        # 如果没有指定版本，使用随机版本
        self.version = version or f"worker-{uuid.uuid4().hex[:8]}"
        
        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        logger.info(f"启动工作节点，版本: {self.version}")
        
        # 启动工作节点
        start_worker(self.version)
        self.running = True
        
        # 保持进程运行
        logger.info(f"工作节点 {self.version} 已启动，按Ctrl+C停止")
        try:
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        """停止工作节点"""
        if not self.running:
            return
            
        logger.info("正在停止工作节点...")
        stop_worker()
        self.running = False
        logger.info("工作节点已停止")
        
    def _signal_handler(self, sig, frame):
        """处理终止信号，优雅地关闭工作节点"""
        logger.info("接收到中断，停止工作节点...")
        self.stop()
        logger.info("工作节点已停止")

# 创建全局 Worker 实例
worker_sdk = Worker()

# 导出装饰器以便简化使用
register_handler = worker_sdk.register_handler

# 导出 Worker 类供高级用例使用
Worker = Worker 