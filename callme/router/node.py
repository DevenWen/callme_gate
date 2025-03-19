#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
节点抽象类
用于表示一个工作节点及其状态
"""
from typing import Dict, List, Any, Optional, Set
import time
from enum import Enum


class NodeStatus(Enum):
    """节点状态枚举"""
    ONLINE = "online"     # 节点在线，正常工作
    OFFLINE = "offline"   # 节点离线
    BUSY = "busy"         # 节点繁忙
    ERROR = "error"       # 节点出错
    STARTING = "starting" # 节点正在启动
    STOPPING = "stopping" # 节点正在停止


class Node:
    """工作节点类，表示一个服务工作节点及其状态"""
    
    def __init__(self, worker_id: str, version: str, queue: str):
        """初始化工作节点
        
        Args:
            worker_id: 工作节点唯一标识
            version: 工作节点实现的服务版本
            queue: 工作节点监听的队列名称
        """
        self.worker_id = worker_id
        self.version = version
        self.queue = queue
        self.status = NodeStatus.STARTING
        self.routes: Set[str] = set()  # 节点支持的路由ID集合
        self.metadata: Dict[str, Any] = {}
        self.started_at = int(time.time())
        self.last_heartbeat = int(time.time())
        self.metrics = {
            "total_requests": 0,      # 总请求数
            "completed_requests": 0,  # 完成的请求数
            "failed_requests": 0,     # 失败的请求数
            "avg_process_time": 0,    # 平均处理时间（毫秒）
        }
        
    def update_status(self, status: NodeStatus):
        """更新节点状态
        
        Args:
            status: 新的节点状态
        """
        self.status = status
        if status == NodeStatus.ONLINE:
            self.last_heartbeat = int(time.time())
            
    def heartbeat(self):
        """更新节点心跳时间"""
        self.last_heartbeat = int(time.time())
        
    def add_route(self, route_id: str):
        """添加节点支持的路由
        
        Args:
            route_id: 路由唯一标识(method:path)
        """
        self.routes.add(route_id)
        
    def remove_route(self, route_id: str) -> bool:
        """移除节点支持的路由
        
        Args:
            route_id: 路由唯一标识(method:path)
            
        Returns:
            是否成功移除
        """
        if route_id in self.routes:
            self.routes.remove(route_id)
            return True
        return False
        
    def update_metrics(self, request_completed: bool, request_failed: bool, process_time: float):
        """更新节点性能指标
        
        Args:
            request_completed: 是否完成了请求
            request_failed: 请求是否失败
            process_time: 处理时间（毫秒）
        """
        self.metrics["total_requests"] += 1
        
        if request_completed:
            self.metrics["completed_requests"] += 1
            
        if request_failed:
            self.metrics["failed_requests"] += 1
            
        # 更新平均处理时间
        total_completed = self.metrics["completed_requests"]
        if total_completed > 0:
            current_avg = self.metrics["avg_process_time"]
            self.metrics["avg_process_time"] = (current_avg * (total_completed - 1) + process_time) / total_completed
            
    def is_alive(self, max_heartbeat_age: int = 30) -> bool:
        """检查节点是否存活
        
        Args:
            max_heartbeat_age: 最大心跳间隔（秒）
            
        Returns:
            节点是否存活
        """
        return (int(time.time()) - self.last_heartbeat) <= max_heartbeat_age
        
    def to_dict(self) -> Dict[str, Any]:
        """将节点信息转换为字典格式
        
        Returns:
            表示节点信息的字典
        """
        return {
            "worker_id": self.worker_id,
            "version": self.version,
            "queue": self.queue,
            "status": self.status.value,
            "routes": list(self.routes),
            "metadata": self.metadata,
            "started_at": self.started_at,
            "last_heartbeat": self.last_heartbeat,
            "uptime": int(time.time()) - self.started_at,
            "metrics": self.metrics
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Node':
        """从字典创建节点对象
        
        Args:
            data: 表示节点信息的字典
            
        Returns:
            节点对象
        """
        node = cls(
            data["worker_id"],
            data["version"],
            data["queue"]
        )
        node.status = NodeStatus(data.get("status", "offline"))
        node.routes = set(data.get("routes", []))
        node.metadata = data.get("metadata", {})
        node.started_at = data.get("started_at", int(time.time()))
        node.last_heartbeat = data.get("last_heartbeat", int(time.time()))
        node.metrics = data.get("metrics", {
            "total_requests": 0,
            "completed_requests": 0,
            "failed_requests": 0,
            "avg_process_time": 0
        })
        return node 