#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
路由信息抽象类
用于表示API路由和相关信息
"""
from typing import Dict, List, Any, Optional
import time


class Route:
    """路由信息类，表示一个API路由及其处理信息"""
    
    def __init__(self, path: str, method: str, timeout: int = 5):
        """初始化路由信息
        
        Args:
            path: API路径
            method: HTTP方法
            timeout: 处理超时时间（秒）
        """
        self.path = path
        self.method = method.upper()
        self.timeout = timeout
        self.route_id = f"{self.method}:{self.path}"
        self.worker_nodes: Dict[str, Dict[str, Any]] = {}  # worker_id -> worker信息
        self.created_at = int(time.time())
        self.updated_at = int(time.time())
        
    def add_worker(self, worker_id: str, version: str, queue: str, metadata: Optional[Dict[str, Any]] = None):
        """添加一个工作节点到路由
        
        Args:
            worker_id: 工作节点唯一标识
            version: 工作节点实现的服务版本
            queue: 工作节点监听的队列名称
            metadata: 额外的元数据信息
        """
        self.worker_nodes[worker_id] = {
            "worker_id": worker_id,
            "version": version,
            "queue": queue,
            "metadata": metadata or {},
            "added_at": int(time.time())
        }
        self.updated_at = int(time.time())
        
    def remove_worker(self, worker_id: str):
        """从路由中移除一个工作节点
        
        Args:
            worker_id: 工作节点唯一标识
        
        Returns:
            bool: 是否成功移除
        """
        if worker_id in self.worker_nodes:
            del self.worker_nodes[worker_id]
            self.updated_at = int(time.time())
            return True
        return False
        
    def get_workers(self) -> List[Dict[str, Any]]:
        """获取处理此路由的所有工作节点
        
        Returns:
            工作节点信息列表
        """
        return list(self.worker_nodes.values())
        
    def get_versions(self) -> List[str]:
        """获取此路由支持的所有版本
        
        Returns:
            版本列表
        """
        return list(set(worker["version"] for worker in self.worker_nodes.values()))
        
    def to_dict(self) -> Dict[str, Any]:
        """将路由信息转换为字典格式
        
        Returns:
            表示路由信息的字典
        """
        return {
            "route_id": self.route_id,
            "path": self.path,
            "method": self.method,
            "timeout": self.timeout,
            "worker_nodes": self.worker_nodes,
            "versions": self.get_versions(),
            "worker_count": len(self.worker_nodes),
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Route':
        """从字典创建路由对象
        
        Args:
            data: 表示路由信息的字典
            
        Returns:
            路由对象
        """
        route = cls(data["path"], data["method"], data.get("timeout", 5))
        route.route_id = data["route_id"]
        route.worker_nodes = data.get("worker_nodes", {})
        route.created_at = data.get("created_at", int(time.time()))
        route.updated_at = data.get("updated_at", int(time.time()))
        return route 