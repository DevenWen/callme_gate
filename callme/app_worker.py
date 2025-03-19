#!/usr/bin/env python
# -*- coding: utf-8 -*-

import time
import json
import threading
import logging
import uuid
from typing import Callable, Dict, Any, Optional, List, Union

from .redis_client import RedisClient
from .model.http_job import HttpJob, JobStatus
from .model.job_repository import http_job_repository
from .router.route_registry import route_registry
from .router.job_dispatcher import job_dispatcher

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app_worker")

class AppWorker:
    """应用工作节点
    
    负责从队列获取任务并处理
    """
    
    def __init__(self, worker_version: str = None):
        """初始化工作节点
        
        Args:
            worker_version: 工作节点版本，如不提供则自动生成
        """
        self.redis = RedisClient()
        self.running = False
        self.handlers = {}  # 路径到处理函数的映射
        self.worker_thread = None
        self.worker_version = worker_version or f"worker-{uuid.uuid4().hex[:8]}"
        self.registered_routes = set()  # 记录已注册的路由
        
    def register_handler(self, path: str, method: str, handler: Callable[[HttpJob], Any], timeout: int = 5):
        """注册路径处理器
        
        Args:
            path: API路径
            method: HTTP方法
            handler: 处理函数，接收HttpJob对象，返回处理结果
            timeout: 处理超时时间(秒)
        """
        key = f"{method.upper()}:{path}"
        logger.info(f"注册处理器: {key}")
        self.handlers[key] = handler
        
        # 获取队列名称
        queue = self.get_queue_name()
        
        # 向服务注册表注册路由
        if route_registry.register_route(path, method, self.worker_version, self.worker_version, queue, timeout):
            logger.info(f"路由 {key} 已注册到服务发现系统")
            self.registered_routes.add(key)
        else:
            logger.error(f"路由 {key} 注册到服务发现系统失败")
        
    def process_job(self, job: HttpJob) -> bool:
        """处理单个作业
        
        Args:
            job: 待处理的作业
            
        Returns:
            是否成功处理
        """
        try:
            # 更新作业状态为运行中
            job.update_status(JobStatus.RUNNING)
            http_job_repository.save(job)
            
            # 创建处理器键
            handler_key = f"{job.method}:{job.path}"
            
            # 检查是否有对应的处理器
            if handler_key not in self.handlers:
                logger.warning(f"找不到处理 {handler_key} 的处理器")
                job.set_error(f"找不到处理 {job.method} {job.path} 的处理器")
                http_job_repository.save(job)
                return False
                
            # 获取处理器并处理请求
            handler = self.handlers[handler_key]
            logger.info(f"使用处理器 {handler.__name__} 处理请求 {job.request_id}")
            
            try:
                # 调用处理函数
                result = handler(job)
                
                # 设置作业的响应
                job.set_response(
                    status=200,
                    headers={"Content-Type": "application/json"},
                    body=result
                )
                
                # 更新作业状态
                http_job_repository.save(job)
                
                # 发布处理结果
                job_dispatcher.publish_result(job.request_id, json.dumps(job.to_dict()))
                
                logger.info(f"请求 {job.request_id} 处理成功")
                return True
                
            except Exception as e:
                # 记录错误并更新作业状态
                logger.exception(f"处理请求 {job.request_id} 时发生错误")
                error_message = str(e)
                job.set_error(error_message)
                http_job_repository.save(job)
                
                # 发布错误结果
                job_dispatcher.publish_result(job.request_id, json.dumps(job.to_dict()))
                
                return False
                
        except Exception as e:
            logger.exception(f"处理请求 {job.request_id} 时发生未处理的错误")
            try:
                job.set_error(f"处理作业时发生未处理的错误: {str(e)}")
                http_job_repository.save(job)
                
                # 尝试发布错误结果
                job_dispatcher.publish_result(job.request_id, json.dumps(job.to_dict()))
            except:
                logger.exception("无法保存错误状态")
            return False
    
    def get_queue_name(self) -> str:
        """获取当前工作节点的队列名称
        
        Returns:
            队列名称
        """
        # 使用固定格式创建队列名称
        return f"callme_gate#worker_queue:{self.worker_version}"
    
    def dequeue_task(self, timeout: int = 0) -> Optional[str]:
        """从队列中获取任务
        
        Args:
            timeout: 等待超时时间（秒），0表示不等待
            
        Returns:
            任务ID或None（无任务）
        """
        queue_name = self.get_queue_name()
        
        try:
            # 使用阻塞方式获取任务
            result = self.redis.client.blpop(queue_name, timeout)
            if result:
                _, task_id = result
                logger.info(f"从队列 {queue_name} 获取到任务: {task_id}")
                return task_id
            return None
        except Exception as e:
            logger.error(f"从队列获取任务时发生错误: {e}")
            return None
    
    def process_queue(self):
        """持续处理队列中的任务"""
        logger.info(f"工作节点 {self.worker_version} 开始处理队列")
        
        while self.running:
            try:
                # 等待并获取任务
                task_id = self.dequeue_task(timeout=1)
                
                if not task_id:
                    continue
                    
                # 获取任务详细信息
                job = http_job_repository.get(task_id)
                
                if job is None:
                    logger.warning(f"找不到任务: {task_id}")
                    continue
                    
                # 处理任务
                self.process_job(job)
                    
            except Exception as e:
                logger.exception(f"处理队列时发生错误: {e}")
                # 短暂休息后继续
                time.sleep(0.5)
                
        logger.info("工作节点已停止处理队列")
    
    def start(self):
        """启动工作节点"""
        if self.running:
            logger.warning("工作节点已在运行中")
            return
            
        self.running = True
        
        # 启动工作线程
        self.worker_thread = threading.Thread(target=self.process_queue)
        self.worker_thread.daemon = True
        self.worker_thread.start()
        
        logger.info(f"工作节点 {self.worker_version} 已启动")
    
    def stop(self):
        """停止工作节点"""
        if not self.running:
            logger.warning("工作节点未在运行")
            return
            
        self.running = False
        
        # 等待工作线程结束
        if self.worker_thread and self.worker_thread.is_alive():
            self.worker_thread.join(timeout=2)
            
        # 取消注册所有路由
        for route_id in self.registered_routes:
            method, path = route_id.split(":", 1)
            route_registry.unregister_route(path, method, self.worker_version)
            
        logger.info(f"工作节点 {self.worker_version} 已停止")

# 全局工作节点实例
worker = None

def start_worker(version: str = None):
    """启动全局工作节点
    
    Args:
        version: 工作节点版本，如不提供则自动生成
    """
    global worker
    worker = AppWorker(worker_version=version)
    
    # 注册所有待注册的处理器
    if hasattr(register_handler, 'pending_handlers'):
        for path, method, handler, timeout in register_handler.pending_handlers:
            worker.register_handler(path, method, handler, timeout)
        # 清空待注册列表
        register_handler.pending_handlers = []
    
    worker.start()

def stop_worker():
    """停止全局工作节点"""
    global worker
    if worker:
        worker.stop()

def register_handler(path: str, method: str = "GET", timeout: int = 5):
    """注册路由处理函数的装饰器
    
    Args:
        path: API路径
        method: HTTP方法，默认为GET
        timeout: 处理超时时间(秒)
        
    Returns:
        装饰器函数
    """
    def decorator(f):
        global worker
        if worker:
            worker.register_handler(path, method, f, timeout)
        else:
            # 当 worker 未初始化时，存储路由信息
            # 在 worker 初始化时会进行实际注册
            if not hasattr(register_handler, 'pending_handlers'):
                register_handler.pending_handlers = []
            register_handler.pending_handlers.append((path, method, f, timeout))
        return f
    return decorator 